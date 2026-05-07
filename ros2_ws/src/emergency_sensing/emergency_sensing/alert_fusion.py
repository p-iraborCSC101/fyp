"""Fusion node that converts sensor readings into an emergency alert."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import rclpy
import yaml
from rclpy.node import Node
from std_msgs.msg import String


class AlertFusionNode(Node):
    def __init__(self):
        super().__init__('alert_fusion')

        self.declare_parameter('scenario_file', '')
        self.declare_parameter('run_id', 1)
        self.declare_parameter('seed', 42)
        self.declare_parameter('heart_rate_threshold', 120)
        self.declare_parameter('event_type', 'fall_detected')

        self.publisher = self.create_publisher(String, '/emergency_alert', 10)

        self.create_subscription(String, '/sensor/camera_fall', self.on_camera, 10)
        self.create_subscription(String, '/sensor/heart_rate', self.on_heart_rate, 10)
        self.create_subscription(String, '/sensor/motion_state', self.on_motion, 10)

        self.run_id = int(self.get_parameter('run_id').get_parameter_value().integer_value)
        seed = int(self.get_parameter('seed').get_parameter_value().integer_value)
        self._rng = random.Random(seed + self.run_id)

        self.patient_locations = self._load_locations()
        self._latest = {}
        self._alert_sent = False

    def _load_locations(self) -> list[dict]:
        scenario_file = self.get_parameter('scenario_file').get_parameter_value().string_value
        if not scenario_file:
            return [
                {'name': 'patient_a', 'x': 4, 'y': 9, 'severity': 'high'},
                {'name': 'patient_b', 'x': 12, 'y': 9, 'severity': 'high'},
            ]
        path = Path(scenario_file)
        if not path.exists():
            self.get_logger().error(f'Scenario file not found: {scenario_file}')
            return []
        cfg = yaml.safe_load(path.read_text()) or {}
        return list(cfg.get('patient_locations', []))

    def on_camera(self, msg: String) -> None:
        payload = self._parse(msg)
        self._latest['camera'] = payload
        if payload.get('fall_detected'):
            self._try_publish(payload)

    def on_heart_rate(self, msg: String) -> None:
        payload = self._parse(msg)
        self._latest['heart'] = payload
        if payload.get('heart_rate_bpm', 0) >= self.get_parameter('heart_rate_threshold').get_parameter_value().integer_value:
            self._try_publish(payload)

    def on_motion(self, msg: String) -> None:
        payload = self._parse(msg)
        self._latest['motion'] = payload
        if payload.get('motion_ok') is False:
            self._try_publish(payload)

    def _try_publish(self, trigger_payload: dict) -> None:
        if self._alert_sent:
            return
        patient_id = trigger_payload.get('patient_id')
        location = next((p for p in self.patient_locations if p.get('name') == patient_id), None)
        if not location and self.patient_locations:
            location = self.patient_locations[0]

        alert_id = f'run{self.run_id}_alert1_{int(time.time()*1000) % 100000}'
        now_ns = self.get_clock().now().nanoseconds
        payload = {
            'alert_id': alert_id,
            'event_type': self.get_parameter('event_type').get_parameter_value().string_value,
            'patient_id': patient_id or location.get('name', 'patient_a'),
            'severity': location.get('severity', 'high') if location else 'high',
            'location': {'x': int(location['x']), 'y': int(location['y'])} if location else {'x': 4, 'y': 9},
            'run_id': self.run_id,
            'sequence': 0,
            't_alert_ns': now_ns,
        }

        msg = String()
        msg.data = json.dumps(payload)
        self.publisher.publish(msg)
        self._alert_sent = True
        self.get_logger().info(f'Published emergency alert from fusion: {msg.data}')

    @staticmethod
    def _parse(msg: String) -> dict:
        try:
            return json.loads(msg.data)
        except json.JSONDecodeError:
            return {'raw': msg.data}


def main(args=None):
    rclpy.init(args=args)
    node = AlertFusionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
