"""Simulated IoT emergency publisher.

Reads patient locations from a scenario YAML, picks one based on the
trial seed, and publishes a single /emergency_alert after `first_alert_delay_s`.
This single-shot behaviour is what the orchestrator needs: one alert per
launch invocation, deterministic per (run_id, seed).

Each alert payload includes a stable alert_id that flows through the planner
and logger so all downstream rows can be joined into one trial.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import rclpy
import yaml
from rclpy.node import Node
from std_msgs.msg import String


class EmergencyPublisher(Node):
    def __init__(self):
        super().__init__('emergency_publisher')

        self.declare_parameter('scenario_file', '')
        self.declare_parameter('run_id', 1)
        self.declare_parameter('seed', 42)
        self.declare_parameter('first_alert_delay_s', 4.0)
        self.declare_parameter('alert_period_s', 0.0)  # 0 = single-shot
        self.declare_parameter('event_type', 'fall_detected')

        self.publisher = self.create_publisher(String, '/emergency_alert', 10)

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

    # ------------------------------------------------------------------
    def _load_locations(self) -> list[dict]:
        scenario_file = self.get_parameter('scenario_file').get_parameter_value().string_value
        if not scenario_file:
            self.get_logger().warn('No scenario_file parameter; falling back to defaults.')
            return [
                {'name': 'patient_a', 'x': 4, 'y': 9},
                {'name': 'patient_b', 'x': 12, 'y': 9},
                {'name': 'patient_c', 'x': 20, 'y': 9},
            ]
        path = Path(scenario_file)
        if not path.exists():
            self.get_logger().error(f'Scenario file not found: {scenario_file}')
            return []
        cfg = yaml.safe_load(path.read_text()) or {}
        return list(cfg.get('patient_locations', []))

    # ------------------------------------------------------------------
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

        alert_id = f'run{self.run_id}_alert{self.sequence + 1}_{int(time.time()*1000) % 100000}'
        now_ns = self.get_clock().now().nanoseconds
        payload = {
            'alert_id': alert_id,
            'event_type': self.get_parameter('event_type').get_parameter_value().string_value,
            'patient_id': location.get('name', f'patient_{self.sequence + 1}'),
            'severity': location.get('severity', 'high'),
            'location': {'x': int(location['x']), 'y': int(location['y'])},
            'run_id': self.run_id,
            'sequence': self.sequence,
            't_alert_ns': now_ns,
        }

        msg = String()
        msg.data = json.dumps(payload)
        self.publisher.publish(msg)
        self.get_logger().info(f'Published emergency alert: {msg.data}')
        self.sequence += 1


def main(args=None):
    rclpy.init(args=args)
    node = EmergencyPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
