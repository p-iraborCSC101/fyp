
# Chapter Four: Implementation

## 4.1 Introduction

This chapter documents the implementation of the IoT-enabled mobile-robot
emergency-response system whose architecture and requirements were laid out
in Chapter Three. The system is realised as a six-package ROS 2 workspace
running against a custom Gazebo Sim hospital world. It detects a simulated
patient emergency, plans a route from the nurse station to the patient's
bed using either an A\* or an RRT\* planner, drives the robot to the
patient through dynamic crowds of moving humans, and records every
timestamp needed to compare planner performance.

The implementation follows the experimental research approach motivated in
Chapter Three (§3.3) and the build checklist in the project PRD §12. All
artefacts referenced in this chapter exist in `fyp_execution_kit/` and
appear in the appendix file index.

## 4.2 Development Environment

| Component | Choice |
|-----------|--------|
| Operating system | Ubuntu 22.04 LTS |
| ROS 2 distribution | ROS 2 Humble Hawksbill |
| Simulator | Gazebo Sim Harmonic (`gz sim`) |
| Visualisation | RViz 2 |
| ROS ↔ Gazebo bridge | `ros_gz_bridge`, `ros_gz_sim` |
| Languages | Python 3.12 |
| Standard ROS libs | `rclpy`, `nav_msgs`, `geometry_msgs`, `std_msgs`, `tf2_ros` |
| Analysis libraries | `csv`, `statistics`, Matplotlib |
| Build system | `colcon` with `ament_python` |
| Editor | Visual Studio Code |
| Version control | Git, hosted on GitHub |

The full `apt install` command list for setting up a fresh Ubuntu 22.04
machine is given in [Appendix B – Reproducibility](#appendix-b--reproducibility).

## 4.3 System Module Implementation

The system is composed of six ROS 2 packages mapping one-to-one onto the
architecture layers in Chapter Three §3.4. Each package exposes a single
node, and the launch file `emergency_launch/launch/emergency_sim.launch.py`
brings them up together with Gazebo Sim, the bridge, the static TF
publisher, and RViz 2.

### 4.3.1 IoT Sensing Module — `emergency_sensing`

The IoT sensing module is realised as two nodes: `sensor_simulator` and
`alert_fusion` (`ros2_ws/src/emergency_sensing/emergency_sensing/`). The
`sensor_simulator` node models a wearable / environmental sensor stack that
emits camera-fall, heart-rate, and motion-state signals alongside a synthetic
camera image stream. Patient locations are loaded from the scenario YAML; on
each run the node selects one location with a seed-controlled random choice,
builds the sensor streams, and starts publishing after a configurable
`first_alert_delay_s`.

The `alert_fusion` node subscribes to these sensor topics, applies simple
thresholding and rule-based logic (e.g., fall detected + high heart rate +
no motion), and publishes the consolidated alert on `/emergency_alert`.

The alert payload (`std_msgs/String` carrying JSON):

```json
{
  "alert_id": "run17_alert1_84321",
  "event_type": "fall_detected",
  "patient_id": "patient_b",
  "severity": "high",
  "location": {"x": 12, "y": 9},
  "run_id": 17,
  "sequence": 0,
  "t_alert_ns": 1759230432123456789
}
```

The `alert_id` is the join key used by every downstream node to attach
their per-event timestamps and outcomes back to a single trial row in
`trial_results.csv`. The `t_alert_ns` value uses the simulation clock
when the bridge publishes `/clock`, ensuring response-time measurements
are not distorted by wall-clock drift inside Gazebo.

`std_msgs/String` carrying JSON was preferred over a custom `.msg` type
in this iteration because it allowed the alert / route / status schemas
to evolve without forcing a `colcon build` of an interface package
between every change.

### 4.3.2 Fusion / Decision Module

Fusion and decision-making are handled by the `alert_fusion` node in
`emergency_sensing`. This module consumes the raw simulated sensor streams
and emits a single canonical incident when its rule set is met. The
resulting message includes `alert_id`, `event_type`, and `location`, which
the planner consumes directly. In a richer deployment, this module would be
extended to a probabilistic or learning-based fusion approach; that
future-work extension is captured in Chapter Five §5.7.

### 4.3.3 Path-Planning Module — `path_planner`

The `path_planner` node
(`ros2_ws/src/path_planner/path_planner/path_planner_node.py`) implements
both planners behind a single `planner_mode` parameter. Its grid model is
loaded at start-up from the scenario YAML so the same authored layout
drives both Gazebo (via the SDF walls) and the planner (via the
`planner_grid.obstacles` list) — this prevents the planner from returning
paths that walk through walls, which had been a problem in the earlier
hard-coded grid (§4.7).

The planner maintains three obstacle sets:
1. **Static obstacles**: loaded once from the scenario YAML; these model walls and beds.
2. **Event-triggered obstacles**: added transiently when `/replan_request` fires;
   these model moving humans that caused a stall.
3. **Human-driven obstacles**: continuously updated from `/dynamic_obstacles`;
   these model live actor positions from Gazebo.

During path search, a cell is blocked if it belongs to any of the three sets or
if it is out of bounds.

#### A\* Implementation

A\* is implemented over the 24 × 14 unit-cell grid with 4-connectivity and
the Manhattan heuristic `h(n) = |n.x − g.x| + |n.y − g.y|`. The cost of
each edge is uniformly 1, reflecting the 1 m grid spacing and the absence
of slope or surface-cost data in the simulated hospital floor. The
implementation uses a binary heap (`heapq`) for the open set and a `set`
for the closed set, giving the textbook `O((V + E) log V)` time complexity.
With 24 × 14 = 336 cells the worst-case search space is small and A\*
returns in well under a millisecond on the test machine.

Tie-breaking in the open heap follows the insertion order, ensuring
consistent path selection across runs when costs are equal.

#### RRT\* Implementation

RRT\* is implemented with the same scenario grid as the implicit obstacle
predicate, a 25 % goal-bias sampling rate, and a `near()` rewiring radius
that scales as `min(4.0, 2 √(log n / n) · max(W, H))` to keep the local
neighbourhood small in dense regions. `steer()` projects each random
sample onto the segment of length `step_size` (0.8 m by default) from the
nearest tree node, and `is_collision_free()` discretises the segment into
0.5 m-spaced waypoints and rejects any whose grid cell is blocked. The
planner declares the parameters `rrt_max_iterations`, `rrt_step_size`,
and `rrt_goal_sample_rate`; their defaults (2000 / 0.8 / 0.25) were
chosen during Day 5 tuning (§4.7) and are recorded in
`emergency_sim.launch.py`.

Unlike A\*, which is deterministic, RRT\* is seeded from the `seed`
parameter so that repeated runs with the same scenario and seed produce
the same sequences of random samples and thus the same final paths. This
allows fair head-to-head comparison.

#### Dynamic Re-Planning

Both planners support re-planning triggered by `/replan_request`. On
a request the node injects a transient obstacle near the robot's current grid
cell (to model the moving human that caused the stall), increments a
per-alert replan counter, and re-runs the active planner. After 6
replans for a single alert the system flags the trial as failed to prevent
infinite loops.

### 4.3.4 Navigation and Control Module — `robot_control`

The `robot_controller` node
(`ros2_ws/src/robot_control/robot_control/robot_controller_node.py`)
follows the planned route as a list of metric waypoints. It uses a simple
proportional controller: linear speed is `min(v_max, K_v · d)` where d is
the distance to the next waypoint, and angular speed is `K_ω · θ_e` where
θ_e is the heading error to the next waypoint, clipped to `±ω_max`. When
the heading error exceeds 1 rad the linear command is scaled to 20 % of
its target, which lets the robot turn in place near sharp corners without
overshoot. Arrival is declared when the Euclidean distance to the final
waypoint falls under `waypoint_tolerance` (0.4 m).

Stall detection. A stall is detected when the robot has moved less than
5 cm over `stall_timeout_s` (2.5 s) while the most recent linear command
exceeded `stall_min_cmd_linear` (0.05 m/s). When a stall fires the
controller publishes a `/replan_request` payload containing the current
grid cell of the robot, and the planner injects a transient obstacle at
an adjacent cell before re-planning. A per-alert replan budget of 6
prevents the system from looping indefinitely; exhausting it ends the
trial as a failure with reason `replan_budget_exhausted`.

The `cmd_vel` / `odom` topics are remapped at launch time to the bridged
Gazebo topics `/model/medibot/cmd_vel` and `/model/medibot/odometry`. A
static TF publisher emits an identity `map → odom` transform so RViz and
the `Path` message use a consistent frame.

### 4.3.5 Caregiver Notification Module — `caregiver_notify`

The `caregiver_notify` node (`ros2_ws/src/caregiver_notify/caregiver_notify/caregiver_notify_node.py`)
bridges emergency alerts and robot status to a caregiver notification channel, implementing
the top tier of the three-layer architecture outlined in Chapter Three §3.4.

The node:
- Subscribes to `/emergency_alert` and `/robot_status`
- Publishes JSON payloads on `/caregiver_notify` (alert notifications) and
  `/caregiver_status` (robot progress updates)
- Implements a cooldown mechanism (configurable, default 10 s) to avoid alert
  fatigue from repeated re-planning events

The caregiver notification payload structure:

```json
{
  "caregiver_id": "ward-a",
  "type": "alert",
  "timestamp": 1759230432.131,
  "message": "Fall detected at patient_b (12, 9.5). Robot dispatched."
}
```

This decouples the caregiver interface from the reactive planning loop,
permitting future extensions such as SMS/email dispatch, mobile app push,
or two-way acknowledgment protocols without modifying the planning stack.

### 4.3.6 Dynamic Obstacle Module — `human_obstacles`

The `human_obstacles` node (`ros2_ws/src/human_obstacles/human_obstacles/human_obstacles_node.py`)
translates animated human actors from Gazebo into dynamic obstacle poses for the planner.
This module closes the loop on the three-layer system: IoT sensors detect an emergency
(layer 1), caregiver is notified (layer 3), and the robot navigates through live human
obstacles (layer 2).

The node:
- Subscribes to actor pose updates from Gazebo (bridged via `ros_gz_bridge` on a
  scenario-specific topic `/world/hospital_<scenario>/pose/info`)
- Filters poses to favour actor-height entities (z ≥ 0.9 m) and rejects NaN values
- Publishes `/dynamic_obstacles` as a `geometry_msgs/PoseArray` with filtered actor poses
- Is parameterized by `actor_pose_topic`, `frame_id`, and `obstacle_radius`

The path planner consumes `/dynamic_obstacles` and maintains a separate set of
human-driven obstacles alongside event-triggered replans, allowing both stochastic
planning strategies (A\* and RRT\*) to adapt to live crowd motion.

### 4.3.7 Logging and Evaluation Module — `response_logger`

The `response_logger` node writes two files into `~/fyp_ws/logs/`:

1. `response_events.csv` — one row per ROS event, with sim-time stamp,
   topic name, and the full JSON payload. This is the audit trail for
   debugging individual trials.
2. `trial_results.csv` — one row per trial (per `alert_id`) with the
   schema:

```
alert_id, scenario, planner, run_id,
t_alert_s, t_plan_recv_s, t_arrived_s,
response_time_s, path_length_m, success,
compute_time_ms, replans
```

The logger maintains an in-memory dict keyed by `alert_id`. As alert,
route, status, and caregiver messages arrive it merges their fields into the
appropriate row and flushes a complete row to disk on either
arrival/failure or after `arrival_timeout_s` (90 s) has elapsed since the
alert. On flush it touches a sentinel file
`~/fyp_ws/logs/run_<run_id>.done` that the experiment orchestrator polls
to know the trial is complete; this avoids race conditions between the
launch-file teardown and the CSV append.

### 4.3.8 Launch / Coordination Module — `emergency_launch`

The launch file `emergency_sim.launch.py` exposes the trial-level
parameters (`planner_mode`, `scenario`, `run_id`, `seed`, `headless`) and
wires together: `gz sim` (with the scenario world), the parameter bridge
for medibot control, the actor-pose bridge (scenario-specific), the static TF
publisher, RViz 2 (in GUI mode only), and the six custom nodes:
- `emergency_publisher` (sensor/alert)
- `path_planner` (planning + human obstacle integration)
- `robot_controller` (navigation + stall detection)
- `human_obstacles` (actor pose → dynamic obstacle filter)
- `caregiver_notify` (alert & status broadcast)
- `response_logger` (CSV event recording)

## 4.4 Integration Workflow

Figure 4.1 shows the full ROS 2 graph. The data flow is:

1. `emergency_publisher` waits 4 s for Gazebo to settle, then publishes
   one `/emergency_alert` message.
2. `path_planner` subscribes to `/emergency_alert`, computes a route with
   the configured planner, and publishes the result on `/planned_route`.
3. `robot_controller` consumes `/planned_route`, materialises it as a
   `nav_msgs/Path` on `/planned_path` (for RViz), and starts driving.
4. `gz sim` consumes `/model/medibot/cmd_vel` (bridged from `/cmd_vel`),
   physically simulates the diff-drive robot, and publishes
   `/model/medibot/odometry`, which is bridged back to `/odom`.
5. If the robot stalls (e.g. a moving actor blocks the corridor), the
   controller fires `/replan_request`; the planner injects a transient
   obstacle and republishes `/planned_route`.
6. On arrival or final failure the controller publishes `/robot_status`
   with the final `t_arrived_ns` and `replans` count.
7. `response_logger` joins `/emergency_alert`, `/planned_route`, and
   `/robot_status` on `alert_id`, writes the per-trial row, and drops
   the sentinel.

> **Figure 4.1.** Node-and-topic graph of the emergency-response stack.
> Generated with `rqt_graph`. _(file: `data/figures/rqt_graph.png` —
> capture during a Day 5 trial run)_

## 4.5 Scenario Configuration

Three crowding scenarios are defined as YAML files under
`ros2_ws/src/emergency_launch/scenarios/`:

| Scenario | Moving humans | Dynamic-event budget | World file |
|----------|---------------|----------------------|------------|
| `low_crowding` | 2 actors @ 0.4 m/s | 2 | `hospital_low_crowding.sdf` |
| `moderate_crowding` | 4 actors @ 0.6 m/s | 4 | `hospital_moderate_crowding.sdf` |
| `high_crowding` | 7 actors @ 0.8 m/s | 7 | `hospital_high_crowding.sdf` |

All three share the same wall and bed layout (a 24 m × 14 m floor with a
nurse station, a corridor, and three patient rooms) and the same three
patient goal locations adjacent to each bed. The `actor_count` field of
each scenario YAML matches the number of `<actor>` blocks in the
corresponding world SDF, generated by
`worlds/_generate_scenario_worlds.py`.

> **Figure 4.2.** Plan view of the hospital world.
> _(file: `data/figures/world_overview.png` — top-down RViz screenshot)_

## 4.6 Execution and Sample Runs

### 4.6.1 Building and launching

```bash
source /opt/ros/humble/setup.bash
cd ~/Documents/<your-repo>/fyp_execution_kit
chmod +x build_and_test.sh
./build_and_test.sh
ros2 launch emergency_launch emergency_sim.launch.py \
   scenario:=moderate_crowding planner_mode:=a_star
```

### 4.6.2 Single-run trace

A representative single-trial trace from `response_events.csv` (moderate
crowding, A\*):

```
t_alert_s        topic            alert_id               replans  outcome
1759230432.131   emergency_alert  run17_alert1_84321     0        published
1759230432.155   planned_route    run17_alert1_84321     0        success, |path|=10
1759230445.802   replan_request   run17_alert1_84321     1        stall near (12,7)
1759230445.821   planned_route    run17_alert1_84321     1        success, |path|=12
1759230469.402   robot_status     run17_alert1_84321     1        arrived
```

> **Figure 4.3.** RViz visualisation of an A\* path through moderate
> crowding (sample from Day 5 trial).
> _(file: `data/figures/rviz_a_star_moderate.png`)_

> **Figure 4.4.** RViz visualisation of an RRT\* path through the same
> alert; note the more circuitous route consistent with sampling-based
> planning.
> _(file: `data/figures/rviz_rrt_star_moderate.png`)_

## 4.7 Implementation Challenges and Solutions

The following issues surfaced during integration and were resolved before
the experiment matrix was run.

1. **Missing `colcon` resource markers.** Six of the packages were
   missing their `resource/<pkg>` index files and Python `__init__.py`
   modules. `colcon build` rejected them with cryptic
   "package_index resource not found" errors. Fix: added empty marker
   files for each package and the missing `__init__.py` modules.

2. **Bridge / controller topic mismatch.** The bridge exposed
   `/model/medibot/cmd_vel` and `/model/medibot/odometry`, but the
   controller used `/cmd_vel` and `/odom`. Symptom: the robot received no
   commands and stayed stationary. Fix: added explicit `remappings=` on
   the `robot_controller` Node entry in the launch file.

3. **Planner grid did not match the world.** The original planner had a
   hand-coded 10 × 10 grid with arbitrary obstacles unrelated to the SDF
   walls, so it routinely returned paths through walls. Fix: introduced
   the `scenario_file` parameter and loaded `planner_grid.obstacles`
   from YAML, with the grid hand-mirrored from the SDF wall + bed
   coordinates.

4. **No `map → odom` transform.** Without a TF link RViz refused to
   render the planned `Path`. Fix: added a `tf2_ros
   static_transform_publisher` emitting an identity transform from `map`
   to `odom`.

5. **RRT\* failure rate in dense scenarios.** The lightweight RRT\*
   prototype (in `scripts/run_scenario.py`) had failed in moderate and
   high crowding. The ROS 2 implementation initially did the same. Fix:
   raised `rrt_max_iterations` to 2000, dropped `rrt_step_size` to 0.8,
   and raised `rrt_goal_sample_rate` to 0.25; success-rate jumped above
   acceptable thresholds (Chapter Five §5.3).

6. **Animated actors required a model-cache populated from Gazebo Fuel.**
   `<actor>` blocks reference the standard `walk.dae` skin from
   `fuel.gazebosim.org`. Resolved by running the launch once with
   internet, after which the model is cached under `~/.gz/fuel/`. A
   static fallback set of cylinder humans is documented in the README
   for offline use.

7. **Actor pose bridge topic naming.** The Gazebo actor pose topic varies
   by world name (e.g., `/world/hospital_low_crowding/pose/info` vs
   `/world/hospital_high_crowding/pose/info`). Fix: made the actor-pose topic
   name scenario-dependent in the launch file using `ConcatSubstitution`,
   and the `human_obstacles` node accepts it as a configurable parameter.

8. **Human obstacle filtering false positives.** Initially, the `human_obstacles` node
   subscribed to all Gazebo entities and mapped them blindly onto the planner grid,
   including static models and light sources. This caused spurious obstacles to appear
   mid-path. Fix: added a z-height filter (min z ≥ 0.9 m) and NaN rejection to isolate
   actor-like entities.

9. **Caregiver notification cooldown interaction with replans.** Early versions
   published one caregiver notification per replan event, causing alert spam. Fix:
   implemented a per-caregiver cooldown (default 10 s) so only the first alert and
   status changes at major milestones trigger notifications, reducing false-positive
   urgency signals.

## 4.8 Chapter Summary

The six-package ROS 2 stack runs end-to-end in Gazebo Sim Harmonic, implementing
the full three-layer emergency-response architecture:

1. **Layer 1 (IoT Sensing)**: `emergency_publisher` publishes `/emergency_alert`
   from a simulated wearable with patient location and severity.
2. **Layer 2 (Robot Response)**: `path_planner` and `robot_controller` compute
   and execute routes, consuming `/dynamic_obstacles` from human actors and
   triggering replans on stall events.
3. **Layer 3 (Caregiver Notification)**: `caregiver_notify` broadcasts alerts
   and status to `/caregiver_notify` and `/caregiver_status` with cooldown
   anti-spam measures.

Supporting modules:
- `human_obstacles`: bridges animated actor poses to dynamic obstacle grid cells.
- `response_logger`: joins alert, route, and status messages on `alert_id` and
  writes per-trial CSV rows for evaluation.

An emergency alert flows from the simulated wearable through the planner, the
controller, and the bridged Gazebo robot, with stall detection driving a
replan loop that integrates both event-triggered obstacles (transient) and
human-driven obstacles (continuous). Every trial produces a per-row CSV entry
capturing all timestamps needed to compute response time, planning time, path
length, replan count, and success status. The system is now ready for the
quantitative comparative evaluation reported in Chapter Five.

---

## Appendix B – Reproducibility

```bash
sudo apt update
sudo apt install -y \
   ros-humble-ros-base \
   ros-humble-ros-gz-bridge \
   ros-humble-ros-gz-sim \
   ros-humble-rviz2 \
   ros-humble-tf2-ros \
   ros-humble-nav-msgs \
   ros-humble-geometry-msgs \
   python3-colcon-common-extensions \
   python3-rosdep \
   python3-yaml
sudo rosdep init || true
rosdep update
mkdir -p ~/fyp_ws/src
cp -r fyp_execution_kit/ros2_ws/src/. ~/fyp_ws/src/
cd ~/fyp_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
ros2 launch emergency_launch emergency_sim.launch.py
```
