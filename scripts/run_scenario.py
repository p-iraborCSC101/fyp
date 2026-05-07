#!/usr/bin/env python3
"""Run synthetic emergency-response scenarios comparing A* and RRT*.

This script provides an immediate, ROS-free baseline pipeline so the project can
start generating reproducible evidence while ROS2/Gazebo setup is in progress.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import time
from dataclasses import dataclass
from heapq import heappop, heappush


@dataclass(frozen=True)
class Point:
    x: int
    y: int


SCENARIOS = {
    "low_crowding": {"obs_ratio": 0.05, "dynamic_events": 2},
    "moderate_crowding": {"obs_ratio": 0.10, "dynamic_events": 4},
    "high_crowding": {"obs_ratio": 0.16, "dynamic_events": 7},
}


def make_grid(size: int, obs_ratio: float, rng: random.Random) -> list[list[int]]:
    grid = [[0 for _ in range(size)] for _ in range(size)]
    obstacle_count = int(size * size * obs_ratio)
    for _ in range(obstacle_count):
        x = rng.randrange(size)
        y = rng.randrange(size)
        grid[y][x] = 1
    return grid


def neighbors(p: Point, size: int) -> list[Point]:
    cand = [(p.x + 1, p.y), (p.x - 1, p.y), (p.x, p.y + 1), (p.x, p.y - 1)]
    out = []
    for x, y in cand:
        if 0 <= x < size and 0 <= y < size:
            out.append(Point(x, y))
    return out


def heuristic(a: Point, b: Point) -> float:
    return abs(a.x - b.x) + abs(a.y - b.y)


def reconstruct(prev: dict[Point, Point], cur: Point) -> list[Point]:
    path = [cur]
    while cur in prev:
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return path


def astar(grid: list[list[int]], start: Point, goal: Point) -> list[Point]:
    size = len(grid)
    open_set = []
    heappush(open_set, (0, start.x, start.y, start))
    g = {start: 0.0}
    prev: dict[Point, Point] = {}

    while open_set:
        _, _, _, cur = heappop(open_set)
        if cur == goal:
            return reconstruct(prev, cur)
        for nxt in neighbors(cur, size):
            if grid[nxt.y][nxt.x] == 1:
                continue
            cand = g[cur] + 1.0
            if cand < g.get(nxt, float("inf")):
                prev[nxt] = cur
                g[nxt] = cand
                f = cand + heuristic(nxt, goal)
                heappush(open_set, (f, nxt.x, nxt.y, nxt))
    return []


def line_cells(a: Point, b: Point) -> list[Point]:
    cells = []
    x0, y0 = a.x, a.y
    x1, y1 = b.x, b.y
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        cells.append(Point(x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return cells


def collision_free(grid: list[list[int]], a: Point, b: Point) -> bool:
    for c in line_cells(a, b):
        if grid[c.y][c.x] == 1:
            return False
    return True


def euclid(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def rrt_star(grid: list[list[int]], start: Point, goal: Point, rng: random.Random, iterations: int = 700, step: int = 2, goal_bias: float = 0.18) -> list[Point]:
    size = len(grid)
    nodes = [start]
    parent: dict[Point, Point] = {}
    cost = {start: 0.0}

    def nearest(q: Point) -> Point:
        return min(nodes, key=lambda n: euclid(n, q))

    def steer(a: Point, b: Point) -> Point:
        dist = euclid(a, b)
        if dist <= step:
            return b
        nx = int(round(a.x + (b.x - a.x) * (step / dist)))
        ny = int(round(a.y + (b.y - a.y) * (step / dist)))
        nx = max(0, min(size - 1, nx))
        ny = max(0, min(size - 1, ny))
        return Point(nx, ny)

    goal_node = None

    for _ in range(iterations):
        q_rand = goal if rng.random() < goal_bias else Point(rng.randrange(size), rng.randrange(size))
        if grid[q_rand.y][q_rand.x] == 1:
            continue
        q_near = nearest(q_rand)
        q_new = steer(q_near, q_rand)
        if grid[q_new.y][q_new.x] == 1 or not collision_free(grid, q_near, q_new):
            continue

        nodes.append(q_new)
        parent[q_new] = q_near
        cost[q_new] = cost[q_near] + euclid(q_near, q_new)

        # Local rewiring radius scaled for small grid worlds.
        radius = 3
        near_nodes = [n for n in nodes if euclid(n, q_new) <= radius and n != q_new]
        for n in near_nodes:
            if collision_free(grid, n, q_new):
                cand = cost[n] + euclid(n, q_new)
                if cand < cost[q_new]:
                    parent[q_new] = n
                    cost[q_new] = cand

        # Skip rewiring existing near nodes through q_new to avoid accidental
        # parent cycles in this lightweight baseline implementation.

        if euclid(q_new, goal) <= 2 and collision_free(grid, q_new, goal):
            goal_node = goal
            parent[goal] = q_new
            break

    if goal_node is None and goal in parent:
        goal_node = goal
    if goal_node is None:
        return []

    path = [goal]
    cur = goal
    visited = {goal}
    while cur in parent:
        cur = parent[cur]
        if cur in visited:
            return []
        visited.add(cur)
        path.append(cur)
        if cur == start:
            break
    path.reverse()
    return path if path and path[0] == start else []


def path_length(path: list[Point]) -> float:
    if len(path) < 2:
        return 0.0
    s = 0.0
    for i in range(1, len(path)):
        s += euclid(path[i - 1], path[i])
    return s


def pick_start_goal(grid: list[list[int]], rng: random.Random) -> tuple[Point, Point]:
    size = len(grid)
    while True:
        s = Point(rng.randrange(size), rng.randrange(size))
        g = Point(rng.randrange(size), rng.randrange(size))
        if s != g and grid[s.y][s.x] == 0 and grid[g.y][g.x] == 0 and heuristic(s, g) > size // 2:
            return s, g


def maybe_add_dynamic_obstacles(grid: list[list[int]], path: list[Point], events: int, rng: random.Random) -> int:
    if not path:
        return 0
    size = len(grid)
    replans = 0
    for _ in range(events):
        if len(path) < 4:
            break
        k = rng.randrange(1, len(path) - 1)
        p = path[k]
        if (0 < p.x < size - 1) and (0 < p.y < size - 1):
            grid[p.y][p.x] = 1
            replans += 1
    return replans


def run_once(planner: str, scenario: str, run_id: int, base_seed: int, size: int) -> dict[str, float | int | str]:
    cfg = SCENARIOS[scenario]
    rng = random.Random(base_seed + run_id)
    grid = make_grid(size=size, obs_ratio=cfg["obs_ratio"], rng=rng)
    start, goal = pick_start_goal(grid, rng)

    # Keep scenarios solvable at baseline so comparisons are informative.
    for _ in range(30):
        if astar(grid, start, goal):
            break
        grid = make_grid(size=size, obs_ratio=cfg["obs_ratio"], rng=rng)
        start, goal = pick_start_goal(grid, rng)

    emergency_detect_ms = rng.uniform(50, 200)

    t0 = time.perf_counter()
    if planner == "A*":
        path = astar(grid, start, goal)
    elif planner == "RRT*":
        path = rrt_star(grid, start, goal, rng=rng)
    else:
        raise ValueError("planner must be A* or RRT*")
    t1 = time.perf_counter()

    compute_ms = (t1 - t0) * 1000.0
    success = 1 if path else 0

    replans = 0
    if success:
        replans = maybe_add_dynamic_obstacles(grid, path, cfg["dynamic_events"], rng)
        for _ in range(replans):
            if planner == "A*":
                path = astar(grid, start, goal)
            else:
                path = rrt_star(grid, start, goal, rng=rng)
            if not path:
                success = 0
                break

    p_len = path_length(path) if success else 0.0
    travel_speed = rng.uniform(0.8, 1.2)
    travel_time_s = (p_len / max(travel_speed, 0.1)) if success else 999.0
    response_time_s = (emergency_detect_ms / 1000.0) + (compute_ms / 1000.0) + travel_time_s

    return {
        "scenario": scenario,
        "planner": planner,
        "run": run_id,
        "response_time_s": round(response_time_s, 4),
        "path_length_m": round(p_len, 4),
        "success": success,
        "compute_time_ms": round(compute_ms, 4),
        "replans": replans,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic emergency scenarios for A* and RRT*.")
    parser.add_argument("--runs", type=int, default=30, help="Runs per planner per scenario.")
    parser.add_argument("--size", type=int, default=28, help="Grid size (NxN).")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed.")
    parser.add_argument("--out", type=str, default="../data/raw_logs/experiment_runs.csv", help="Output CSV path.")
    args = parser.parse_args()

    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.out))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    rows = []
    for scenario in SCENARIOS:
        for planner in ("A*", "RRT*"):
            for run_id in range(1, args.runs + 1):
                rows.append(run_once(planner, scenario, run_id, args.seed, args.size))

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario",
                "planner",
                "run",
                "response_time_s",
                "path_length_m",
                "success",
                "compute_time_ms",
                "replans",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
