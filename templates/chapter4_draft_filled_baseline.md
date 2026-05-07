# Chapter Four: Implementation

## 4.1 Introduction
This chapter presents the implemented emergency-response prototype used to operationalize the study objectives. The implementation connects emergency event generation, path planning, execution logic, and performance logging.

Although the final architecture is targeted for ROS2 and Gazebo, this baseline implementation was developed first as a reproducible Python experiment pipeline to establish end-to-end behavior and generate initial evaluation evidence.

## 4.2 Development Environment
Implementation environment:
- Language: Python 3
- Libraries: standard Python libraries and Matplotlib for plotting
- Repository structure: execution scripts, data logs, processed summaries, figure outputs
- Development platform: macOS

Generated artifacts are written to:
- Raw run logs in CSV format
- Processed metric summary in CSV format
- Comparison figures in PNG format

## 4.3 Implemented Modules
### 4.3.1 Scenario and Event Module
A scenario module defines three uncertainty levels (low, moderate, and high crowding). Each scenario controls obstacle density and dynamic obstruction events. For each run, an emergency is triggered and a start-goal pair is generated.

### 4.3.2 Path Planning Module
Two planners were implemented:
1. A*: deterministic graph search with Manhattan heuristic.
2. RRT*: sampling-based stochastic planner with nearest-node extension, local parent improvement, and goal-biased sampling.

### 4.3.3 Dynamic Obstacle and Replanning Module
During execution, dynamic obstacle injections can invalidate previously feasible routes. The module triggers replanning and tracks the number of replan events per run.

### 4.3.4 Metrics Logging Module
Each run logs:
- Scenario and planner
- Response time
- Path length
- Success or failure
- Planning computation time
- Replanning count

### 4.3.5 Analysis and Visualization Module
Post-processing scripts aggregate metrics by scenario and planner and generate chapter-ready figures for response-time and success-rate comparison.

## 4.4 Integration Workflow
1. Scenario is initialized.
2. Emergency event is triggered.
3. Planner computes route.
4. Dynamic events may trigger replanning.
5. Final outcome and metrics are recorded.
6. Aggregation and plotting scripts produce summary outputs.

## 4.5 Scenario Configuration
Three scenarios were configured:
1. Low crowding: lower obstacle density and fewer dynamic events.
2. Moderate crowding: increased density and moderate dynamic interference.
3. High crowding: highest density and frequent dynamic disruption.

Each scenario was executed for both planners under matched run counts.

## 4.6 Execution Outputs
The implementation generated the following outputs:
- Experiment run log CSV (all runs)
- Result summary CSV (aggregated metrics)
- Response-time comparison figure
- Success-rate comparison figure

These outputs provide direct evidence for the Chapter Five conclusions.

## 4.7 Implementation Challenges and Fixes
1. Runtime hang in initial RRT* implementation
- Cause: potential parent-cycle in rewiring and path reconstruction.
- Fix: removed unsafe rewiring path and added cycle guard.
- Result: stable execution and completed run batches.

2. Slow execution in early parameter settings
- Cause: large grid and high iteration defaults.
- Fix: reduced baseline grid size and RRT* runtime parameters.
- Result: practical run duration on laptop environment.

3. Plotting dependency issue
- Cause: missing plotting package in active environment.
- Fix: installed required package and used non-GUI plotting backend.
- Result: figures generated successfully.

## 4.8 Chapter Summary
This chapter documented the implemented baseline prototype and its experiment workflow. The system successfully executed comparative runs, logged all required metrics, and produced analysis outputs. These results support the quantitative discussion, conclusions, and recommendations presented in Chapter Five while preparing the project for full ROS2/Gazebo migration.
