#!/usr/bin/env python3
"""Create chapter-ready figures from results_summary.csv.

Works with either the pooled summary (scenario, planner) or the per-goal summary
produced by `evaluate_metrics.py --by-goal` (adds a `goal` column). For a per-goal
summary each metric figure gets one subplot per goal (patient_a / patient_b), so
the short and long routes are not averaged together.

Plots the metrics that actually carry signal: path length, response time, compute
time, and replans -- each as grouped A*/RRT* bars across crowding levels, with
std error bars.
"""

from __future__ import annotations

import argparse
import csv
import os

import matplotlib.pyplot as plt

SCENARIOS = ["low_crowding", "moderate_crowding", "high_crowding"]
PLANNERS = ["A*", "RRT*"]

# (mean_col, std_col, y-label, filename-stem)
METRICS = [
    ("path_length_mean_m", "path_length_std_m", "Path Length (m)", "path_length"),
    ("response_time_mean_s", "response_time_std_s", "Response Time (s)", "response_time"),
    ("compute_time_mean_ms", "compute_time_std_ms", "Compute Time (ms)", "compute_time"),
    ("replans_mean", "replans_std", "Replans", "replans"),
    ("success_rate_pct", "success_rate_std", "Success Rate (%)", "success_rate"),
]


def load_summary(path: str) -> list[dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(row: dict, col: str) -> float:
    try:
        return float(row.get(col, 0.0))
    except (ValueError, TypeError):
        return 0.0


def find(rows, scenario, planner, goal=None):
    for r in rows:
        if r["scenario"] == scenario and r["planner"] == planner:
            if goal is None or r.get("goal") == goal:
                return r
    return None


def draw_group(ax, rows, mean_col, std_col, ylabel, goal=None):
    x = list(range(len(SCENARIOS)))
    width = 0.35
    for i, planner in enumerate(PLANNERS):
        means = []
        for s in SCENARIOS:
            r = find(rows, s, planner, goal)
            means.append(fnum(r, mean_col) if r else 0.0)
        offset = (i - 0.5) * width
        xs = [xi + offset for xi in x]
        ax.bar(xs, means, width=width, label=planner)
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_crowding", "") for s in SCENARIOS])
    ax.set_xlabel("Crowding")
    ax.set_ylabel(ylabel)
    # Bar charts must start at zero.
    ax.set_ylim(bottom=0)
    ax.legend()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot summary metrics by planner/scenario(/goal).")
    parser.add_argument("--infile", type=str, default="../data/processed/results_summary.csv")
    parser.add_argument("--outdir", type=str, default="../data/figures")
    args = parser.parse_args()

    in_path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.infile))
    outdir = os.path.abspath(os.path.join(os.path.dirname(__file__), args.outdir))
    os.makedirs(outdir, exist_ok=True)

    rows = load_summary(in_path)
    goals = sorted({r["goal"] for r in rows if r.get("goal")}) if any("goal" in r for r in rows) else []

    for mean_col, std_col, ylabel, stem in METRICS:
        if goals:
            fig, axes = plt.subplots(1, len(goals), figsize=(5.5 * len(goals), 4.5), squeeze=False)
            for ax, goal in zip(axes[0], goals):
                draw_group(ax, rows, mean_col, std_col, ylabel, goal=goal)
                ax.set_title(f"{ylabel} - {goal}")
        else:
            fig, ax = plt.subplots(figsize=(8, 4.5))
            draw_group(ax, rows, mean_col, std_col, ylabel)
            ax.set_title(f"{ylabel} by Crowding")
        fig.tight_layout()
        out = os.path.join(outdir, f"{stem}_comparison.png")
        fig.savefig(out, dpi=180)
        plt.close(fig)
        print(f"Saved {out}")


if __name__ == "__main__":
    main()
