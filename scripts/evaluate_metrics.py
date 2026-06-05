#!/usr/bin/env python3
"""Aggregate experiment runs into chapter-ready summary metrics.

By default rows are grouped by (scenario, planner). Pass --by-goal to additionally
split by the goal cell (patient_a vs patient_b), which removes the bimodality you
get from averaging the short near-patient route together with the long
far-patient route -- recommended for the write-up.
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
from collections import defaultdict

# Known patient goals -> readable label (falls back to raw coords otherwise).
PATIENT_LABELS = {
    (4, 9): "patient_a",
    (12, 9): "patient_b",
}


def read_rows(path: str) -> list[dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def goal_label(gx: str, gy: str) -> str:
    try:
        key = (int(float(gx)), int(float(gy)))
    except (ValueError, TypeError):
        return "unknown"
    return PATIENT_LABELS.get(key, f"goal_{key[0]}_{key[1]}")


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return round(values[0], 4), 0.0
    return round(statistics.fmean(values), 4), round(statistics.pstdev(values), 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize experiment CSV into planner/scenario metrics.")
    parser.add_argument("--infile", type=str, default="../data/raw_logs/experiment_runs.csv")
    parser.add_argument("--outfile", type=str, default="../data/processed/results_summary.csv")
    parser.add_argument("--by-goal", action="store_true",
                        help="Also split each (scenario, planner) cell by goal (patient_a/patient_b).")
    args = parser.parse_args()

    in_path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.infile))
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.outfile))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    rows = read_rows(in_path)
    grouped: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        if args.by_goal:
            key = (r["scenario"], r["planner"], goal_label(r.get("goal_x", ""), r.get("goal_y", "")))
        else:
            key = (r["scenario"], r["planner"])
        grouped[key].append(r)

    summary = []
    for key, items in sorted(grouped.items()):
        resp_m, resp_s = mean_std([to_float(x["response_time_s"]) for x in items])
        plen_m, plen_s = mean_std([to_float(x["path_length_m"]) for x in items])
        comp_m, comp_s = mean_std([to_float(x["compute_time_ms"]) for x in items])
        repl_m, repl_s = mean_std([to_float(x["replans"]) for x in items])
        succ = [to_float(x["success"]) for x in items]

        row = {
            "scenario": key[0],
            "planner": key[1],
            "runs": len(items),
            "response_time_mean_s": resp_m,
            "response_time_std_s": resp_s,
            "path_length_mean_m": plen_m,
            "path_length_std_m": plen_s,
            "success_rate_pct": round(100.0 * statistics.fmean(succ), 2) if succ else 0.0,
            "compute_time_mean_ms": comp_m,
            "compute_time_std_ms": comp_s,
            "replans_mean": repl_m,
            "replans_std": repl_s,
        }
        if args.by_goal:
            row["goal"] = key[2]
        summary.append(row)

    fieldnames = ["scenario", "planner"]
    if args.by_goal:
        fieldnames.append("goal")
    fieldnames += [
        "runs",
        "response_time_mean_s", "response_time_std_s",
        "path_length_mean_m", "path_length_std_m",
        "success_rate_pct",
        "compute_time_mean_ms", "compute_time_std_ms",
        "replans_mean", "replans_std",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary)

    print(f"Wrote summary to {out_path}  ({'by goal' if args.by_goal else 'pooled'}, {len(summary)} rows)")


if __name__ == "__main__":
    main()
