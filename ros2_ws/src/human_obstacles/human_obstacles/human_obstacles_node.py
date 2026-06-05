"""Software-driven dynamic human obstacles.

Gazebo animates scripted <actor> entities via its animation system and does NOT
broadcast their live poses on the /world/<world>/pose/info (static snapshot) or
.../dynamic_pose/info (physics-only -- carries the robot, never the actors)
topics. So the planner could never "see" the walking humans.

This node instead reproduces the actors' scripted trajectories in software: it
loads the `humans:` waypoint lists from the scenario YAML and, on a timer driven
by sim time, publishes each human's interpolated grid position on
/dynamic_obstacles (a PoseArray). The waypoints mirror the <actor> trajectories
in the matching world file, so the planner's dynamic obstacles stay in sync with
what Gazebo renders.
"""

from pathlib import Path

import rclpy
import yaml
from geometry_msgs.msg import Pose, PoseArray
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String


class HumanObstaclesNode(Node):
    def __init__(self) -> None:
        super().__init__("human_obstacles")
        qos = QoSProfile(depth=10)

        self._frame_id = str(self.declare_parameter("frame_id", "world").value)
        self._scenario_file = str(self.declare_parameter("scenario_file", "").value)
        self._publish_rate = float(self.declare_parameter("publish_rate_hz", 10.0).value)
        self._z = float(self.declare_parameter("human_z", 1.0).value)

        self._humans = self._load_humans()

        self._pose_pub = self.create_publisher(PoseArray, "/dynamic_obstacles", qos)
        self._status_pub = self.create_publisher(String, "/human_obstacles_status", qos)

        period = 1.0 / self._publish_rate if self._publish_rate > 0 else 0.1
        self._timer = self.create_timer(period, self._tick)

        self.get_logger().info(
            f"Human obstacles node started with {len(self._humans)} human(s) "
            f"from {self._scenario_file or '<none>'}."
        )

    # ------------------------------------------------------------------
    def _load_humans(self) -> list[list[tuple[float, float, float]]]:
        """Return a list of trajectories; each is a list of (time, x, y)."""
        if not self._scenario_file:
            self.get_logger().warn("No scenario_file parameter; no humans loaded.")
            return []
        path = Path(self._scenario_file)
        if not path.exists():
            self.get_logger().error(f"Scenario file not found: {self._scenario_file}")
            return []
        cfg = yaml.safe_load(path.read_text()) or {}
        humans: list[list[tuple[float, float, float]]] = []
        for entry in cfg.get("humans", []):
            wps = entry.get("waypoints", []) if isinstance(entry, dict) else []
            traj = [(float(w[0]), float(w[1]), float(w[2])) for w in wps if len(w) >= 3]
            if len(traj) >= 2:
                humans.append(traj)
        return humans

    @staticmethod
    def _interpolate(traj: list[tuple[float, float, float]], t: float) -> tuple[float, float]:
        """Position along a looping trajectory at sim time t."""
        period = traj[-1][0]
        tm = t % period if period > 0 else 0.0
        for i in range(1, len(traj)):
            t0, x0, y0 = traj[i - 1]
            t1, x1, y1 = traj[i]
            if t0 <= tm <= t1:
                span = t1 - t0
                r = (tm - t0) / span if span > 0 else 0.0
                return (x0 + r * (x1 - x0), y0 + r * (y1 - y0))
        # Fallback: last waypoint position.
        return (traj[-1][1], traj[-1][2])

    def _tick(self) -> None:
        if not self._humans:
            return
        now_s = self.get_clock().now().nanoseconds / 1e9

        msg = PoseArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._frame_id
        for traj in self._humans:
            x, y = self._interpolate(traj, now_s)
            pose = Pose()
            pose.position.x = x
            pose.position.y = y
            pose.position.z = self._z
            pose.orientation.w = 1.0
            msg.poses.append(pose)

        self._pose_pub.publish(msg)
        self._status_pub.publish(String(data=f"dynamic_obstacles={len(msg.poses)}"))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HumanObstaclesNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
