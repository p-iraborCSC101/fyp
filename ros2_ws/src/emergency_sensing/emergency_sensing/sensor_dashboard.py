"""RViz dashboard markers for simulated IoT sensor state."""

from __future__ import annotations

import json
from collections import deque

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray


class SensorDashboard(Node):
    def __init__(self) -> None:
        super().__init__('sensor_dashboard')

        self.publisher = self.create_publisher(MarkerArray, '/sensor_dashboard', 10)

        self.create_subscription(String, '/sensor/camera_fall', self.on_camera, 10)
        self.create_subscription(String, '/sensor/heart_rate', self.on_heart_rate, 10)
        self.create_subscription(String, '/sensor/motion_state', self.on_motion, 10)

        self._camera = {}
        self._heart = {}
        self._motion = {}
        self._hr_series: deque[int] = deque(maxlen=40)

        self.timer = self.create_timer(0.5, self.publish_dashboard)

    def on_camera(self, msg: String) -> None:
        self._camera = self._parse(msg)

    def on_heart_rate(self, msg: String) -> None:
        self._heart = self._parse(msg)
        if isinstance(self._heart.get('heart_rate_bpm'), (int, float)):
            self._hr_series.append(int(self._heart['heart_rate_bpm']))

    def on_motion(self, msg: String) -> None:
        self._motion = self._parse(msg)

    def publish_dashboard(self) -> None:
        text_lines = [
            f"Camera fall: {self._camera.get('fall_detected', '--')}",
            f"HR bpm: {self._heart.get('heart_rate_bpm', '--')}",
            f"Motion ok: {self._motion.get('motion_ok', '--')}",
        ]
        marker = Marker()
        marker.header.frame_id = 'map'
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = 'sensor_dashboard'
        marker.id = 0
        marker.type = Marker.TEXT_VIEW_FACING
        marker.action = Marker.ADD
        marker.pose.position.x = 1.0
        marker.pose.position.y = 1.0
        marker.pose.position.z = 2.0
        marker.scale.z = 0.4
        marker.color.r = 0.2
        marker.color.g = 0.9
        marker.color.b = 0.2
        marker.color.a = 1.0
        marker.text = "\n".join(text_lines)

        array = MarkerArray()
        array.markers.append(marker)
        array.markers.append(self._build_hr_plot())
        self.publisher.publish(array)

    def _build_hr_plot(self) -> Marker:
        marker = Marker()
        marker.header.frame_id = 'map'
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = 'sensor_dashboard'
        marker.id = 1
        marker.type = Marker.LINE_STRIP
        marker.action = Marker.ADD
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.05
        marker.color.r = 1.0
        marker.color.g = 0.4
        marker.color.b = 0.1
        marker.color.a = 1.0

        points = []
        base_x = 1.0
        base_y = 0.2
        dx = 0.08
        if self._hr_series:
            min_hr = min(self._hr_series)
            max_hr = max(self._hr_series)
            span = max(max_hr - min_hr, 1)
            for idx, hr in enumerate(self._hr_series):
                y = base_y + (hr - min_hr) / span * 0.8
                points.append(Point(x=base_x + idx * dx, y=y, z=1.8))
        else:
            points.append(Point(x=base_x, y=base_y, z=1.8))
            points.append(Point(x=base_x + dx, y=base_y, z=1.8))

        marker.points = points
        return marker

    @staticmethod
    def _parse(msg: String) -> dict:
        try:
            return json.loads(msg.data)
        except json.JSONDecodeError:
            return {'raw': msg.data}


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SensorDashboard()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
