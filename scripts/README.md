# fyp_execution_kit scripts

## Quick start (no ROS needed)

1. Create Python venv:
```bash
cd /Users/paulairabor/Documents/year4-sem2/fyp/fyp_execution_kit
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install matplotlib
```

2. Run experiment generator:
```bash
cd scripts
python run_scenario.py --runs 30
```

3. Build summary table:
```bash
python evaluate_metrics.py
```

4. Generate figures:
```bash
python plot_results.py
```

Outputs:
- data/raw_logs/experiment_runs.csv
- data/processed/results_summary.csv
- data/figures/response_time_comparison.png
- data/figures/success_rate_comparison.png

Use results_summary.csv values to fill dissertation tables.
