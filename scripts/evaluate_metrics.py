#!/usr/bin/env python3
"""Aggregate experiment runs into chapter-ready summary metrics."""

from __future__ import annotations

import argparse
import csv
import os
import statistics
from collections import defaultdict


def read_rows(path: str) -> list[dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(v: str) -> float:
    try:
        return float(v)
    except ValueError:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize experiment CSV into planner/scenario metrics.")
    parser.add_argument("--infile", type=str, default="../data/raw_logs/experiment_runs.csv")
    parser.add_argument("--outfile", type=str, default="../data/processed/results_summary.csv")
    args = parser.parse_args()

    in_path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.infile))
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.outfile))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    rows = read_rows(in_path)
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        grouped[(r["scenario"], r["planner"])].append(r)

    summary = []
    for (scenario, planner), items in sorted(grouped.items()):
        n = len(items)
        resp = [to_float(x["response_time_s"]) for x in items]
        plen = [to_float(x["path_length_m"]) for x in items]
        succ = [to_float(x["success"]) for x in items]
        comp = [to_float(x["compute_time_ms"]) for x in items]
        repl = [to_float(x["replans"]) for x in items]

        summary.append(
            {
                "scenario": scenario,
                "planner": planner,
                "runs": n,
                "response_time_mean_s": round(statistics.fmean(resp), 4),
                "response_time_std_s": round(statistics.pstdev(resp), 4),
                "path_length_mean_m": round(statistics.fmean(plen), 4),
                "path_length_std_m": round(statistics.pstdev(plen), 4),
                "success_rate_pct": round(100.0 * statistics.fmean(succ), 2),
                "compute_time_mean_ms": round(statistics.fmean(comp), 4),
                "replans_mean": round(statistics.fmean(repl), 4),
            }
        )

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario",
                "planner",
                "runs",
                "response_time_mean_s",
                "response_time_std_s",
                "path_length_mean_m",
                "path_length_std_m",
                "success_rate_pct",
                "compute_time_mean_ms",
                "replans_mean",
            ],
        )
        writer.writeheader()
        writer.writerows(summary)

    print(f"Wrote summary to {out_path}")


if __name__ == "__main__":
    main()
