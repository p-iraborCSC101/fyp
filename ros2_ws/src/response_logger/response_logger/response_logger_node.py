"""Response logger.

Subscribes to /emergency_alert, /planned_route, /robot_status and writes:

1. ~/fyp_ws/logs/response_events.csv  -- one row per event (raw audit log).
2. ~/fyp_ws/logs/trial_results.csv    -- one row per alert that completes
                                         (or hits arrival_timeout_s), with
                                         the columns the analysis scripts
                                         consume:

   alert_id, scenario, planner, run_id,
   t_alert_s, t_plan_recv_s, t_arrived_s,
   response_time_s, path_length_m, success,
   compute_time_ms, replans

3. ~/fyp_ws/logs/run_<run_id>.done    -- sentinel file the orchestrator
                                         polls for to know the trial finished.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


EVENT_FIELDS = ['timestamp', 'topic', 'payload']
TRIAL_FIELDS = [
    'alert_id', 'scenario', 'planner', 'run_id',
    'start_x', 'start_y', 'goal_x', 'goal_y',
    't_alert_s', 't_plan_recv_s', 't_arrived_s',
    'response_time_s', 'path_length_m', 'success',
    'compute_time_ms', 'replans',
]


class ResponseLoggerNode(Node):
    def __init__(self):
        super().__init__('response_logger')

        self.declare_parameter('scenario', 'unknown')
        self.declare_parameter('planner', 'unknown')
        self.declare_parameter('run_id', 0)
        self.declare_parameter('arrival_timeout_s', 90.0)
        self.declare_parameter('log_dir', str(Path.home() / 'fyp_ws' / 'logs'))

        self.scenario = self.get_parameter('scenario').get_parameter_value().string_value
        raw_planner = self.get_parameter('planner').get_parameter_value().string_value
        self.planner = {'a_star': 'A*', 'rrt_star': 'RRT*'}.get(raw_planner, raw_planner)
        self.run_id = int(self.get_parameter('run_id').get_parameter_value().integer_value)
        self.timeout_s = float(self.get_parameter('arrival_timeout_s').get_parameter_value().double_value)

        log_dir = Path(self.get_parameter('log_dir').get_parameter_value().string_value)
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = log_dir
        self.events_csv = log_dir / 'response_events.csv'
        self.trials_csv = log_dir / 'trial_results.csv'
        self.sentinel = log_dir / f'run_{self.run_id}.done'
        self._ensure_csv(self.events_csv, EVENT_FIELDS)
        self._ensure_csv(self.trials_csv, TRIAL_FIELDS)

        # alert_id -> partial row dict
        self._trials: dict[str, dict] = {}
        self._completed: set[str] = set()

        self.create_subscription(String, '/emergency_alert', self.on_alert, 10)
        self.create_subscription(String, '/planned_route', self.on_route, 10)
        self.create_subscription(String, '/robot_status', self.on_status, 10)

        self._timeout_timer = self.create_timer(1.0, self._check_timeouts)

    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_csv(path: Path, fields: list[str]) -> None:
        if path.exists():
            return
        with path.open('w', newline='') as h:
            writer = csv.DictWriter(h, fieldnames=fields)
            writer.writeheader()

    def _now_s(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def _append_event(self, topic: str, payload: dict) -> None:
        row = {
            'timestamp': f'{self._now_s():.3f}',
            'topic': topic,
            'payload': json.dumps(payload),
        }
        with self.events_csv.open('a', newline='') as h:
            csv.DictWriter(h, fieldnames=EVENT_FIELDS).writerow(row)

    def _flush_trial(self, alert_id: str) -> None:
        if alert_id in self._completed:
            return
        trial = self._trials.get(alert_id)
        if not trial:
            return
        row = {f: trial.get(f, '') for f in TRIAL_FIELDS}
        with self.trials_csv.open('a', newline='') as h:
            csv.DictWriter(h, fieldnames=TRIAL_FIELDS).writerow(row)
        self._completed.add(alert_id)
        self.get_logger().info(
            f'Trial logged: alert={alert_id} success={row["success"]} '
            f'response_time_s={row["response_time_s"]} replans={row["replans"]}'
        )
        # Drop sentinel so the orchestrator can advance
        try:
            self.sentinel.touch(exist_ok=True)
        except OSError as exc:
            self.get_logger().warn(f'Could not write sentinel {self.sentinel}: {exc}')

    # ------------------------------------------------------------------
    # subscribers
    # ------------------------------------------------------------------
    def on_alert(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {'raw': msg.data}
        self._append_event('emergency_alert', payload)

        alert_id = str(payload.get('alert_id', f'alert_{int(self._now_s()*1000)}'))
        location = payload.get('location') or {}
        self._trials.setdefault(alert_id, {
            'alert_id': alert_id,
            'scenario': self.scenario,
            'planner': self.planner,
            'run_id': self.run_id,
            'start_x': '',
            'start_y': '',
            'goal_x': location.get('x', ''),
            'goal_y': location.get('y', ''),
            't_alert_s': round(self._now_s(), 4),
            'replans': 0,
            'success': 0,
            'compute_time_ms': '',
            'path_length_m': '',
            't_plan_recv_s': '',
            't_arrived_s': '',
            'response_time_s': '',
        })

    def on_route(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {'raw': msg.data}
        self._append_event('planned_route', payload)

        alert_id = str(payload.get('alert_id', ''))
        if not alert_id:
            return
        trial = self._trials.setdefault(alert_id, {
            'alert_id': alert_id,
            'scenario': self.scenario,
            'planner': self.planner,
            'run_id': self.run_id,
            't_alert_s': round(self._now_s(), 4),
            'replans': 0,
            'success': 0,
        })
        trial['replans'] = max(
            int(payload.get('replans_so_far', 0)),
            int(trial.get('replans', 0)),
        )
        start = payload.get('start') or {}
        goal = payload.get('goal') or {}
        if 'x' in start:
            trial['start_x'] = start.get('x')
            trial['start_y'] = start.get('y')
        if 'x' in goal:
            trial['goal_x'] = goal.get('x')
            trial['goal_y'] = goal.get('y')
        if not trial.get('t_plan_recv_s'):
            trial['t_plan_recv_s'] = round(self._now_s(), 4)
        trial['compute_time_ms'] = (
            float(trial.get('compute_time_ms') or 0)
            + float(payload.get('compute_time_ms', 0))
        )
        trial['path_length_m'] = float(payload.get('path_length', trial.get('path_length_m') or 0))
        if payload.get('status') != 'success':
            trial['success'] = 0
            trial['t_arrived_s'] = round(self._now_s(), 4)
            trial['response_time_s'] = round(trial['t_arrived_s'] - trial['t_alert_s'], 4)
            self._flush_trial(alert_id)

    def on_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {'raw': msg.data}
        self._append_event('robot_status', payload)

        alert_id = str(payload.get('alert_id', ''))
        if not alert_id:
            return
        trial = self._trials.get(alert_id)
        if not trial:
            return

        trial['replans'] = max(
            int(payload.get('replans', 0)),
            int(trial.get('replans', 0)),
        )
        if payload.get('status') == 'arrived':
            trial['success'] = 1
            trial['t_arrived_s'] = round(self._now_s(), 4)
            trial['response_time_s'] = round(trial['t_arrived_s'] - trial['t_alert_s'], 4)
            self._flush_trial(alert_id)
        elif payload.get('status') == 'failed':
            trial['success'] = 0
            trial['t_arrived_s'] = round(self._now_s(), 4)
            trial['response_time_s'] = round(trial['t_arrived_s'] - trial['t_alert_s'], 4)
            self._flush_trial(alert_id)

    # ------------------------------------------------------------------
    # timeout sweep
    # ------------------------------------------------------------------
    def _check_timeouts(self) -> None:
        now_s = self._now_s()
        for alert_id, trial in list(self._trials.items()):
            if alert_id in self._completed:
                continue
            elapsed = now_s - float(trial.get('t_alert_s', now_s))
            if elapsed > self.timeout_s:
                trial['success'] = 0
                trial['t_arrived_s'] = round(now_s, 4)
                trial['response_time_s'] = round(elapsed, 4)
                self.get_logger().warn(
                    f'Trial {alert_id} timed out after {elapsed:.1f}s')
                self._flush_trial(alert_id)


def main(args=None):
    rclpy.init(args=args)
    node = ResponseLoggerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
