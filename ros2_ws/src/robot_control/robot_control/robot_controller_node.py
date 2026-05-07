"""Diff-drive controller that follows planned routes from the path planner.

Listens on /planned_route, extracts the waypoint list, and drives the
robot toward each waypoint in turn.  Detects stalled progress (no odom
movement while a non-zero cmd_vel is being sent) and publishes a
/replan_request so the planner can inject a dynamic obstacle and try again.

On arrival or final-failure it publishes a structured /robot_status
message that the response logger turns into one CSV row.
"""

from __future__ import annotations

import json
import math
from typing import List, Tuple

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node
from std_msgs.msg import String


def normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def yaw_from_quaternion(q) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


class RobotControllerNode(Node):
    def __init__(self):
        super().__init__('robot_controller')
        self.cmd_publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.status_publisher = self.create_publisher(String, '/robot_status', 10)
        self.path_publisher = self.create_publisher(Path, '/planned_path', 10)
        self.replan_publisher = self.create_publisher(String, '/replan_request', 10)

        self.create_subscription(String, '/planned_route', self.route_callback, 10)
        self.create_subscription(Odometry, '/odom', self.odom_callback, 10)

        self.declare_parameter('grid_scale', 1.0)
        self.declare_parameter('max_linear_speed', 0.45)
        self.declare_parameter('max_angular_speed', 1.5)
        self.declare_parameter('waypoint_tolerance', 0.4)
        self.declare_parameter('linear_gain', 0.8)
        self.declare_parameter('angular_gain', 2.2)
        self.declare_parameter('stall_timeout_s', 2.5)
        self.declare_parameter('stall_min_cmd_linear', 0.05)
        self.declare_parameter('max_replans_per_alert', 6)

        self.pose = None
        self.current_path: List[Tuple[float, float]] = []
        self.path_index = 0
        self.arrived = False
        self.failed = False

        self.alert_id: str | None = None
        self.planner: str | None = None
        self.t_arrived_ns: int | None = None

        self._last_progress_pos: Tuple[float, float] | None = None
        self._last_progress_time = self.get_clock().now()
        self._replans_sent = 0
        self._cmd_linear_last = 0.0

        self.timer = self.create_timer(0.1, self.control_loop)

    # ------------------------------------------------------------------
    # subscribers
    # ------------------------------------------------------------------
    def odom_callback(self, msg: Odometry):
        self.pose = msg.pose.pose

    def route_callback(self, msg: String):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error('Invalid route payload')
            return

        new_alert_id = payload.get('alert_id')
        if new_alert_id and new_alert_id != self.alert_id:
            self.alert_id = new_alert_id
            self._replans_sent = 0
            self.t_arrived_ns = None

        self.planner = payload.get('planner')

        if payload.get('status') != 'success':
            self.get_logger().warning('Route failed; sending failure status')
            self._publish_status(success=False, reason=payload.get('reason', 'no_path'))
            self.current_path = []
            self.path_index = 0
            self.arrived = False
            self.failed = True
            return

        scale = self.get_parameter('grid_scale').get_parameter_value().double_value
        raw_path = payload.get('path', [])
        self.current_path = [(point['x'] * scale, point['y'] * scale) for point in raw_path]
        self.path_index = 0
        self.arrived = False
        self.failed = False
        self._last_progress_pos = None
        self._last_progress_time = self.get_clock().now()
        self.publish_path()
        self.get_logger().info(
            f'Loaded route alert={self.alert_id} planner={self.planner} '
            f'waypoints={len(self.current_path)}'
        )

    # ------------------------------------------------------------------
    # publishing
    # ------------------------------------------------------------------
    def publish_path(self):
        if not self.current_path:
            return
        path_msg = Path()
        path_msg.header.frame_id = 'map'
        path_msg.header.stamp = self.get_clock().now().to_msg()
        for x, y in self.current_path:
            pose = PoseStamped()
            pose.header.frame_id = 'map'
            pose.header.stamp = path_msg.header.stamp
            pose.pose.position.x = float(x)
            pose.pose.position.y = float(y)
            pose.pose.position.z = 0.0
            pose.pose.orientation.w = 1.0
            path_msg.poses.append(pose)
        self.path_publisher.publish(path_msg)

    def _publish_status(self, success: bool, reason: str = '') -> None:
        msg = String()
        msg.data = json.dumps({
            'alert_id': self.alert_id,
            'planner': self.planner,
            'status': 'arrived' if success else 'failed',
            'reason': reason,
            't_arrived_ns': self.t_arrived_ns,
            'replans': self._replans_sent,
        })
        self.status_publisher.publish(msg)

    def _publish_replan(self) -> None:
        if self.pose is None:
            return
        cell = (int(round(self.pose.position.x)), int(round(self.pose.position.y)))
        msg = String()
        msg.data = json.dumps({
            'alert_id': self.alert_id,
            'robot_cell': list(cell),
            'replans_so_far': self._replans_sent,
        })
        self.replan_publisher.publish(msg)
        self._replans_sent += 1
        self._last_progress_time = self.get_clock().now()
        self.get_logger().warn(
            f'Stall detected near {cell}; replan #{self._replans_sent} requested for {self.alert_id}'
        )

    # ------------------------------------------------------------------
    # control loop
    # ------------------------------------------------------------------
    def control_loop(self):
        if self.pose is None or not self.current_path or self.failed:
            return

        if self.path_index >= len(self.current_path):
            if not self.arrived:
                self.send_stop()
                self.t_arrived_ns = self.get_clock().now().nanoseconds
                self._publish_status(success=True, reason='arrived')
                self.arrived = True
            return

        target_x, target_y = self.current_path[self.path_index]
        dx = target_x - self.pose.position.x
        dy = target_y - self.pose.position.y
        distance = math.hypot(dx, dy)

        tol = self.get_parameter('waypoint_tolerance').get_parameter_value().double_value
        if distance < tol:
            self.path_index += 1
            return

        # --- stall detection -----------------------------------------
        cur_pos = (self.pose.position.x, self.pose.position.y)
        now = self.get_clock().now()
        if self._last_progress_pos is None:
            self._last_progress_pos = cur_pos
            self._last_progress_time = now
        elif math.hypot(cur_pos[0] - self._last_progress_pos[0],
                        cur_pos[1] - self._last_progress_pos[1]) > 0.05:
            self._last_progress_pos = cur_pos
            self._last_progress_time = now
        else:
            stall_to = self.get_parameter('stall_timeout_s').get_parameter_value().double_value
            min_cmd = self.get_parameter('stall_min_cmd_linear').get_parameter_value().double_value
            elapsed = (now.nanoseconds - self._last_progress_time.nanoseconds) / 1e9
            if elapsed > stall_to and self._cmd_linear_last > min_cmd:
                max_r = self.get_parameter('max_replans_per_alert').get_parameter_value().integer_value
                if self._replans_sent < max_r:
                    self._publish_replan()
                else:
                    self.send_stop()
                    self._publish_status(success=False, reason='replan_budget_exhausted')
                    self.failed = True
                return

        # --- proportional drive --------------------------------------
        yaw = yaw_from_quaternion(self.pose.orientation)
        target_yaw = math.atan2(dy, dx)
        heading_error = normalize_angle(target_yaw - yaw)

        max_lin = self.get_parameter('max_linear_speed').get_parameter_value().double_value
        max_ang = self.get_parameter('max_angular_speed').get_parameter_value().double_value
        lin_gain = self.get_parameter('linear_gain').get_parameter_value().double_value
        ang_gain = self.get_parameter('angular_gain').get_parameter_value().double_value

        cmd = Twist()
        cmd.linear.x = min(max_lin, lin_gain * distance)
        cmd.angular.z = max(-max_ang, min(max_ang, ang_gain * heading_error))
        if abs(heading_error) > 1.0:
            cmd.linear.x *= 0.2

        self._cmd_linear_last = cmd.linear.x
        self.cmd_publisher.publish(cmd)

    def send_stop(self):
        self._cmd_linear_last = 0.0
        self.cmd_publisher.publish(Twist())


def main(args=None):
    rclpy.init(args=args)
    node = RobotControllerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.send_stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
