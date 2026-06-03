# Chapter Five: Summary, Conclusions and Recommendations

## 5.1 Introduction
This chapter summarises the study, presents key experimental results from the implemented evaluation pipeline, interprets those results, and gives evidence-based conclusions and recommendations for future work.

## 5.2 Summary of Study
The project integrated an IoT-based emergency detection pipeline with two path-planning implementations (A* and RRT*) and evaluated their performance in three simulated hospital crowding scenarios (low, moderate, high). Trials were executed reproducibly by the ROS2/Gazebo experiment orchestrator and results were aggregated into `fyp_execution_kit/data/processed/results_summary.csv`.

## 5.3 Summary of Experimental Results
Results below use the aggregated means from the experiment log (30 runs per planner per scenario).

### Quick Results Table
scenario,planner,response_time_mean_s,path_length_mean_m,success_rate_pct
low_crowding,A*,25.155,24.167,100.0
low_crowding,RRT*,739.077,6.228,26.67
moderate_crowding,A*,25.724,25.900,100.0
moderate_crowding,RRT*,934.276,1.660,6.67
high_crowding,A*,60.442,26.433,96.67
high_crowding,RRT*,999.130,0.000,0.00

Note: `999.130` response time indicates trials that hit the configured timeout and should be treated as failures for timing and path metrics; `0.000` path length indicates planner failure to produce a valid route. When presenting results, state these semantics explicitly and consider excluding timeouts from mean path-length calculations or showing them separately.

### 5.3.1 Response Time (mean)
### 5.3.1 Response Time (mean)
- Low crowding: A* = 25.16 s, RRT* = 739.08 s
- Moderate crowding: A* = 25.72 s, RRT* = 934.28 s
- High crowding: A* = 60.44 s, RRT* = 999.13 s

### 5.3.2 Path Length (mean)
- Low crowding: A* = 24.17 m, RRT* = 6.23 m
- Moderate crowding: A* = 25.90 m, RRT* = 1.66 m
- High crowding: A* = 26.43 m, RRT* = 0.00 m

### 5.3.3 Success Rate (percent)
- Low crowding: A* = 100.0%, RRT* = 26.67%
- Moderate crowding: A* = 100.0%, RRT* = 6.67%
- High crowding: A* = 96.67%, RRT* = 0.00%

### 5.3.4 Compute Time and Replans (mean)
- Compute time (mean ms): A* ≈ 0.45 ms, RRT* ≈ 1.09 ms (varies by scenario)
- Replans (mean): A* increases with crowding (≈1.67, 3.80, 6.63), RRT* shows fewer replans but very low success (≈1.0–3.73)

### 5.3.5 Statistical Tests
To support claims about observed differences, a permutation test on successful-run response times (A* vs RRT*) was performed per scenario. Tests exclude failed trials (response_time >= timeout sentinel) and compare mean response times using 20,000 permutations.

- low_crowding: A* (n=30) vs RRT* (n=8) — A* mean = 25.155 s, RRT* mean = 23.910 s; permutation p ≈ 0.697 (no significant difference among successful runs).
- moderate_crowding: A* (n=30) vs RRT* (n=2) — A* mean = 25.724 s, RRT* mean = 26.336 s; permutation p ≈ 0.887 (not significant; very small RRT* sample).
- high_crowding: RRT* had no successful runs (n=0); statistical comparison is not possible.

Caveats: the large number of RRT* timeouts means the successful-run sample for RRT* is small and biased; permutation tests on successful runs therefore do not capture the real operational difference driven by failure rates. For strict comparison of operational performance consider tests on success rates (chi-squared or Fisher exact) and comparing full-run response-time distributions treating timeouts as censored outcomes.

### 5.3.6 Success-rate tests
To quantify operational differences we applied Fisher's exact test to the 2×2 success/failure contingency table (A* vs RRT*) per scenario. The test was performed on the full trial set (30 trials per planner per scenario). Results:

- low_crowding: A* successes = 30/30, RRT* successes = 8/30 → Fisher two-sided p ≈ 8.27e-10 (strongly significant).
- moderate_crowding: A* successes = 30/30, RRT* successes = 2/30 → Fisher two-sided p ≈ 8.39e-15 (strongly significant).
- high_crowing: A* successes = 29/30, RRT* successes = 0/30 → Fisher two-sided p ≈ 2.29e-13 (strongly significant).

Interpretation: the success-rate tests show that A* achieves significantly higher completion rates than the RRT* configuration used here across all scenarios. Because these tests use the full trial counts, they capture the operational failure modes (timeouts and planner failures) that permutation tests on successful runs miss. Together, the success-rate and timing analyses support the conclusion that A* is a more reliable planner under the present implementation and parameterisation.

### 5.3.7 Hyperparameter sweep and informed-sampling results
To explore whether simple hyperparameter changes or an informed-sampling variant could improve RRT* reliability, an extended grid sweep was run across iteration budgets {2000, 5000, 10000}, goal-bias {0.25, 0.40, 0.60}, step sizes {1, 2, 4}, and an informed-sampling toggle. Each configuration executed 30 runs per planner per scenario. Results are summarised in the experiment artifact `fyp_execution_kit/data/processed/rrt_sweep_success_counts.csv`.

Quick summary (best-performing configuration per scenario):

- **low_crowding:** `iters5000_gb60_step1_informed` — 13/30 RRT* successes
- **moderate_crowding:** `iters5000_gb60_step2_informed` — 7/30 RRT* successes
- **high_crowding:** `iters10000_gb25_step2` — 1/30 RRT* successes

Interpretation: the sweep shows that (1) informed-sampling variants can substantially increase success rates in the low-crowding case (best observed 13/30), and (2) some parameter combinations (notably moderate iteration budgets with high goal-bias and small step) yield modest gains in moderate crowding. However, no configuration in this sweep produced robust performance in the high-crowding scenario: success rates remain effectively zero for practical operation.

Recommendation: informed sampling plus targeted tuning (e.g., `iters=5000`, `goal_bias=0.6`, `step=1`) is worth exploring further, but for operational deployment the A* baseline remains the safer option until a more reliable stochastic planner is developed and validated.

## 5.4 Discussion of Findings
- Reliability: A* is a stable, low-latency baseline across scenarios; it achieved near-perfect success and low response times. This makes A* suitable as a dependable emergency-response planner in the implemented simulation.
- RRT* behaviour: RRT* produced shorter or zero path-lengths in some scenarios but failed to produce usable results consistently: extremely high mean response times and low success rates indicate tuning or algorithmic mismatches for these constrained indoor, time-critical scenarios.
- Interpretation: The measured RRT* failures likely reflect implementation and parameter choices (iteration budget, step size, goal-bias) and the sampling-based planner’s difficulty with narrow, dynamic corridors and strict realtime constraints. A*’s deterministic, grid-based search benefits from the structured scenario maps used here.
- Trade-offs: Although stochastic planners can explore richer solution spaces, for time-critical emergency response in a small indoor environment, deterministic planners with robust replanning may offer better operational safety and predictability.

## 5.5 Conclusions
1. The implemented IoT-to-navigation pipeline is functional and produced reproducible experimental data supporting the project's objectives.  
2. A* provides a reliable baseline with low response times and high success in the evaluated scenarios.  
3. The current RRT* configuration is not robust for these emergency-response scenarios; it requires substantial tuning or a different formulation to be competitive under time constraints.  
4. Overall, the evidence supports continuing with A* as the baseline and investing targeted effort to improve stochastic planner robustness before claiming parity with deterministic methods.

## 5.6 Contributions
- An end-to-end, reproducible experiment pipeline linking IoT emergency detection and robot navigation.  
- A comparative, metric-driven evaluation of A* and RRT* in hospital-like simulated scenarios.  
- Public experiment artifacts (logs, aggregated summaries, figures) suitable for dissertation tables and figures.

## 5.7 Limitations
- Simulation-only evaluation; real-robot transfer remains untested.  
- RRT* hyperparameters were tuned for baseline experiments and may not reflect optimal settings.  
- Emergency detection is rule-based and not medical-grade; sensor models are simplified.

## 5.8 Recommendations for Future Work
1. Re-run stochastic planners with extended tuning: informed sampling, adaptive iteration budgets, and goal-bias schedules.  
2. Integrate chance-constrained or human-aware cost terms to better capture safety-critical constraints.  
3. Perform transfer tests on a physical robot or in high-fidelity hardware-in-the-loop simulation.  
4. Expand trials (higher run counts) and apply formal statistical tests to strengthen claims.  
5. Investigate hybrid planners that combine A* speed with stochastic refinement for safety-critical replanning.

## 5.9 Final Closing Statement
This work delivers a practical evidence base for IoT-enabled emergency-response navigation in simulated hospital settings. The results provide clear next steps: consolidate the A* baseline for operational use and invest targeted improvements to stochastic planners to achieve reliable, safe autonomy in real-world emergency scenarios.
