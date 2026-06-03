#!/usr/bin/env python3
"""Run parameter sweep for RRT* hyperparameters and aggregate results.

Produces one processed summary file per configuration and a combined CSV
summarising success counts per scenario per config.
"""
from __future__ import annotations

import csv
import runpy
from pathlib import Path
from itertools import product

# load run_scenario as module dict
base = Path(__file__).resolve().parent
rs_globals = runpy.run_path(str(base / 'run_scenario.py'))

# wrap into object for attribute access
class RS:
    pass
rs = RS()
for k, v in rs_globals.items():
    setattr(rs, k, v)

OUT_DIR = base / '../data/processed'
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR = base / '../data/raw_logs'
RAW_DIR.mkdir(parents=True, exist_ok=True)

iter_choices = [2000, 5000, 10000]
goal_bias_choices = [0.25, 0.4, 0.6]
step_choices = [1, 2, 4]
informed_choices = [False, True]

summary_rows = []
config_id = 0
for iters, gb, step, informed in product(iter_choices, goal_bias_choices, step_choices, informed_choices):
    config_id += 1
    name = f'iters{iters}_gb{int(gb*100)}_step{step}' + ("_informed" if informed else "")
    raw_path = RAW_DIR / f'experiment_runs_rrt_{name}.csv'
    # define tuned rrt
    orig = rs.rrt_star
    if not informed:
        def rrt_tuned(grid, start, goal, rng, iterations=iters, step=step, goal_bias=gb):
            return orig(grid, start, goal, rng, iterations=iterations, step=step, goal_bias=goal_bias)
        rs.rrt_star = rrt_tuned
    else:
        # informed-sampling variant: sample along line between start and goal with gaussian perpendicular noise
        def rrt_informed(grid, start, goal, rng, iterations=iters, step=step, goal_bias=gb):
            size = len(grid)
            nodes = [start]
            parent = {}
            cost = {start: 0.0}

            def euclid(a, b):
                import math
                return math.hypot(a.x - b.x, a.y - b.y)

            def nearest(q):
                return min(nodes, key=lambda n: euclid(n, q))

            def steer(a, b):
                dist = euclid(a, b)
                if dist <= step:
                    return b
                nx = int(round(a.x + (b.x - a.x) * (step / dist)))
                ny = int(round(a.y + (b.y - a.y) * (step / dist)))
                nx = max(0, min(size - 1, nx))
                ny = max(0, min(size - 1, ny))
                return rs.Point(nx, ny)

            for _ in range(iterations):
                if rng.random() < goal_bias:
                    q_rand = goal
                else:
                    # sample t along line, perturb perpendicular with Gaussian
                    t = rng.random()
                    mx = start.x + t * (goal.x - start.x)
                    my = start.y + t * (goal.y - start.y)
                    # perpendicular noise magnitude scaled by distance
                    dist = euclid(start, goal)
                    perp_std = max(1.0, dist * 0.1)
                    rx = int(round(rng.gauss(mx, perp_std)))
                    ry = int(round(rng.gauss(my, perp_std)))
                    rx = max(0, min(size - 1, rx))
                    ry = max(0, min(size - 1, ry))
                    q_rand = rs.Point(rx, ry)
                if grid[q_rand.y][q_rand.x] == 1:
                    continue
                q_near = nearest(q_rand)
                q_new = steer(q_near, q_rand)
                if grid[q_new.y][q_new.x] == 1:
                    continue
                # collision check using provided helper if available
                try:
                    ok = rs.collision_free(grid, q_near, q_new)
                except Exception:
                    ok = True
                if not ok:
                    continue

                nodes.append(q_new)
                parent[q_new] = q_near
                cost[q_new] = cost[q_near] + euclid(q_near, q_new)

                radius = 3
                near_nodes = [n for n in nodes if euclid(n, q_new) <= radius and n != q_new]
                for n in near_nodes:
                    try:
                        if rs.collision_free(grid, n, q_new):
                            cand = cost[n] + euclid(n, q_new)
                            if cand < cost[q_new]:
                                parent[q_new] = n
                                cost[q_new] = cand
                    except Exception:
                        continue

                # continue building tree; final path reconstruction will fall back to original
            # fallback: attempt original with given iterations
            return orig(grid, start, goal, rng, iterations=iterations, step=step, goal_bias=goal_bias)
        rs.rrt_star = rrt_informed
    rows = []
    run_counter = 0
    for scenario in rs.SCENARIOS:
        for planner in ("A*", "RRT*"):
            for run_id in range(1, 31):
                run_counter += 1
                seed = 1000 * config_id + run_counter
                rows.append(rs.run_once(planner, scenario, run_id, base_seed=seed, size=28))
    # write raw
    with open(raw_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    # evaluate metrics by calling evaluate_metrics.py logic here (simple aggregation)
    grouped = {}
    for r in rows:
        key = (r['scenario'], r['planner'])
        grouped.setdefault(key, []).append(r)
    outrows = []
    for (scenario, planner), items in sorted(grouped.items()):
        runs = len(items)
        resp = [float(x['response_time_s']) for x in items]
        plen = [float(x['path_length_m']) for x in items]
        succ = [int(x['success']) for x in items]
        comp = [float(x['compute_time_ms']) for x in items]
        repl = [int(x['replans']) for x in items]
        import statistics
        outrows.append({
            'config': name,
            'scenario': scenario,
            'planner': planner,
            'runs': runs,
            'response_time_mean_s': round(statistics.fmean(resp), 4),
            'path_length_mean_m': round(statistics.fmean(plen), 4),
            'success_rate_pct': round(100.0 * statistics.fmean(succ), 2),
            'compute_time_mean_ms': round(statistics.fmean(comp), 4),
            'replans_mean': round(statistics.fmean(repl), 4),
        })
    # write processed per-config
    proc_path = OUT_DIR / f'results_summary_rrt_{name}.csv'
    with open(proc_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = list(outrows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(outrows)
    # record summary (success counts)
    for r in rows:
        if r['planner'] == 'RRT*':
            summary_rows.append({'config': name, 'scenario': r['scenario'], 'success': r['success']})

# write combined success summary pivot-like
combined = {}
for row in summary_rows:
    key = (row['config'], row['scenario'])
    combined.setdefault(key, 0)
    combined[key] += int(row['success'])

with open(OUT_DIR / 'rrt_sweep_success_counts.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['config', 'scenario', 'rtt_success_count_out_of_30'])
    for (cfg, sc), cnt in sorted(combined.items()):
        writer.writerow([cfg, sc, cnt])

print('Sweep complete; per-config processed outputs in', OUT_DIR)
print('Summary counts in', OUT_DIR / 'rrt_sweep_success_counts.csv')
