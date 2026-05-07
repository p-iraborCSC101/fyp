#!/usr/bin/env python3
"""Orchestrator for the full ROS 2 / Gazebo experiment matrix.

Loops over (scenario, planner, run_id), launches the emergency_sim stack
once per trial, waits for the response logger to drop the per-trial sentinel
~/fyp_ws/logs/run_<run_id>.done (or hits a wall-clock timeout), kills the
launch, and continues.  At the end it copies the aggregated trial_results.csv
into data/raw_logs/ for the analysis scripts.

Usage:
    python3 scripts/run_ros2_experiment.py --runs 30 --seed 42

Run inside a sourced ROS 2 / colcon environment, e.g.:
    source /opt/ros/jazzy/setup.bash
    source ~/fyp_ws/install/setup.bash
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SCENARIOS = ('low_crowding', 'moderate_crowding', 'high_crowding')
PLANNERS = ('a_star', 'rrt_star')

LOG_DIR = Path.home() / 'fyp_ws' / 'logs'
TRIAL_CSV = LOG_DIR / 'trial_results.csv'


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Run the full A* vs RRT* matrix in Gazebo Sim.')
    p.add_argument('--runs', type=int, default=30,
                   help='Trials per (scenario, planner) cell.  Default 30.')
    p.add_argument('--seed', type=int, default=42, help='Base seed.')
    p.add_argument('--launch-timeout-s', type=float, default=120.0,
                   help='Wall-clock budget per trial before forcibly killing the launch.')
    p.add_argument('--settle-s', type=float, default=2.0,
                   help='Sleep between trials so Gazebo can fully tear down.')
    p.add_argument('--headless', action='store_true', default=True,
                   help='Use gz sim -s (no GUI).  Default true for batch.')
    p.add_argument('--gui', dest='headless', action='store_false',
                   help='Force GUI on (slower).')
    p.add_argument('--scenarios', nargs='+', default=list(SCENARIOS),
                   help='Subset of scenarios.')
    p.add_argument('--planners', nargs='+', default=list(PLANNERS),
                   help='Subset of planners.')
    p.add_argument('--out-csv', type=str,
                   default=str(Path(__file__).resolve().parent.parent
                               / 'data' / 'raw_logs' / 'experiment_runs_ros2.csv'),
                   help='Where to copy the aggregated trial_results.csv.')
    return p.parse_args()


def ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def reset_trial_csv() -> None:
    if TRIAL_CSV.exists():
        backup = TRIAL_CSV.with_suffix(f'.csv.bak.{int(time.time())}')
        shutil.move(TRIAL_CSV, backup)
        print(f'  (existing trial_results.csv backed up to {backup.name})')


def run_trial(scenario: str, planner: str, run_id: int, seed: int,
              launch_timeout_s: float, headless: bool) -> bool:
    """Launch one trial and wait for the sentinel.  Return True on success."""
    sentinel = LOG_DIR / f'run_{run_id}.done'
    if sentinel.exists():
        sentinel.unlink()

    cmd = [
        'ros2', 'launch', 'emergency_launch', 'emergency_sim.launch.py',
        f'planner_mode:={planner}',
        f'scenario:={scenario}',
        f'run_id:={run_id}',
        f'seed:={seed + run_id}',
        f'headless:={"true" if headless else "false"}',
    ]
    print(f'  launching: {" ".join(cmd)}')
    proc = subprocess.Popen(cmd, preexec_fn=os.setsid,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    deadline = time.monotonic() + launch_timeout_s
    sentinel_seen = False
    try:
        while time.monotonic() < deadline:
            if sentinel.exists():
                sentinel_seen = True
                # Give the logger a beat to flush.
                time.sleep(1.0)
                break
            if proc.poll() is not None:
                print(f'  launch exited prematurely (rc={proc.returncode})')
                break
            time.sleep(0.5)
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass

    if not sentinel_seen:
        print(f'  TIMEOUT for run_id={run_id}')
    return sentinel_seen


def main() -> None:
    args = parse_args()
    ensure_log_dir()
    reset_trial_csv()

    total = len(args.scenarios) * len(args.planners) * args.runs
    print(f'Total trials: {total}')

    run_id = 0
    success = 0
    t_start = time.time()
    for scenario in args.scenarios:
        for planner in args.planners:
            for trial_idx in range(1, args.runs + 1):
                run_id += 1
                print(f'[{run_id}/{total}] scenario={scenario} planner={planner} trial={trial_idx}')
                ok = run_trial(scenario, planner, run_id, args.seed,
                               args.launch_timeout_s, args.headless)
                if ok:
                    success += 1
                time.sleep(args.settle_s)

    elapsed = time.time() - t_start
    print(f'\nDone: {success}/{total} trials reached the sentinel; {elapsed/60:.1f} min wall clock.')

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if TRIAL_CSV.exists():
        shutil.copy2(TRIAL_CSV, out_csv)
        print(f'Copied {TRIAL_CSV} -> {out_csv}')
    else:
        print(f'WARNING: {TRIAL_CSV} not found; nothing to copy.', file=sys.stderr)


if __name__ == '__main__':
    main()
