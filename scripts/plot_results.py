#!/usr/bin/env python3
"""Create basic figures for Chapter 5 from results_summary.csv."""

from __future__ import annotations

import argparse
import csv
import os

import matplotlib.pyplot as plt


def load_summary(path: str) -> list[dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot response time and success rate by planner/scenario.")
    parser.add_argument("--infile", type=str, default="../data/processed/results_summary.csv")
    parser.add_argument("--outdir", type=str, default="../data/figures")
    args = parser.parse_args()

    in_path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.infile))
    outdir = os.path.abspath(os.path.join(os.path.dirname(__file__), args.outdir))
    os.makedirs(outdir, exist_ok=True)

    rows = load_summary(in_path)
    scenarios = ["low_crowding", "moderate_crowding", "high_crowding"]

    for metric, ylabel, fname in [
        ("response_time_mean_s", "Mean Response Time (s)", "response_time_comparison.png"),
        ("success_rate_pct", "Success Rate (%)", "success_rate_comparison.png"),
    ]:
        x = list(range(len(scenarios)))
        a_vals = []
        r_vals = []
        for s in scenarios:
            a = next((r for r in rows if r["scenario"] == s and r["planner"] == "A*"), None)
            rr = next((r for r in rows if r["scenario"] == s and r["planner"] == "RRT*"), None)
            a_vals.append(float(a[metric]) if a else 0.0)
            r_vals.append(float(rr[metric]) if rr else 0.0)

        width = 0.35
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar([i - width / 2 for i in x], a_vals, width=width, label="A*")
        ax.bar([i + width / 2 for i in x], r_vals, width=width, label="RRT*")
        ax.set_xticks(x)
        ax.set_xticklabels([s.replace("_", " ") for s in scenarios])
        ax.set_ylabel(ylabel)
        ax.set_title(f"{ylabel} by Scenario")
        ax.legend()
        fig.tight_layout()
        out = os.path.join(outdir, fname)
        fig.savefig(out, dpi=180)
        plt.close(fig)
        print(f"Saved {out}")


if __name__ == "__main__":
    main()
