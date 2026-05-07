# Chapter Five: Summary, Conclusions and Recommendations

## 5.1 Introduction
This chapter summarizes the study and presents findings from the implemented emergency-response evaluation pipeline. The objective was to assess how path-planning strategy affects response performance in uncertain hospital-like scenarios.

## 5.2 Summary of the Study
The study addressed delayed emergency response in dynamic clinical environments by integrating emergency event detection and autonomous navigation planning. The system compared A* and RRT* under three scenario groups: low crowding, moderate crowding, and high crowding.

A reproducible experiment pipeline was used to run repeated trials, log metrics, and produce summary statistics and figures. The core metrics were response time, path length, success rate, planning computation time, and replanning frequency.

## 5.3 Summary of Results
The experiment set used 10 runs per planner per scenario (60 runs total).

### 5.3.1 Response Time
- Low crowding: A* mean = 26.8095 s, RRT* mean = 705.7694 s
- Moderate crowding: A* mean = 24.1605 s, RRT* mean = 999.1207 s
- High crowding: A* mean = 125.6230 s, RRT* mean = 999.1360 s

### 5.3.2 Path Length
- Low crowding: A* mean = 25.0000 m, RRT* mean = 6.5919 m
- Moderate crowding: A* mean = 24.2000 m, RRT* mean = 0.0000 m
- High crowding: A* mean = 25.6000 m, RRT* mean = 0.0000 m

### 5.3.3 Success Rate
- Low crowding: A* = 100.0%, RRT* = 30.0%
- Moderate crowding: A* = 100.0%, RRT* = 0.0%
- High crowding: A* = 90.0%, RRT* = 0.0%

### 5.3.4 Computation Time and Replanning
- Low crowding compute time: A* = 0.4841 ms, RRT* = 3.1373 ms
- Moderate crowding compute time: A* = 0.4202 ms, RRT* = 0.7667 ms
- High crowding compute time: A* = 0.4768 ms, RRT* = 2.3440 ms
- Mean replans (A*): 1.6, 3.8, 6.4 by increasing crowding
- Mean replans (RRT*): 1.0, 1.6, 3.5 by increasing crowding

## 5.4 Discussion of Findings
Across this baseline implementation, A* produced substantially higher reliability and lower response times than RRT*. A* maintained perfect success in low and moderate crowding and retained high reliability under high crowding. RRT* performance degraded significantly, with low success in low crowding and complete failure in moderate and high crowding.

The result suggests that implementation quality and runtime constraints strongly influence stochastic planner performance. In this baseline, the RRT* configuration was not robust enough for dense dynamic conditions. Therefore, these findings should be interpreted as implementation-level evidence, not as a final conclusion about stochastic methods in general.

## 5.5 Conclusions
1. Objective 1 (emergency event detection pipeline) was achieved through successful event-to-navigation triggering and complete run logging.
2. Objective 2 (planner implementation) was achieved, as both A* and RRT* were implemented and executed across all scenarios.
3. Objective 3 (integration of sensing and navigation) was achieved with end-to-end run traces and generated outputs.
4. Objective 4 (comparative evaluation) was achieved through metric-based analysis across multiple uncertainty conditions.

Overall, the current baseline implementation shows that A* is more stable than the current RRT* setup in the tested simulation pipeline. This establishes a concrete benchmark and motivates further optimization of the stochastic planner in the full ROS2/Gazebo environment.

## 5.6 Contributions of the Study
- Delivered a complete, reproducible emergency-response experiment workflow.
- Produced measurable comparison outputs across uncertainty levels.
- Established baseline evidence that can be extended in ROS2/Gazebo experiments.

## 5.7 Limitations
- Current baseline evaluation is not full ROS2/Gazebo hardware-faithful simulation.
- RRT* tuning is preliminary and may under-represent achievable stochastic performance.
- Emergency behavior and human-flow dynamics are simplified.

## 5.8 Recommendations for Future Work
1. Re-implement and evaluate both planners inside ROS2/Gazebo with navigation stack integration.
2. Improve RRT* using informed sampling, stronger goal bias control, and adaptive iteration budgets.
3. Add richer dynamic obstacle models and human-aware constraints.
4. Increase trial counts and apply stronger statistical tests.
5. Validate transferability with a physical robot platform in controlled settings.

## 5.9 Final Closing Statement
The project demonstrates a practical path from concept to evidence by turning the proposed emergency-response framework into executable experiments and measurable outcomes. It provides a foundation for full ROS2/Gazebo deployment and stronger stochastic navigation evaluation in healthcare emergency contexts.
