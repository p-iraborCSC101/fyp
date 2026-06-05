#!/usr/bin/env python3
"""Render a top-down plan view of a scenario for the write-up (Figure 4.2).

Reads a scenario YAML (planner grid, obstacles, patient locations, humans) and
draws the hospital grid: walls/beds, the robot start cell, the two patient
goals, and each human's looping walking path. Runs fully headless -- no ROS or
Gazebo required, just matplotlib + pyyaml.

Usage:
    python3 scripts/plot_world.py --scenario high_crowding
    python3 scripts/plot_world.py --scenario low_crowding --outdir data/figures
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")  # headless backend
import matplotlib.pyplot as plt
import yaml


def main() -> None:
    here = os.path.dirname(__file__)
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="high_crowding",
                   help="Scenario name (low_crowding | moderate_crowding | high_crowding).")
    p.add_argument("--scenarios-dir",
                   default=os.path.join(here, "..", "ros2_ws", "src",
                                        "emergency_launch", "scenarios"))
    p.add_argument("--outdir", default=os.path.join(here, "..", "data", "figures"))
    args = p.parse_args()

    path = os.path.abspath(os.path.join(args.scenarios_dir, f"{args.scenario}.yaml"))
    cfg = yaml.safe_load(open(path, encoding="utf-8"))
    grid = cfg["planner_grid"]
    W, H = int(grid["width"]), int(grid["height"])
    start = tuple(grid.get("start", [2, 2]))
    obstacles = [tuple(c) for c in grid.get("obstacles", [])]
    patients = cfg.get("patient_locations", [])
    humans = cfg.get("humans", [])

    fig, ax = plt.subplots(figsize=(8, 7))
    ax.set_xticks(range(W + 1))
    ax.set_yticks(range(H + 1))
    ax.grid(True, color="0.85", linewidth=0.5)

    # Walls + beds
    for (x, y) in obstacles:
        ax.add_patch(plt.Rectangle((x - 0.5, y - 0.5), 1, 1, color="0.4"))

    # Human walking paths
    for i, h in enumerate(humans):
        wps = h.get("waypoints", [])
        xs = [w[1] for w in wps]
        ys = [w[2] for w in wps]
        ax.plot(xs, ys, "--", color="tab:orange", linewidth=1.6,
                alpha=0.85, label="human paths" if i == 0 else None)
        ax.plot(xs[0], ys[0], "o", color="tab:orange", markersize=5)

    # Robot start (nurse station)
    ax.plot(start[0], start[1], "s", color="tab:blue", markersize=12,
            label="robot start (nurse station)")

    # Patient goals
    for j, pt in enumerate(patients):
        ax.plot(pt["x"], pt["y"], "*", color="tab:red", markersize=18,
                label="patient goal" if j == 0 else None)
        ax.annotate(pt.get("name", ""), (pt["x"], pt["y"]),
                    textcoords="offset points", xytext=(8, 6), fontsize=9)

    ax.set_xlim(-0.5, W - 0.5)
    ax.set_ylim(-0.5, H - 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("x (grid cells)")
    ax.set_ylabel("y (grid cells)")
    ax.set_title(f"Hospital plan view — {args.scenario} "
                 f"({len(humans)} humans, {W}x{H} grid)")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)

    os.makedirs(os.path.abspath(args.outdir), exist_ok=True)
    out = os.path.abspath(os.path.join(args.outdir, f"world_{args.scenario}.png"))
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
