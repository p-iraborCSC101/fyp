#!/usr/bin/env python3
"""2D playback animation of a navigation run for the defence (Option 2).

Reconstructs a representative emergency-response run from the SAME scenario files
and the SAME A*/RRT* planning logic used in the ROS 2 / Gazebo experiment, and
renders it as a watchable side-by-side video (A* on the left, RRT* on the right)
through the crowded ward to the far patient.

IMPORTANT — describe this honestly in the defence:
  This is a 2D visualization of the navigation/replanning LOGIC, reconstructed
  from the deterministic planner and the scenario's human walking paths. It is
  NOT a pixel-replay of the Gazebo physics run (the per-trial logs store summary
  rows, not continuous trajectories). The physics results come from the headless
  Gazebo experiment; this clip is an illustration of what those runs look like.

Runs fully on macOS with no ROS/Gazebo — just matplotlib + pyyaml + numpy.

Usage:
    python3 scripts/animate_run.py                     # high_crowding, far patient
    python3 scripts/animate_run.py --scenario moderate_crowding --patient patient_b
    python3 scripts/animate_run.py --single rrt_star   # only RRT*, bigger frame
"""
from __future__ import annotations

import argparse
import heapq
import math
import os
import random

import matplotlib
matplotlib.use("Agg")  # headless: render straight to a file
import matplotlib.pyplot as plt
from matplotlib import animation
import yaml


# ----------------------------------------------------------------------------
# scenario
# ----------------------------------------------------------------------------
def load_scenario(scenarios_dir: str, scenario: str) -> dict:
    path = os.path.abspath(os.path.join(scenarios_dir, f"{scenario}.yaml"))
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def human_pos_at(waypoints: list[list[float]], t: float) -> tuple[float, float]:
    """Interpolate a human's position at time t, looping over the final timestamp."""
    if not waypoints:
        return (0.0, 0.0)
    if len(waypoints) == 1:
        return (waypoints[0][1], waypoints[0][2])
    period = waypoints[-1][0]
    if period <= 0:
        return (waypoints[0][1], waypoints[0][2])
    tm = t % period
    for i in range(1, len(waypoints)):
        t0, x0, y0 = waypoints[i - 1]
        t1, x1, y1 = waypoints[i]
        if t0 <= tm <= t1 and t1 > t0:
            r = (tm - t0) / (t1 - t0)
            return (x0 + r * (x1 - x0), y0 + r * (y1 - y0))
    return (waypoints[-1][1], waypoints[-1][2])


def human_cells_at(humans: list[dict], t: float) -> set[tuple[int, int]]:
    cells = set()
    for h in humans:
        x, y = human_pos_at(h.get("waypoints", []), t)
        cells.add((int(round(x)), int(round(y))))
    return cells


# ----------------------------------------------------------------------------
# planners (ported from path_planner_node.py so the visual matches the system)
# ----------------------------------------------------------------------------
class Planner:
    def __init__(self, W: int, H: int, static_obs: set[tuple[int, int]], seed: int = 42):
        self.W, self.H = W, H
        self.static = static_obs
        self.rng = random.Random(seed)

    def blocked(self, cell, dynamic):
        return cell in self.static or cell in dynamic

    # --- A* (8-connected, octile, no corner cutting) ---
    def neighbors(self, node, dynamic):
        x, y = node
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.W and 0 <= ny < self.H):
                continue
            if self.blocked((nx, ny), dynamic):
                continue
            if dx != 0 and dy != 0:
                if self.blocked((x + dx, y), dynamic) or self.blocked((x, y + dy), dynamic):
                    continue
            yield (nx, ny)

    @staticmethod
    def octile(a, b):
        dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
        return (dx + dy) + (math.sqrt(2) - 2.0) * min(dx, dy)

    @staticmethod
    def euclid(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def a_star(self, start, goal, dynamic):
        if start == goal:
            return [start]
        if self.blocked(goal, dynamic):
            return None
        open_heap = [(0, start)]
        came, g, closed = {}, {start: 0}, set()
        while open_heap:
            _, cur = heapq.heappop(open_heap)
            if cur in closed:
                continue
            if cur == goal:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                return path[::-1]
            closed.add(cur)
            for nb in self.neighbors(cur, dynamic):
                tg = g[cur] + self.euclid(cur, nb)
                if tg >= g.get(nb, math.inf):
                    continue
                came[nb] = cur
                g[nb] = tg
                heapq.heappush(open_heap, (tg + self.octile(nb, goal), nb))
        return None

    # --- RRT* (step 0.8, 25% goal bias, shrinking rewire radius) ---
    def _collision_free(self, a, b, dynamic):
        steps = max(int(self.euclid(a, b) / 0.5), 1)
        for i in range(steps + 1):
            r = i / steps
            x = a[0] + r * (b[0] - a[0])
            y = a[1] + r * (b[1] - a[1])
            cell = (int(round(x)), int(round(y)))
            if not (0 <= cell[0] < self.W and 0 <= cell[1] < self.H):
                return False
            if self.blocked(cell, dynamic):
                return False
        return True

    @staticmethod
    def _steer(frm, to, step):
        d = math.hypot(to[0] - frm[0], to[1] - frm[1])
        if d <= step:
            return to
        r = step / d
        return (frm[0] + r * (to[0] - frm[0]), frm[1] + r * (to[1] - frm[1]))

    def rrt_star(self, start, goal, dynamic, max_iter=1200, step=0.8, goal_bias=0.25):
        if self.blocked(goal, dynamic):
            return None
        start_node = {"pos": (float(start[0]), float(start[1])), "parent": None, "cost": 0.0}
        nodes = [start_node]
        for _ in range(max_iter):
            if self.rng.random() < goal_bias:
                sample = (float(goal[0]), float(goal[1]))
            else:
                sample = (self.rng.uniform(0, self.W - 1), self.rng.uniform(0, self.H - 1))
            nearest = min(nodes, key=lambda n: self.euclid(n["pos"], sample))
            new_pos = self._steer(nearest["pos"], sample, step)
            if not self._collision_free(nearest["pos"], new_pos, dynamic):
                continue
            new_node = {"pos": new_pos, "parent": nearest,
                        "cost": nearest["cost"] + self.euclid(nearest["pos"], new_pos)}
            radius = min(4.0, 2.0 * math.sqrt(math.log(len(nodes) + 1) / (len(nodes) + 1))
                         * max(self.W, self.H))
            near = [n for n in nodes if self.euclid(n["pos"], new_pos) <= radius]
            for nb in near:
                c = nb["cost"] + self.euclid(nb["pos"], new_pos)
                if c < new_node["cost"] and self._collision_free(nb["pos"], new_pos, dynamic):
                    new_node["parent"], new_node["cost"] = nb, c
            nodes.append(new_node)
            for nb in near:
                c = new_node["cost"] + self.euclid(new_node["pos"], nb["pos"])
                if c < nb["cost"] and self._collision_free(new_node["pos"], nb["pos"], dynamic):
                    nb["parent"], nb["cost"] = new_node, c
            if self.euclid(new_pos, goal) <= step and self._collision_free(new_pos, goal, dynamic):
                node = {"pos": (float(goal[0]), float(goal[1])), "parent": new_node,
                        "cost": new_node["cost"] + self.euclid(new_pos, goal)}
                path = []
                while node is not None:
                    path.append((int(round(node["pos"][0])), int(round(node["pos"][1]))))
                    node = node["parent"]
                path.reverse()
                compact = []
                for p in path:
                    if not compact or compact[-1] != p:
                        compact.append(p)
                return compact
        return None

    def plan(self, mode, start, goal, dynamic):
        return self.rrt_star(start, goal, dynamic) if mode == "rrt_star" \
            else self.a_star(start, goal, dynamic)


# ----------------------------------------------------------------------------
# per-robot simulation
# ----------------------------------------------------------------------------
class RobotSim:
    SPEED = 0.45           # m/s (grid cell = 1 m), matches max_linear_speed
    TOL = 0.4              # waypoint tolerance
    MAX_REPLANS = 6        # matches max_replans_per_alert
    DEADLINE = 60.0        # clinical deadline (s)

    def __init__(self, mode, planner, start, goal):
        self.mode = mode
        self.planner = planner
        self.pos = (float(start[0]), float(start[1]))
        self.start = (int(start[0]), int(start[1]))
        self.goal = (int(goal[0]), int(goal[1]))
        self.path = planner.plan(mode, self.start, self.goal, set()) or [self.start]
        self.idx = self._nearest_idx()
        self.replans = 0
        self.t = 0.0
        self.arrived = False
        self.failed = False
        self.status = "driving"
        self._last_sig = frozenset()
        self._stall_t = 0.0

    def _nearest_idx(self):
        return min(range(len(self.path)),
                   key=lambda i: math.hypot(self.path[i][0] - self.pos[0],
                                            self.path[i][1] - self.pos[1]))

    def cur_cell(self):
        return (int(round(self.pos[0])), int(round(self.pos[1])))

    def step(self, dt, human_cells):
        if self.arrived or self.failed:
            return
        self.t += dt
        if self.t > self.DEADLINE and not self.arrived:
            self.failed = True
            self.status = "FAILED (deadline)"
            return

        # path cells ahead of the robot
        ahead = set(self.path[self.idx:])
        blocking = (human_cells & ahead) - {self.goal, self.start}
        sig = frozenset(blocking)
        need_replan = bool(blocking) and sig != self._last_sig

        if need_replan and self.replans < self.MAX_REPLANS:
            self._last_sig = sig
            self.replans += 1
            new_path = self.planner.plan(self.mode, self.cur_cell(), self.goal, human_cells)
            if new_path and len(new_path) > 1:
                self.path = new_path
                self.idx = self._nearest_idx()
                self.status = f"replan #{self.replans}"
            else:
                self.status = f"blocked (replan #{self.replans})"
                self._stall_t += dt
                return  # no route right now -> wait in place (visible stall)

        # also stall if the immediate next cell is occupied
        if self.idx < len(self.path):
            nxt = self.path[min(self.idx, len(self.path) - 1)]
            if nxt in human_cells and nxt != self.goal:
                self._stall_t += dt
                self.status = "waiting (blocked)"
                if self._stall_t > 3.0 and self.replans >= self.MAX_REPLANS:
                    self.failed = True
                    self.status = "FAILED (stuck)"
                return

        self._stall_t = 0.0
        # advance toward current waypoint
        remaining = self.SPEED * dt
        while remaining > 0 and self.idx < len(self.path):
            tx, ty = self.path[self.idx]
            dx, dy = tx - self.pos[0], ty - self.pos[1]
            d = math.hypot(dx, dy)
            if d <= self.TOL:
                self.idx += 1
                continue
            stepd = min(remaining, d)
            self.pos = (self.pos[0] + stepd * dx / d, self.pos[1] + stepd * dy / d)
            remaining -= stepd
            if self.planner.euclid(self.pos, self.goal) <= self.TOL:
                self.idx = len(self.path)
        if self.idx >= len(self.path) or self.planner.euclid(self.pos, self.goal) <= self.TOL:
            self.arrived = True
            self.status = f"ARRIVED ({self.t:.1f}s)"


# ----------------------------------------------------------------------------
# build + render
# ----------------------------------------------------------------------------
def simulate(cfg, goal, modes, dt=0.2, horizon=75.0):
    grid = cfg["planner_grid"]
    W, H = int(grid["width"]), int(grid["height"])
    start = tuple(grid.get("start", [2, 2]))
    static = {tuple(c) for c in grid.get("obstacles", [])}
    humans = cfg.get("humans", [])

    robots = {m: RobotSim(m, Planner(W, H, static, seed=42 + i), start, goal)
              for i, m in enumerate(modes)}
    frames = []
    t = 0.0
    while t <= horizon:
        hc = human_cells_at(humans, t)
        hpos = [human_pos_at(h.get("waypoints", []), t) for h in humans]
        for r in robots.values():
            r.step(dt, hc)
        frames.append({
            "t": t,
            "humans": hpos,
            "robots": {m: {"pos": r.pos, "path": list(r.path[r.idx:]),
                           "status": r.status, "replans": r.replans,
                           "arrived": r.arrived, "failed": r.failed}
                       for m, r in robots.items()},
        })
        if all(r.arrived or r.failed for r in robots.values()):
            # let it linger a moment on the final frame
            for _ in range(10):
                frames.append(frames[-1])
            break
        t += dt
    return W, H, start, static, frames


def render(cfg, scenario, goal_name, goal, W, H, static, frames, modes, outdir):
    pretty = {"a_star": "A* (deterministic)", "rrt_star": "RRT* (stochastic)"}
    fig, axes = plt.subplots(1, len(modes), figsize=(7.5 * len(modes), 7.2), squeeze=False)
    axes = axes[0]

    def draw_static(ax, title):
        ax.clear()
        for (x, y) in static:
            ax.add_patch(plt.Rectangle((x - 0.5, y - 0.5), 1, 1, color="0.45"))
        ax.plot(frames[0]["robots"][modes[0]]["pos"][0] if False else 0, 0)  # noop
        ax.set_xlim(-0.5, W - 0.5)
        ax.set_ylim(-0.5, H - 0.5)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, fontsize=12)

    def update(fi):
        fr = frames[fi]
        for ax, m in zip(axes, modes):
            draw_static(ax, pretty.get(m, m))
            # remaining planned path
            p = fr["robots"][m]["path"]
            if len(p) >= 2:
                ax.plot([c[0] for c in p], [c[1] for c in p], "-",
                        color="tab:green", lw=2.0, alpha=0.8)
            # goal
            ax.plot(goal[0], goal[1], "*", color="tab:red", markersize=22,
                    markeredgecolor="k", zorder=5)
            # humans
            hx = [h[0] for h in fr["humans"]]
            hy = [h[1] for h in fr["humans"]]
            ax.scatter(hx, hy, s=160, color="tab:orange", edgecolors="k",
                       zorder=6, label="people")
            # robot
            rp = fr["robots"][m]["pos"]
            col = "tab:blue"
            if fr["robots"][m]["failed"]:
                col = "crimson"
            elif fr["robots"][m]["arrived"]:
                col = "green"
            ax.scatter([rp[0]], [rp[1]], s=240, marker="s", color=col,
                       edgecolors="k", zorder=7, label="robot")
            st = fr["robots"][m]["status"]
            ax.text(0.02, 0.98, f"t = {fr['t']:.1f}s   replans: {fr['robots'][m]['replans']}",
                    transform=ax.transAxes, va="top", fontsize=11,
                    bbox=dict(boxstyle="round", fc="white", alpha=0.85))
            ax.text(0.02, 0.04, st, transform=ax.transAxes, va="bottom", fontsize=12,
                    color=col, weight="bold",
                    bbox=dict(boxstyle="round", fc="white", alpha=0.85))
        fig.suptitle(f"Emergency response — {scenario.replace('_', ' ')}, "
                     f"{goal_name} (far patient)   |   robot=blue square, "
                     f"people=orange, goal=red star",
                     fontsize=13)
        return []

    anim = animation.FuncAnimation(fig, update, frames=len(frames), interval=120, blit=False)
    os.makedirs(os.path.abspath(outdir), exist_ok=True)
    base = os.path.join(os.path.abspath(outdir), f"run_{scenario}_{goal_name}")

    saved = []
    # MP4 (best for slides) if ffmpeg present, else fall back to GIF
    try:
        anim.save(base + ".mp4", writer=animation.FFMpegWriter(fps=10, bitrate=2400))
        saved.append(base + ".mp4")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] mp4 save failed ({exc}); writing GIF instead")
    try:
        anim.save(base + ".gif", writer=animation.PillowWriter(fps=10))
        saved.append(base + ".gif")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] gif save failed: {exc}")
    plt.close(fig)
    return saved


def main():
    here = os.path.dirname(__file__)
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="high_crowding")
    ap.add_argument("--patient", default="patient_b", help="goal patient name")
    ap.add_argument("--single", default=None, choices=["a_star", "rrt_star"],
                    help="render only one planner instead of side-by-side")
    ap.add_argument("--scenarios-dir",
                    default=os.path.join(here, "..", "ros2_ws", "src",
                                         "emergency_launch", "scenarios"))
    ap.add_argument("--outdir", default=os.path.join(here, "..", "data", "figures"))
    args = ap.parse_args()

    cfg = load_scenario(args.scenarios_dir, args.scenario)
    patient = next((p for p in cfg.get("patient_locations", [])
                    if p.get("name") == args.patient), None)
    if patient is None:
        patient = cfg["patient_locations"][-1]
    goal = (int(patient["x"]), int(patient["y"]))
    modes = [args.single] if args.single else ["a_star", "rrt_star"]

    print(f"Simulating {args.scenario} -> {patient.get('name')} {goal} for {modes} ...")
    W, H, start, static, frames = simulate(cfg, goal, modes)
    print(f"  {len(frames)} frames; rendering ...")
    saved = render(cfg, args.scenario, patient.get("name", "goal"),
                   goal, W, H, static, frames, modes, args.outdir)
    for s in saved:
        print(f"Wrote {s}")
    print("\nNOTE: this is a 2D visualization of the navigation LOGIC reconstructed from the\n"
          "planner + scenario human paths — NOT a pixel-replay of the Gazebo physics run.")


if __name__ == "__main__":
    main()
