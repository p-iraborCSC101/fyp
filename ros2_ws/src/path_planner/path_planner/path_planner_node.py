"""Path planner node supporting A* and RRT*.

Reads its grid model + start pose + planner-mode parameters from a scenario
YAML.  On each /emergency_alert message it plans a route to the alert's goal
and publishes the result on /planned_route, including timing metadata that
the response logger uses to build per-trial rows.

It also listens on /replan_request: on a request it injects a transient
obstacle near the robot's current grid cell (a 'dynamic event'), increments
the replan counter for that alert, and re-plans.
"""

from __future__ import annotations

import heapq
import json
import math
import random
import time
from math import inf
from pathlib import Path

import rclpy
import yaml
from geometry_msgs.msg import PoseArray
from rclpy.node import Node
from std_msgs.msg import String


class PathPlannerNode(Node):
    def __init__(self):
        super().__init__('path_planner')

        self.declare_parameter('planner_mode', 'a_star')
        self.declare_parameter('scenario_file', '')
        self.declare_parameter('rrt_max_iterations', 2000)
        self.declare_parameter('rrt_step_size', 0.8)
        self.declare_parameter('rrt_goal_sample_rate', 0.25)
        self.declare_parameter('seed', 42)
        self.declare_parameter('world_to_grid_scale', 1.0)
        self.declare_parameter('world_to_grid_origin', [0.0, 0.0])
        self.declare_parameter('max_predictive_replans', 6)

        seed = int(self.get_parameter('seed').get_parameter_value().integer_value)
        self._rng = random.Random(seed)

        self.grid_width = 24
        self.grid_height = 14
        self.start = (2, 2)
        self.obstacles: set[tuple[int, int]] = set()
        self._event_obstacles: set[tuple[int, int]] = set()
        self._human_obstacles: set[tuple[int, int]] = set()
        self._max_predictive_replans = int(
            self.get_parameter('max_predictive_replans').get_parameter_value().integer_value
        )
        # Active planned path (grid cells) and the last human-on-path blockage we
        # replanned around — used to trigger predictive replans when a human steps
        # onto the current route, instead of waiting for the robot to physically stall.
        self._current_path_cells: set[tuple[int, int]] = set()
        self._last_block_sig: frozenset = frozenset()
        self._load_scenario()

        self.subscription = self.create_subscription(
            String, '/emergency_alert', self.alert_callback, 10
        )
        self.replan_sub = self.create_subscription(
            String, '/replan_request', self.replan_callback, 10
        )
        self.humans_sub = self.create_subscription(
            PoseArray, '/dynamic_obstacles', self.dynamic_obstacles_callback, 10
        )
        self.publisher = self.create_publisher(String, '/planned_route', 10)

        self._last_alert: dict | None = None
        self._replans_for_alert: dict[str, int] = {}

    # ------------------------------------------------------------------
    # scenario loading
    # ------------------------------------------------------------------
    def _load_scenario(self) -> None:
        scenario_file = self.get_parameter('scenario_file').get_parameter_value().string_value
        if not scenario_file:
            self.get_logger().warn('No scenario_file parameter; using empty obstacle grid.')
            return
        path = Path(scenario_file)
        if not path.exists():
            self.get_logger().error(f'Scenario file not found: {scenario_file}')
            return
        cfg = yaml.safe_load(path.read_text()) or {}
        grid_cfg = cfg.get('planner_grid', {})
        self.grid_width = int(grid_cfg.get('width', self.grid_width))
        self.grid_height = int(grid_cfg.get('height', self.grid_height))
        start = grid_cfg.get('start', [self.start[0], self.start[1]])
        self.start = (int(start[0]), int(start[1]))
        for cell in grid_cfg.get('obstacles', []):
            self.obstacles.add((int(cell[0]), int(cell[1])))
        self.get_logger().info(
            f'Loaded scenario: grid={self.grid_width}x{self.grid_height}, '
            f'start={self.start}, obstacles={len(self.obstacles)}'
        )

    # ------------------------------------------------------------------
    # alert / replan handlers
    # ------------------------------------------------------------------
    def alert_callback(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error('Received malformed alert payload')
            return

        location = payload.get('location', {})
        goal = (int(location.get('x', 8)), int(location.get('y', 8)))
        alert_id = str(payload.get('alert_id', f'alert_{int(time.time()*1000)}'))

        self._event_obstacles.clear()
        self._current_path_cells = set()
        self._last_block_sig = frozenset()
        self._replans_for_alert[alert_id] = 0
        self._last_alert = {
            'alert_id': alert_id,
            'goal': goal,
            'start': self.start,
            'reason': 'initial',
        }
        self._plan_and_publish()

    def replan_callback(self, msg: String) -> None:
        if self._last_alert is None:
            return
        try:
            payload = json.loads(msg.data) if msg.data else {}
        except json.JSONDecodeError:
            payload = {}

        robot_cell = payload.get('robot_cell')
        if robot_cell:
            cx, cy = int(robot_cell[0]), int(robot_cell[1])
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
                cell = (cx + dx, cy + dy)
                if 0 <= cell[0] < self.grid_width and 0 <= cell[1] < self.grid_height:
                    if cell != self._last_alert['goal']:
                        self._event_obstacles.add(cell)
                        break
        else:
            for _ in range(8):
                cell = (
                    self._rng.randrange(self.grid_width),
                    self._rng.randrange(self.grid_height),
                )
                if cell not in self.obstacles and cell != self._last_alert['goal']:
                    self._event_obstacles.add(cell)
                    break

        alert_id = self._last_alert['alert_id']
        self._replans_for_alert[alert_id] = self._replans_for_alert.get(alert_id, 0) + 1
        self._last_alert['reason'] = 'replan'
        self.get_logger().info(
            f'Replan #{self._replans_for_alert[alert_id]} for {alert_id}; '
            f'dynamic obstacles now: {len(self._event_obstacles) + len(self._human_obstacles)}'
        )
        self._plan_and_publish()

    def dynamic_obstacles_callback(self, msg: PoseArray) -> None:
        scale = self.get_parameter('world_to_grid_scale').get_parameter_value().double_value
        origin = self.get_parameter('world_to_grid_origin').get_parameter_value().double_array_value
        origin_x = float(origin[0]) if len(origin) >= 2 else 0.0
        origin_y = float(origin[1]) if len(origin) >= 2 else 0.0

        updated: set[tuple[int, int]] = set()
        for pose in msg.poses:
            gx = int(round((pose.position.x - origin_x) * scale))
            gy = int(round((pose.position.y - origin_y) * scale))
            if 0 <= gx < self.grid_width and 0 <= gy < self.grid_height:
                if (gx, gy) not in self.obstacles:
                    updated.add((gx, gy))

        self._human_obstacles = updated
        self._maybe_predictive_replan()

    def _maybe_predictive_replan(self) -> None:
        """Replan proactively when a human now occupies a cell on the active path.

        This makes the dynamic obstacle 'bite' without waiting for the robot to
        physically stall. Debounced by blockage signature and capped per alert so
        a hovering human can't trigger a replan storm.
        """
        if self._last_alert is None or not self._current_path_cells:
            return
        blocking = self._human_obstacles & self._current_path_cells
        blocking.discard(self._last_alert['goal'])
        blocking.discard(self.start)
        sig = frozenset(blocking)
        if not sig or sig == self._last_block_sig:
            return
        alert_id = self._last_alert['alert_id']
        if self._replans_for_alert.get(alert_id, 0) >= self._max_predictive_replans:
            return

        self._last_block_sig = sig
        self._replans_for_alert[alert_id] = self._replans_for_alert.get(alert_id, 0) + 1
        self._last_alert['reason'] = 'replan'
        self.get_logger().info(
            f'Predictive replan #{self._replans_for_alert[alert_id]} for {alert_id}: '
            f'human(s) on path at {sorted(sig)}'
        )
        self._plan_and_publish()

    # ------------------------------------------------------------------
    # planning + publish
    # ------------------------------------------------------------------
    def _plan_and_publish(self) -> None:
        assert self._last_alert is not None
        alert_id = self._last_alert['alert_id']
        goal = self._last_alert['goal']
        planner_mode = self.get_parameter('planner_mode').get_parameter_value().string_value

        t_start_ns = self.get_clock().now().nanoseconds
        cpu_t0 = time.perf_counter()
        if planner_mode == 'rrt_star':
            path = self.rrt_star(self.start, goal)
        else:
            path = self.a_star(self.start, goal)
        cpu_t1 = time.perf_counter()
        t_end_ns = self.get_clock().now().nanoseconds

        compute_ms = (cpu_t1 - cpu_t0) * 1000.0

        if path is None:
            self._current_path_cells = set()
            response = {
                'alert_id': alert_id,
                'status': 'failed',
                'reason': 'no_path_found',
                'planner': 'RRT*' if planner_mode == 'rrt_star' else 'A*',
                'start': {'x': self.start[0], 'y': self.start[1]},
                'goal': {'x': goal[0], 'y': goal[1]},
                't_plan_start_ns': t_start_ns,
                't_plan_end_ns': t_end_ns,
                'compute_time_ms': round(compute_ms, 4),
                'replans_so_far': self._replans_for_alert.get(alert_id, 0),
                'cause': self._last_alert['reason'],
            }
            self.get_logger().warning(f'No path found for goal {goal}')
        else:
            self._current_path_cells = set(path)
            response = {
                'alert_id': alert_id,
                'status': 'success',
                'planner': 'RRT*' if planner_mode == 'rrt_star' else 'A*',
                'start': {'x': self.start[0], 'y': self.start[1]},
                'goal': {'x': goal[0], 'y': goal[1]},
                'path': [{'x': x, 'y': y} for x, y in path],
                'path_length': self.path_length(path),
                't_plan_start_ns': t_start_ns,
                't_plan_end_ns': t_end_ns,
                'compute_time_ms': round(compute_ms, 4),
                'replans_so_far': self._replans_for_alert.get(alert_id, 0),
                'cause': self._last_alert['reason'],
            }
            self.get_logger().info(
                f'{response["planner"]} planned path length={response["path_length"]} '
                f'in {compute_ms:.2f} ms to {goal}'
            )

        out = String()
        out.data = json.dumps(response)
        self.publisher.publish(out)

    # ------------------------------------------------------------------
    # planners
    # ------------------------------------------------------------------
    def _is_blocked(self, cell: tuple[int, int]) -> bool:
        return cell in self.obstacles or cell in self._event_obstacles or cell in self._human_obstacles

    def neighbors(self, node: tuple[int, int]):
        x, y = node
        # 8-connectivity: cardinal + diagonal, for a fair length comparison with
        # the continuous-space RRT* (4-connectivity inflates A* paths by up to ~41%).
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.grid_width and 0 <= ny < self.grid_height):
                continue
            if self._is_blocked((nx, ny)):
                continue
            # No corner-cutting: a diagonal move requires both orthogonal cells free.
            if dx != 0 and dy != 0:
                if self._is_blocked((x + dx, y)) or self._is_blocked((x, y + dy)):
                    continue
            yield (nx, ny)

    @staticmethod
    def heuristic(node: tuple[int, int], goal: tuple[int, int]) -> float:
        # Octile distance: admissible heuristic for 8-connected grids with
        # unit/√2 move costs.
        dx = abs(node[0] - goal[0])
        dy = abs(node[1] - goal[1])
        return (dx + dy) + (math.sqrt(2) - 2.0) * min(dx, dy)

    @staticmethod
    def reconstruct_path(came_from: dict, current: tuple[int, int]) -> list[tuple[int, int]]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    @classmethod
    def path_length(cls, path: list[tuple[int, int]]) -> float:
        if len(path) < 2:
            return 0.0
        total = 0.0
        for idx in range(1, len(path)):
            total += cls._euclid(path[idx - 1], path[idx])
        return round(total, 4)

    def a_star(self, start, goal):
        if start == goal:
            return [start]
        if self._is_blocked(goal):
            return None

        open_heap: list[tuple[float, tuple[int, int]]] = []
        heapq.heappush(open_heap, (0, start))
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score = {start: 0}
        closed: set[tuple[int, int]] = set()

        while open_heap:
            _, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            if current == goal:
                return self.reconstruct_path(came_from, current)
            closed.add(current)

            for nb in self.neighbors(current):
                tentative_g = g_score[current] + self._euclid(current, nb)
                if tentative_g >= g_score.get(nb, inf):
                    continue
                came_from[nb] = current
                g_score[nb] = tentative_g
                f = tentative_g + self.heuristic(nb, goal)
                heapq.heappush(open_heap, (f, nb))
        return None

    def rrt_star(self, start, goal):
        max_iter = self.get_parameter('rrt_max_iterations').get_parameter_value().integer_value
        step = self.get_parameter('rrt_step_size').get_parameter_value().double_value
        goal_bias = self.get_parameter('rrt_goal_sample_rate').get_parameter_value().double_value

        if self._is_blocked(goal):
            return None

        start_node = {'pos': (float(start[0]), float(start[1])), 'parent': None, 'cost': 0.0}
        nodes = [start_node]

        for _ in range(int(max_iter)):
            if self._rng.random() < goal_bias:
                sample = (float(goal[0]), float(goal[1]))
            else:
                sample = (
                    self._rng.uniform(0, self.grid_width - 1),
                    self._rng.uniform(0, self.grid_height - 1),
                )

            nearest = min(nodes, key=lambda n: self._euclid(n['pos'], sample))
            new_pos = self._steer(nearest['pos'], sample, step)

            if not self._collision_free(nearest['pos'], new_pos):
                continue

            new_node = {
                'pos': new_pos,
                'parent': nearest,
                'cost': nearest['cost'] + self._euclid(nearest['pos'], new_pos),
            }

            near_nodes = self._near(nodes, new_pos)
            for nb in near_nodes:
                cost_via_nb = nb['cost'] + self._euclid(nb['pos'], new_pos)
                if cost_via_nb < new_node['cost'] and self._collision_free(nb['pos'], new_pos):
                    new_node['parent'] = nb
                    new_node['cost'] = cost_via_nb

            nodes.append(new_node)

            for nb in near_nodes:
                cost_via_new = new_node['cost'] + self._euclid(new_node['pos'], nb['pos'])
                if cost_via_new < nb['cost'] and self._collision_free(new_node['pos'], nb['pos']):
                    nb['parent'] = new_node
                    nb['cost'] = cost_via_new

            if self._euclid(new_pos, goal) <= step and self._collision_free(new_pos, goal):
                goal_node = {
                    'pos': (float(goal[0]), float(goal[1])),
                    'parent': new_node,
                    'cost': new_node['cost'] + self._euclid(new_pos, goal),
                }
                nodes.append(goal_node)
                return self._rrt_reconstruct(goal_node)
        return None

    # ------------------------------------------------------------------
    # rrt helpers
    # ------------------------------------------------------------------
    def _near(self, nodes, pos):
        if len(nodes) < 2:
            return nodes
        radius = min(4.0,
                     2.0 * math.sqrt(math.log(len(nodes)) / len(nodes))
                     * max(self.grid_width, self.grid_height))
        return [n for n in nodes if self._euclid(n['pos'], pos) <= radius]

    @staticmethod
    def _euclid(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    @staticmethod
    def _steer(from_pos, to_pos, step):
        d = math.hypot(to_pos[0] - from_pos[0], to_pos[1] - from_pos[1])
        if d <= step:
            return to_pos
        ratio = step / d
        return (from_pos[0] + ratio * (to_pos[0] - from_pos[0]),
                from_pos[1] + ratio * (to_pos[1] - from_pos[1]))

    def _collision_free(self, a, b):
        steps = max(int(self._euclid(a, b) / 0.5), 1)
        for i in range(steps + 1):
            r = i / steps
            x = a[0] + r * (b[0] - a[0])
            y = a[1] + r * (b[1] - a[1])
            cell = (int(round(x)), int(round(y)))
            if not (0 <= cell[0] < self.grid_width and 0 <= cell[1] < self.grid_height):
                return False
            if self._is_blocked(cell):
                return False
        return True

    @staticmethod
    def _rrt_reconstruct(node):
        path = []
        cur = node
        while cur is not None:
            path.append((int(round(cur['pos'][0])), int(round(cur['pos'][1]))))
            cur = cur['parent']
        path.reverse()
        compact = []
        for p in path:
            if not compact or compact[-1] != p:
                compact.append(p)
        return compact


def main(args=None):
    rclpy.init(args=args)
    node = PathPlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
