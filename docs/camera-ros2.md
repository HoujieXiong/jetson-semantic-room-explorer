# Femto Mega ROS 2 bring-up

Current status: driver source downloaded and message package built; camera
driver build `BLOCKED` by missing dependencies. Live ROS camera topics and
rosbag recording/replay have not been verified.

## Inspected source and environment

- Official source: <https://github.com/orbbec/OrbbecSDK_ROS2>, branch `v2-main`.
- Pinned commit: `8e7cad2bfa2c4a6ac4e779be99c64e72166043af` (2026-08-07).
- Wrapper and bundled ARM64 SDK: 2.9.3. The bundled library's version API was
  called locally; source CMake selects this library on aarch64.
- Workspace: `/home/jeffx/projects/femto_ros2_ws`.
- The wrapper declares Apache-2.0; its bundled SDK third-party license directory
  remains with the checkout. No third-party source or binaries are copied into
  this project repository.
- ROS 2 Humble, system Python 3.10.12, GCC 11.4.0, colcon and CMake are installed.
  `rclpy`, `rosbag2_py`, `sensor_msgs`, `cv_bridge` and `tf2_ros` import successfully;
  the sqlite3 bag reader/writer is registered.
- The camera remains enumerated at USB 5000 Mbit/s. This check did not stream it.
- Existing native Python capture continues to use its separate `.venv` and SDK
  2.8.6. No native capture code or system packages were changed during this attempt.

The official Femto Mega launch defaults already select 1280x720 MJPG color and
640x576 Y16 depth at 30 FPS. Registration, IR, point-cloud output and timestamp
settings still need explicit selection and hardware validation for M3. Source
inspection also shows the ROS depth publisher converts SDK counts to uint16
millimeters; verify that contract on actual messages before using it downstream.

## Download and build

The authorized download command was:

```bash
mkdir -p /home/jeffx/projects/femto_ros2_ws/src
git clone --depth 1 --branch v2-main --single-branch https://github.com/orbbec/OrbbecSDK_ROS2.git /home/jeffx/projects/femto_ros2_ws/src/OrbbecSDK_ROS2
```

Record the commit after cloning; a moving branch does not reproduce a pinned
build by itself. The current checkout remains unmodified at the commit above.

Build using system ROS Python and two compiler jobs on the 8 GB Jetson:

```bash
source /opt/ros/humble/setup.bash
cd /home/jeffx/projects/femto_ros2_ws
MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --executor sequential --packages-up-to orbbec_camera --event-handlers console_direct+ desktop_notification- --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
```

`orbbec_camera_msgs` built in 1 min 37 s. Its Python imports and an independent
ROS serialization/deserialization round trip passed. `orbbec_camera` failed
during CMake configuration because `backward_rosConfig.cmake` was absent.
The first colcon process did not terminate after CMake failed and was interrupted;
a retry with desktop notifications disabled exited cleanly with code 1 in 2.79 s.
This command disables upstream lint tests for the initial build; no driver
hardware acceptance or test-suite pass is implied.

## Missing dependencies

Source CMake/header inspection found these six missing build dependencies.
Existing `libdw-dev`, `libssl-dev`, OpenGL development files, OpenCV and the core
ROS dependencies are already available. APT simulation on 2026-09-10 proposed
exactly six new packages, zero upgrades and zero removals.

Proposed installation, **awaiting user approval**:

```bash
sudo apt-get install --no-install-recommends ros-humble-backward-ros ros-humble-camera-info-manager ros-humble-camera-calibration-parsers ros-humble-image-publisher ros-humble-diagnostic-updater nlohmann-json3-dev
```

Recheck the transaction before installing if package indexes or the system have
changed. This targeted list covers the inspected build failure and remaining
missing CMake/header requirements; additional runtime requirements are unverified.

Evidence: `data/outputs/femto_ros2/bringup_20260910/` (ignored), containing
`local_environment.json`, `source_and_build.json`, `build_initial.log`,
`build_headless.log` and `dependency_plan.txt`. Upstream per-package build logs
remain under the isolated workspace's `log/` directory.

Next action: install the six dependencies after approval and resume the pinned
driver build, then continue the M3 camera/rosbag acceptance in `AGENTS.md`.
