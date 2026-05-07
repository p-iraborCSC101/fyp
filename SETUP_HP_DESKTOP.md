# HP Desktop Setup (Ubuntu 22.04 + ROS 2 Humble + Gazebo Harmonic)

This guide assumes you will run the project on an HP desktop with Ubuntu 22.04.
If you are using a different OS, tell me and I will adapt the steps.

## 1) System packages

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  curl \
  git \
  gnupg \
  lsb-release \
  python3-pip \
  python3-rosdep \
  python3-venv \
  python3-yaml
```

## 2) Install ROS 2 Humble (Ubuntu 22.04)

```bash
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y \
  ros-humble-ros-base \
  ros-humble-ros-gz-bridge \
  ros-humble-ros-gz-sim \
  ros-humble-rviz2 \
  ros-humble-tf2-ros \
  ros-humble-nav-msgs \
  ros-humble-geometry-msgs \
  python3-colcon-common-extensions
```

Initialize rosdep once per machine:

```bash
sudo rosdep init || true
rosdep update
```

Add ROS 2 to your shell:

```bash
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

## 3) Get the project from GitHub

On your current laptop (the source machine):

```bash
cd /path/to/fyp

git init
# Or skip this if already a git repo.

# Add remote and push

git remote add origin https://github.com/<your-username>/<your-repo>.git

git add .

git commit -m "Initial project sync"

git branch -M main

git push -u origin main
```

On the HP desktop:

```bash
cd ~

git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

## 4) Build and smoke-test

```bash
cd fyp_execution_kit
chmod +x build_and_test.sh
./build_and_test.sh
```

If you are running without a GPU or want to avoid the GUI:

```bash
ros2 launch emergency_launch emergency_sim.launch.py headless:=true
```

## 5) Optional: Gazebo rendering notes

If GUI issues appear on the HP desktop, try:

```bash
export LIBGL_ALWAYS_SOFTWARE=1
```

You can keep using headless mode + RViz if the GUI is unstable.
