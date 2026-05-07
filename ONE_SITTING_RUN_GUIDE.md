# One-Sitting Run Guide (HP Desktop + Ubuntu 22.04 VM)

Goal: finish setup + experiments + analysis + chapter updates in one sitting.
Estimated time: 6 to 9 hours depending on VM speed.

---

## 0) Prep (10 minutes)

- Download Ubuntu 22.04 ISO: https://ubuntu.com/download/desktop
- Create a new VirtualBox VM (recommended):
  - RAM: 8 GB
  - CPU: 2 to 4 cores
  - Disk: 50 GB (VDI, dynamically allocated)
  - Boot order: Optical first
  - EFI: OFF (recommended)

---

## 1) Install Ubuntu (30 to 45 minutes)

- Boot VM from the ISO and choose Install Ubuntu.
- Use Normal installation.
- Enable third-party software (recommended).
- Create your user account and finish install.
- Reboot into Ubuntu.

---

## 2) Install ROS 2 Humble + Gazebo + tooling (45 to 60 minutes)

Open a terminal in Ubuntu and run:

```bash
sudo apt update
sudo apt install -y \
  git curl gnupg lsb-release \
  python3-pip python3-rosdep python3-venv python3-yaml

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

sudo rosdep init || true
rosdep update

echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

---

## 3) Clone the project from GitHub (10 minutes)

```bash
cd ~/Documents

git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>/fyp_execution_kit
```

---

## 4) Build and quick smoke test (20 to 40 minutes)

```bash
chmod +x build_and_test.sh
./build_and_test.sh
```

Quick run to confirm the stack starts:

```bash
ros2 launch emergency_launch emergency_sim.launch.py headless:=true
```

Let it run for 30 to 60 seconds, then stop with Ctrl+C.

If you see errors about OpenGL, keep running in headless mode.

---

## 5) Full experiment run (2 to 4 hours)

```bash
cd ~/Documents/<your-repo>/fyp_execution_kit

python3 scripts/run_ros2_experiment.py \
  --runs 30 \
  --scenarios low_crowding,moderate_crowding,high_crowding
```

If time is tight, start with 10 runs per scenario:

```bash
python3 scripts/run_ros2_experiment.py \
  --runs 10 \
  --scenarios low_crowding,moderate_crowding,high_crowding
```

---

## 6) Generate metrics and figures (30 to 45 minutes)

```bash
cd ~/Documents/<your-repo>/fyp_execution_kit

python3 scripts/evaluate_metrics.py
python3 scripts/plot_results.py
```

Outputs:
- data/processed/results_summary.csv
- data/figures/*.png

---

## 7) Fill Chapter 5 results (45 to 60 minutes)

Open:
- templates/chapter5_draft.docx

Replace the placeholder values [ x.xx ] using:
- data/processed/results_summary.csv

Also update:
- Figure captions (if needed)
- Any text claims in Section 5.4 and 5.5

---

## 8) Final check (15 minutes)

- Confirm figures exist in data/figures/
- Confirm results_summary.csv is updated
- Save the final DOCX files

---

## Quick troubleshooting

- If the VM boots into a UEFI shell, disable EFI in VirtualBox settings.
- If Gazebo GUI fails, run headless:
  ```bash
  ros2 launch emergency_launch emergency_sim.launch.py headless:=true
  ```
- If ROS 2 commands are missing:
  ```bash
  source /opt/ros/humble/setup.bash
  ```

---

## Optional: Compress time further

- Run 10 trials per scenario first to validate output.
- If results look reasonable, scale to 30 runs.
