#!/usr/bin/env python3
"""Rerun the lightweight scenarios with adjusted RRT* hyperparameters.

This script reuses `run_scenario` functions, overrides `rrt_star` with a
higher-iteration, stronger goal-bias variant, writes a new CSV, and
calls `evaluate_metrics.py` to produce a processed summary.
"""

from __future__ import annotations

import csv
import os
import runpy
import sys
from pathlib import Path

# import the run_scenario module
import runpy
rs = runpy.run_path(str(Path(__file__).resolve().parent / 'run_scenario.py'))

# `rs` is a dict of the run_scenario globals; wrap access convenience
class RSModule:
    pass

mod = RSModule()
for k, v in rs.items():
    setattr(mod, k, v)
rs = mod

# keep original
_orig_rrt = rs.rrt_star

# tuned parameters
TUNED_ITER = 10000
TUNED_STEP = 2
TUNED_GOAL_BIAS = 0.4


def rrt_tuned(grid, start, goal, rng, iterations: int = TUNED_ITER, step: int = TUNED_STEP, goal_bias: float = TUNED_GOAL_BIAS):
    # call original implementation with larger budgets and stronger goal bias
    return _orig_rrt(grid, start, goal, rng, iterations=iterations, step=step, goal_bias=goal_bias)

# monkeypatch
rs.rrt_star = rrt_tuned

# prepare output path
here = Path(__file__).resolve().parent
out_csv = here / '../data/raw_logs/experiment_runs_rrt_tuned.csv'
out_csv = out_csv.resolve()
out_csv.parent.mkdir(parents=True, exist_ok=True)

rows = []
for scenario in rs.SCENARIOS:
    for planner in ("A*", "RRT*"):
        for run_id in range(1, 31):
            rows.append(rs.run_once(planner, scenario, run_id, base_seed=42, size=28))

with open(out_csv, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

print(f'Wrote {len(rows)} rows to {out_csv}')

# run evaluate_metrics to produce processed summary
# Use runpy to execute the module's file
eval_script = here / 'evaluate_metrics.py'
# call as script with args
sys.argv = ['evaluate_metrics.py', '--infile', str(out_csv), '--outfile', str(here / '../data/processed/results_summary_rrt_tuned.csv')]
runpy.run_path(str(eval_script), run_name='__main__')

print('Evaluation complete. Processed summary at:', here / '../data/processed/results_summary_rrt_tuned.csv')
