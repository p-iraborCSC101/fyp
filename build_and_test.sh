#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$ROOT_DIR/ros2_ws"

if [[ ! -d "$WS_DIR/src" ]]; then
  echo "Workspace not found: $WS_DIR/src"
  exit 1
fi

source /opt/ros/humble/setup.bash

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
