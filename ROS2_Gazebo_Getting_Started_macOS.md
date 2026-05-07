# Running the FYP stack on Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Sim Harmonic

> _Note: this project targets native Ubuntu 24.04. macOS native install of
> ROS 2 + Gazebo Sim is not supported here. Run the project inside Ubuntu
> (bare metal, dual-boot, or a VM such as UTM/Parallels)._

## 1. Install ROS 2 Jazzy + Gazebo Sim Harmonic

```bash
sudo apt update && sudo apt install -y software-properties-common curl gnupg lsb-release
sudo add-apt-repository universe -y
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
    | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update
sudo apt install -y \
    ros-jazzy-desktop \
    ros-jazzy-ros-gz-bridge ros-jazzy-ros-gz-sim \
    ros-jazzy-rviz2 ros-jazzy-tf2-ros \
    ros-jazzy-nav-msgs ros-jazzy-geometry-msgs \
    python3-colcon-common-extensions python3-rosdep python3-yaml
sudo rosdep init || true
rosdep update
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

Confirm both are installed:

```bash
ros2 --version
gz sim --versions
```

## 2. Drop the project workspace into ~/fyp_ws

```bash
mkdir -p ~/fyp_ws/src
cp -r fyp_execution_kit/ros2_ws/src/. ~/fyp_ws/src/
cd ~/fyp_ws
colcon build --symlink-install
source install/setup.bash
```

If `colcon build` fails with "package_index resource not found" for any
package, double-check that each `src/<pkg>/resource/<pkg>` file exists
(empty file is fine) and that each `src/<pkg>/<pkg>/__init__.py` exists.

## 3. Smoke-test the demo launch

```bash
ros2 launch emergency_launch emergency_sim.launch.py \
    scenario:=low_crowding planner_mode:=a_star
```

Expect, in order:
2. Gazebo Sim window with the hospital world (16 m × 14 m, 2 rooms,
  2 walking actors).
3. RViz 2 window with the medibot and (after ~4 s) a green planned `Path`.
4. The blue medibot drives from the nurse station out to one of the beds
  and stops there.

If you update the base hospital world, regenerate the scenario worlds:

```bash
python3 ~/fyp_ws/src/emergency_launch/worlds/_generate_scenario_worlds.py
```

If the Gazebo GUI fails in a VM, run headless and visualize in RViz:

```bash
export LIBGL_ALWAYS_SOFTWARE=1
ros2 launch emergency_launch emergency_sim.launch.py headless:=true
rviz2 -d ~/fyp_ws/install/emergency_launch/share/emergency_launch/rviz/emergency_nav.rviz
```

## 4. Run the full experiment matrix (180 trials)

```bash
python3 fyp_execution_kit/scripts/run_ros2_experiment.py --runs 30 --seed 42
```

This is roughly 75–180 minutes of wall-clock time depending on machine
speed and per-trial timeout settings. Use `--gui` to keep the GUI open
for the first few trials while you sanity-check.

## 5. Aggregate and plot

```bash
python3 fyp_execution_kit/scripts/evaluate_metrics.py \
    --infile ../data/raw_logs/experiment_runs_ros2.csv \
    --outfile ../data/processed/results_summary.csv
python3 fyp_execution_kit/scripts/plot_results.py
```

Outputs:
- `fyp_execution_kit/data/processed/results_summary.csv` — the table for
  Chapter 5 §5.3.
- `fyp_execution_kit/data/figures/response_time_comparison.png`
- `fyp_execution_kit/data/figures/success_rate_comparison.png`

## 6. Capturing screenshots / video for Chapter 4

While a single trial is running:
- `gz sim` window: take a top-down screenshot for Figure 4.2.
- RViz 2 window: take screenshots of A\* and RRT\* planned paths for
  Figures 4.3 / 4.4.
- Use `rqt_graph` to export the node graph for Figure 4.1.
- Use `ros2 bag record -a -o demo_bag.bag` to capture one full
  representative run for the appendix.

Optional helper script (records the current display + a screenshot):

```bash
chmod +x fyp_execution_kit/scripts/capture_demo.sh
fyp_execution_kit/scripts/capture_demo.sh 30
```

## 7. Common issues

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Robot does not move | Bridge / topic mismatch | Confirm the launch file remaps `/cmd_vel` and `/odom`; check `ros2 topic list` shows `/model/medibot/cmd_vel` |
| RViz says "no transform map → odom" | Static TF publisher missing | Ensure `tf2_ros static_transform_publisher` node is in the launch file |
| Planner returns a path through a wall | Scenario YAML obstacles not loaded | Check `path_planner` log for `Loaded scenario:` line; verify `scenario_file` parameter resolves to an existing file |
| Actors render as `?` placeholders | Fuel skin not cached | Run with internet once; confirm `~/.gz/fuel/` is populated |
| RRT\* often fails | Too few iterations | Bump `rrt_max_iterations` (passed in `emergency_sim.launch.py`) |
