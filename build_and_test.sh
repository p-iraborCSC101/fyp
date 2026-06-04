#!/usr/bin/env bash
# Note: no `-u` (nounset) — ROS 2 setup.bash references unset vars like
# AMENT_TRACE_SETUP_FILES and would abort under nounset.
set -eo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$ROOT_DIR/ros2_ws"

if [[ ! -d "$WS_DIR/src" ]]; then
  echo "Workspace not found: $WS_DIR/src"
  exit 1
fi

# Source ROS 2 (auto-detect the installed distro: Humble on 22.04, Jazzy on 24.04, ...)
if [[ -n "${ROS_DISTRO:-}" && -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]]; then
  source "/opt/ros/${ROS_DISTRO}/setup.bash"
else
  ROS_SETUP="$(ls -d /opt/ros/*/setup.bash 2>/dev/null | head -n1 || true)"
  if [[ -z "$ROS_SETUP" ]]; then
    echo "ERROR: No ROS 2 install found in /opt/ros/."
    echo "Install ROS 2 first (Humble for Ubuntu 22.04, Jazzy for Ubuntu 24.04)."
    exit 1
  fi
  source "$ROS_SETUP"
fi
echo "Using ROS 2 distro: ${ROS_DISTRO:-unknown}"

cd "$WS_DIR"

# Install dependencies from package.xml (if rosdep available)
if command -v rosdep >/dev/null 2>&1; then
  rosdep install --from-paths src --ignore-src -r -y
fi

colcon build --symlink-install

# Smoke test: list key nodes (no GUI)
source install/setup.bash
ros2 pkg list | grep -E "(emergency_sensing|path_planner|robot_control|response_logger|emergency_launch|caregiver_notify|human_obstacles)" || true

echo "Build complete. To run:"
echo "  ros2 launch emergency_launch emergency_sim.launch.py headless:=true"
