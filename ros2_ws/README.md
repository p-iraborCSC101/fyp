# ROS 2 Workspace — Stochastic Emergency-Response Robot

This workspace contains five ROS 2 Jazzy packages that together implement
the IoT-enabled mobile-robot emergency-response pipeline described in
Chapter 4 of the dissertation. The robot lives in a Gazebo Sim Harmonic
two-room hospital world with scripted moving "human" actors.

## Packages

| Package | Node executable | Purpose |
|---------|-----------------|---------|
| `emergency_sensing` | `sensor_simulator`, `alert_fusion` | Publishes camera/heart-rate/motion sensor topics and fuses them into `/emergency_alert` |
| `path_planner` | `path_planner` | Runs A\* or RRT\* over the scenario grid, supports `/replan_request` with dynamic-obstacle injection |
| `robot_control` | `robot_controller` | Proportional waypoint follower; detects stalls and fires `/replan_request`; reports arrival on `/robot_status` |
| `response_logger` | `response_logger` | Joins alert / route / status by `alert_id`; writes `trial_results.csv` and `response_events.csv`; drops a per-trial sentinel |
| `emergency_launch` | _(launch + assets)_ | `emergency_sim.launch.py`, `worlds/*.sdf`, `scenarios/*.yaml`, `rviz/emergency_nav.rviz` |

## Setup on Ubuntu 24.04 (one-time)

```bash
sudo apt update
sudo apt install -y \
    ros-jazzy-desktop \
    ros-jazzy-ros-gz-bridge ros-jazzy-ros-gz-sim \
    ros-jazzy-rviz2 ros-jazzy-tf2-ros \
    ros-jazzy-nav-msgs ros-jazzy-geometry-msgs \
    python3-colcon-common-extensions python3-yaml
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

Then copy this workspace into `~/fyp_ws/src` (or symlink it):

```bash
mkdir -p ~/fyp_ws/src
cp -r fyp_execution_kit/ros2_ws/src/. ~/fyp_ws/src/
cd ~/fyp_ws
colcon build --symlink-install
source install/setup.bash
```

## One-shot demo run (GUI)

```bash
ros2 launch emergency_launch emergency_sim.launch.py \
    scenario:=moderate_crowding \
    planner_mode:=a_star
```

Expected:
- Gazebo Sim window opens with the 2-room hospital and 4 walking actors.
- RViz 2 opens and displays the planned `Path` after ~4 seconds.
- The blue `medibot` cube drives from the nurse station to one of the three
  beds; on arrival it publishes `/robot_status` with `status: arrived`.

Switch planners with `planner_mode:=rrt_star`. Switch scenarios with
`scenario:=low_crowding | moderate_crowding | high_crowding`.

## Headless batch experiment (180 trials)

```bash
source /opt/ros/jazzy/setup.bash
source ~/fyp_ws/install/setup.bash
python3 fyp_execution_kit/scripts/run_ros2_experiment.py \
    --runs 30 --seed 42 --headless
```

This spawns the launch stack 180 times (3 scenarios × 2 planners × 30
runs), waits for each per-trial sentinel, then copies the aggregated
`~/fyp_ws/logs/trial_results.csv` into
`fyp_execution_kit/data/raw_logs/experiment_runs_ros2.csv`.

Then aggregate and plot:

```bash
python3 fyp_execution_kit/scripts/evaluate_metrics.py \
    --infile ../data/raw_logs/experiment_runs_ros2.csv
python3 fyp_execution_kit/scripts/plot_results.py
```

The summary CSV ends up at
`fyp_execution_kit/data/processed/results_summary.csv` and the figures
under `fyp_execution_kit/data/figures/`.

## ROS 2 topics

| Topic | Type | Direction |
|-------|------|-----------|
| `/sensor/camera_fall` | `std_msgs/String` (JSON) | sensor_simulator → alert_fusion |
| `/sensor/heart_rate` | `std_msgs/String` (JSON) | sensor_simulator → alert_fusion |
| `/sensor/motion_state` | `std_msgs/String` (JSON) | sensor_simulator → alert_fusion |
| `/sensor_dashboard` | `visualization_msgs/MarkerArray` | sensor_dashboard → RViz |
| `/emergency_alert` | `std_msgs/String` (JSON) | alert_fusion → planner, logger |
| `/planned_route` | `std_msgs/String` (JSON) | planner → controller, logger |
| `/planned_path` | `nav_msgs/Path` | controller → RViz |
| `/replan_request` | `std_msgs/String` (JSON) | controller → planner |
| `/robot_status` | `std_msgs/String` (JSON) | controller → logger |
| `/cmd_vel` | `geometry_msgs/Twist` | controller → bridge → Gazebo |
| `/odom` | `nav_msgs/Odometry` | Gazebo → bridge → controller |
| `/clock` | `rosgraph_msgs/Clock` | Gazebo → bridge → all nodes |

## Worlds and scenario YAMLs

`worlds/hospital_world.sdf` is the static base hospital (2 rooms). The three
scenario worlds are generated from it by:

```bash
python3 ros2_ws/src/emergency_launch/worlds/_generate_scenario_worlds.py
```

This emits `hospital_low_crowding.sdf`, `hospital_moderate_crowding.sdf`,
`hospital_high_crowding.sdf`. Edit the `SCENARIOS` dict in the generator
to change actor count, speed, or waypoints.

If Gazebo GUI is unavailable in a VM, run headless and visualize in RViz:

```bash
export LIBGL_ALWAYS_SOFTWARE=1
ros2 launch emergency_launch emergency_sim.launch.py headless:=true
rviz2 -d ~/fyp_ws/install/emergency_launch/share/emergency_launch/rviz/emergency_nav.rviz
```

The first launch with internet downloads the standard `walk.dae` skin
from Gazebo Fuel and caches it under `~/.gz/fuel/`. For offline use,
copy that cache directory across machines, or replace the `<actor>`
blocks with static cylinders (see `_generate_scenario_worlds.py` skin
URL — set the `SKIN_URI` to a local file path or empty).

## Logs

All logs land under `~/fyp_ws/logs/`:
- `response_events.csv` — full audit trail (one row per ROS event)
- `trial_results.csv` — one row per trial; this is the file Chapter 5
  plots from
- `run_<run_id>.done` — sentinel file, dropped by the logger when each
  trial completes; the orchestrator polls these
