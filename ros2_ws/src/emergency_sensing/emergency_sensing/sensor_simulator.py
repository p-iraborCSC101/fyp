"""Simulated IoT sensors for emergency detection.

Publishes camera fall detection, heart-rate, and motion state readings using
scenario-defined patient locations. This provides a sensing layer that the
fusion node can consume.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import rclpy
import yaml
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


class SensorSimulator(Node):
    def __init__(self):
        super().__init__('sensor_simulator')

        self.declare_parameter('scenario_file', '')
        self.declare_parameter('run_id', 1)
        self.declare_parameter('seed', 42)
        self.declare_parameter('first_alert_delay_s', 4.0)
        self.declare_parameter('alert_period_s', 0.0)
        self.declare_parameter('baseline_hr', 82)
        self.declare_parameter('fall_hr', 140)

        self.camera_pub = self.create_publisher(String, '/sensor/camera_fall', 10)
        self.hr_pub = self.create_publisher(String, '/sensor/heart_rate', 10)
        self.motion_pub = self.create_publisher(String, '/sensor/motion_state', 10)
        self.image_pub = self.create_publisher(Image, '/sensor/camera_image', 10)

        self.run_id = int(self.get_parameter('run_id').get_parameter_value().integer_value)
        seed = int(self.get_parameter('seed').get_parameter_value().integer_value)
        self._rng = random.Random(seed + self.run_id)

        self.patient_locations = self._load_locations()
        self.sequence = 0
        self._first_alert_done = False

        delay = float(self.get_parameter('first_alert_delay_s').get_parameter_value().double_value)
        period = float(self.get_parameter('alert_period_s').get_parameter_value().double_value)
        self._period = period
        self._first_timer = self.create_timer(max(delay, 0.1), self._first_tick)

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

    def _first_tick(self) -> None:
        self._first_timer.cancel()
        self._publish_one()
        if self._period > 0.0:
            self.create_timer(self._period, self._publish_one)

    def _publish_one(self) -> None:
        if not self.patient_locations:
            self.get_logger().error('No patient locations available; nothing to publish')
            return

        location = self._rng.choice(self.patient_locations) if not self._first_alert_done \
            else self.patient_locations[self.sequence % len(self.patient_locations)]
        self._first_alert_done = True

        patient_id = location.get('name', f'patient_{self.sequence + 1}')
        now_ns = self.get_clock().now().nanoseconds

        camera_payload = {
            'patient_id': patient_id,
            'fall_detected': True,
            'location': {'x': int(location['x']), 'y': int(location['y'])},
            't_sensor_ns': now_ns,
        }
        hr_payload = {
            'patient_id': patient_id,
            'heart_rate_bpm': int(self.get_parameter('fall_hr').get_parameter_value().integer_value),
            't_sensor_ns': now_ns,
        }
        motion_payload = {
            'patient_id': patient_id,
            'motion_ok': False,
            't_sensor_ns': now_ns,
        }

        self._publish_json(self.camera_pub, camera_payload)
        self._publish_json(self.hr_pub, hr_payload)
        self._publish_json(self.motion_pub, motion_payload)
        self.image_pub.publish(self._build_image(patient_id, now_ns))
        self.sequence += 1

    def _build_image(self, patient_id: str, now_ns: int) -> Image:
        width = 160
        height = 120
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera'
        msg.height = height
        msg.width = width
        msg.encoding = 'mono8'
        msg.is_bigendian = False
        msg.step = width

        frame = bytearray(width * height)
        band = int((self.sequence * 7) % width)
        for y in range(height):
            row = y * width
            for x in range(width):
                value = 30
                if abs(x - band) < 3:
                    value = 210
                elif (x + y + self.sequence) % 29 == 0:
                    value = 120
                frame[row + x] = value

        label = f'{patient_id[-1] if patient_id else "?"}{(now_ns // 1_000_000) % 10}'
        self._stamp_label(frame, width, height, 4, 4, label)
        msg.data = bytes(frame)
        return msg

    @staticmethod
    def _stamp_label(frame: bytearray, width: int, height: int, x0: int, y0: int, text: str) -> None:
        glyphs = {
            '0': ["111", "101", "101", "101", "111"],
            '1': ["110", "010", "010", "010", "111"],
            '2': ["111", "001", "111", "100", "111"],
            '3': ["111", "001", "111", "001", "111"],
            '4': ["101", "101", "111", "001", "001"],
            '5': ["111", "100", "111", "001", "111"],
            '6': ["111", "100", "111", "101", "111"],
            '7': ["111", "001", "001", "010", "010"],
            '8': ["111", "101", "111", "101", "111"],
            '9': ["111", "101", "111", "001", "111"],
            'A': ["111", "101", "111", "101", "101"],
            'B': ["110", "101", "110", "101", "110"],
            'C': ["111", "100", "100", "100", "111"],
            '?': ["111", "001", "011", "000", "010"],
        }
        cursor = 0
        for ch in text:
            pattern = glyphs.get(ch, glyphs['?'])
            for dy, row in enumerate(pattern):
                for dx, bit in enumerate(row):
                    if bit != '1':
                        continue
                    x = x0 + cursor * 4 + dx
                    y = y0 + dy
                    if 0 <= x < width and 0 <= y < height:
                        frame[y * width + x] = 240
            cursor += 1

    @staticmethod
    def _publish_json(pub, payload: dict) -> None:
        msg = String()
        msg.data = json.dumps(payload)
        pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SensorSimulator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
