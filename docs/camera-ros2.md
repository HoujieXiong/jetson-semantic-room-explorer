# Femto Mega ROS 2 bring-up

Current status: driver build and the live RGB-D ROS contract are `VERIFIED` on
this Jetson. A 59.39-second stationary recording and exact driver-stopped replay
with simulated time are also `VERIFIED`. Room-walk recording and SLAM remain
unverified.

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
- Femto Mega firmware 1.3.1, USB 5000 Mbit/s. Actual source profiles were
  enumerated and streamed with the driver SDK.
- Existing native Python capture continues to use its separate `.venv` and SDK
  2.8.6. No native capture code or system packages were changed.

The selected source profiles are 1280x720 MJPG color and 640x576 Y16 depth at
15 FPS. Hardware D2C produces 1280x720 depth in the undistorted color projection.
`enable_color_undistortion=true` makes RGB match that projection. The upstream
`image_raw` topic names are retained, but the published RGB is undistorted and
the published depth is registered; neither is a raw sensor image.

| Topic | Message contract |
| --- | --- |
| `/camera/color/image_raw` | 1280x720 `rgb8`, stride 3840; undistorted RGB |
| `/camera/depth/image_raw` | 1280x720 `16UC1`, stride 2560; color-camera axial Z in mm, zero invalid |
| `/camera/color/camera_info` | Matching undistorted color calibration |
| `/camera/depth/camera_info` | Exactly the same K/D/R/P, model and grid as color |
| `/tf_static` | `camera_link` to depth/color body and optical frames |

All image/info frame IDs are `camera_color_optical_frame`. Optical axes are
right/down/forward, with meters in TF. CameraInfo focal lengths are
fx=750.301940918, fy=749.948059082; principal point cx=634.142395020,
cy=335.869262695. D has eight zeros and the SDK labels the model `plumb_bob`.
The node converts SDK depth counts through `getValueScale()` before publishing
uint16 millimeters. Physical center measurements verify this interpretation
against the user's coarse 2–3 m front-panel-to-wall reference.

`time_domain=global` preserves the SDK's host-clock-mapped acquisition timestamp
in ROS headers, rather than callback receipt time. The driver's timestamp CSV
also preserves device, global and system timestamps and source frame indices.
Static TF is checked at the image timestamps. Camera topics use reliable,
volatile QoS; `/tf_static` uses reliable, transient-local durability so late
subscribers can recover the transforms. Queue behavior and subscriber start/stop
edges are measured separately; reliability alone does not prove zero frame loss.

## Reproduce the isolated build

The user approved the six missing dependencies and continued M3 work. Passwordless
sudo was unavailable, so the packages were downloaded through APT and extracted
under the user-owned workspace; no system package or maintainer script was run.
The existing Python camera environment remains separate.

```bash
mkdir -p ~/projects/femto_ros2_ws/{src,debs,deps}
cd ~/projects/femto_ros2_ws/src
git clone --branch v2-main https://github.com/orbbec/OrbbecSDK_ROS2.git
git -C OrbbecSDK_ROS2 checkout 8e7cad2bfa2c4a6ac4e779be99c64e72166043af
git -C OrbbecSDK_ROS2 apply ~/projects/jetson-semantic-room-explorer/patches/orbbec_ros2_rgbd_contract.patch
git clone --branch humble https://github.com/ros-perception/vision_opencv.git
git -C vision_opencv checkout 9800f67cea477c44cfb64e349854bcb6a09dc9ce
cd ../debs
apt-get download ros-humble-backward-ros ros-humble-camera-info-manager ros-humble-camera-calibration-parsers ros-humble-image-publisher ros-humble-diagnostic-updater nlohmann-json3-dev
for package in *.deb; do dpkg-deb -x "$package" ../deps; done
cd ..
source /opt/ros/humble/setup.bash
export CMAKE_PREFIX_PATH="$PWD/deps/opt/ros/humble:$PWD/deps/usr:$CMAKE_PREFIX_PATH"
export LD_LIBRARY_PATH="$PWD/deps/opt/ros/humble/lib:$LD_LIBRARY_PATH"
export CPLUS_INCLUDE_PATH="$PWD/deps/usr/include"
MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --base-paths src --executor sequential --packages-up-to orbbec_camera --allow-overriding cv_bridge --event-handlers console_direct+ desktop_notification- --cmake-clean-cache --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DOpenCV_DIR=/usr/lib/cmake/opencv4
```

`--base-paths src` prevents colcon from mistaking extracted dependency metadata for
source packages. Disabling desktop notifications avoids the observed post-failure
colcon hang. `BUILD_TESTING=OFF` skips upstream build-time tests; it is not a
hardware acceptance claim. Two compiler jobs bound memory use on the 8 GB Jetson.

The system ROS `cv_bridge` links Ubuntu OpenCV 4.5.4, while this Jetson's C++
OpenCV development package selects NVIDIA OpenCV 4.8.0. Building the same Humble
`cv_bridge` 3.2.1 API locally against 4.8 avoids loading both versions in the
camera process. Clear CMake's cache after adding that overlay: otherwise a prior
`cv_bridge_DIR` can keep selecting the system library. `vision_opencv` source
licenses remain in its unmodified checkout. The driver carries only the patch
described below.

The initial complete build passed: three packages in 10 min 10 s, including
9 min 58 s for the camera package. Runtime `ldd` with the environment helper
selects the local cv_bridge and only OpenCV `.408`, with no missing libraries.
The upstream profile utility enumerated the required RGB/depth profiles but then
aborted while opening the IMU. The unpatched driver similarly failed before
publishing any images; the bounded checker detected zero messages and failed.
Both outcomes are retained as failures, not successful hardware verification.

`patches/orbbec_ros2_rgbd_contract.patch` adds a six-line guard before SDK
sensor construction. It skips only accelerometer/gyroscope streams explicitly
disabled by parameters. Synchronized IMU output already enables both flags in
the upstream parameter parser. Requested IMU streams still take the original
path and require proper USB/HID permissions. This permits the RGB-D-only task
to use the existing video access without changing system device permissions.
IMU streaming and enabling IMU dynamically remain outside this verification.
The patch also normalizes the Eigen quaternion constructed from SDK extrinsics:
the initial published depth-to-color-frame quaternion had norm 0.999275748,
which failed the explicit unit-quaternion check. The SDK calibration matrix is
retained unchanged; the ROS rotation representation must have unit norm.

Extracted package versions on this Jetson:

| Package | Version |
| --- | --- |
| ros-humble-backward-ros | 1.0.8-2jammy.20260306.212100 |
| ros-humble-camera-calibration-parsers | 3.1.13-1jammy.20260725.161705 |
| ros-humble-camera-info-manager | 3.1.13-1jammy.20260725.162258 |
| ros-humble-diagnostic-updater | 4.0.7-1jammy.20260725.155003 |
| ros-humble-image-publisher | 3.0.9-1jammy.20260725.191932 |
| nlohmann-json3-dev | 3.10.5-2 |

The saved `.deb` files and `local_dependencies.json` preserve their SHA-256 hashes.
APT commands without version suffixes resolve the available repository versions;
they do not promise identical future binaries. Existing libdw, OpenSSL, Boost
Python, OpenGL and core ROS development dependencies were reused.

Evidence root: `data/outputs/femto_ros2/bringup_20260910/` (ignored). It retains the
initial missing-dependency failure, sudo failure, dependency plan/downloads,
interrupted mixed-OpenCV attempts, and the final build log. Source, dependencies
and generated build/install/log files live outside this project repository.

## Run the camera contract checks

Use a fresh system-Python shell, outside the native-capture virtual environment:

```bash
cd ~/projects/jetson-semantic-room-explorer
source scripts/femto_ros2_env.bash
mkdir -p data/outputs/femto_ros2
ros2 run orbbec_camera orbbec_camera_node --ros-args -r __ns:=/camera -r __node:=camera --params-file config/femto_rgbd.yaml -p frame_timestamp_csv_file:="$PWD/data/outputs/femto_ros2/sensor_timestamps.csv"
```

The environment helper selects the local workspace/dependencies and uses
localhost-only ROS domain 42. Source it in every
camera, recorder, checker and playback terminal. Keep this environment separate
from `.venv` native capture. End the driver with Ctrl-C and check its exit status.

The explicit source profiles are 1280x720 MJPG color and 640x576 Y16 depth at
15 FPS. Hardware D2C registration and explicit RGB undistortion target the same
undistorted color grid. Stream synchronization and complete framesets are enabled.
IR, IMU, point clouds and the optional hole-filling filter are disabled.
`config/femto_rgbd.yaml` owns these selections; the checker deliberately rejects a different measured pixel grid, encoding, calibration or optical frame.

After startup, inspect a bounded live interval from another sourced terminal:

```bash
python3 tests/check_femto_rosbag.py --duration 15 --output data/outputs/femto_ros2/live.json
```

The checker requires positive, increasing source stamps, one-to-one RGB-D
matching within 5 ms, Image/CameraInfo timestamp agreement, matching calibration,
uint16 millimeter depth with zero invalid, a valid center within the supplied
2–3 m wall interval, and a static camera-to-optical TF chain at image timestamps.
It reports rates and timing distributions, QoS, invalid-depth coverage and
recording-boundary mismatches, allowing at most two edge frames per comparison.
A stream that stops early fails rather than being excused as a boundary.
This fixed-scene acceptance tool must be revised before use on a moving recording with a different physical reference.

Record about 60 seconds (Ctrl-C stops recording and flushes metadata):

```bash
ros2 bag record -o data/outputs/femto_ros2/stationary --compression-mode message --compression-format zstd --compression-threads 2 --compression-queue-size 60 --max-cache-size 100000000 /camera/color/image_raw /camera/color/camera_info /camera/depth/image_raw /camera/depth/camera_info /tf_static
python3 tests/check_femto_rosbag.py --bag data/outputs/femto_ros2/stationary --output data/outputs/femto_ros2/stationary_bag.json
```

Stop the driver. Start the checker before the player in separate sourced
terminals, so it receives the complete playback:

```bash
python3 tests/check_femto_rosbag.py --reference data/outputs/femto_ros2/stationary_bag.json --duration 95 --output data/outputs/femto_ros2/stationary_replay.json
ros2 bag play data/outputs/femto_ros2/stationary --clock 30 --delay 2 --read-ahead-queue-size 40 --wait-for-all-acked 5000 --disable-keyboard-controls
```

Replay acceptance compares each topic's exact serialized message count and
SHA-256 digest with the bag, including image bytes, headers, calibration and TF.
The subscriber sets `use_sim_time=true` and checks an advancing `/clock`.
Reports and first-frame NumPy arrays are saved under the ignored output tree;
existing reports are never overwritten. Any contract violation exits nonzero.

Focused offline verification:

```bash
source /opt/ros/humble/setup.bash
python3 -m unittest discover -s tests/ros2 -v
```

## Measured stationary recording

On 2026-09-10, the 15 FPS configuration recorded 59.390958627 s to a 1.055 GB
SQLite/zstd bag. The camera remained fixed, with no ML/SLAM workload running.

| Measurement | Color | Registered depth |
| --- | --- | --- |
| Images and matching CameraInfo | 887 each | 887 each |
| Header-derived rate | 14.9230 Hz | 14.9231 Hz |
| Header period median / P95 / max | 67.011 / 67.170 / 67.571 ms | 67.011 / 67.150 / 67.354 ms |
| Bag receipt minus global header median / P95 / max | 205.502 / 213.604 / 223.133 ms | 209.756 / 217.464 / 228.022 ms |
| Source callback to publication median / P95 | 30.654 / 33.747 ms | 31.485 / 34.732 ms |

- All 887 pairs matched; no unmatched images/CameraInfo, source-index gaps or
  source timestamp intervals above 1.5 nominal frame periods inside the bag.
  The subscriber handoff before recording explains the separate startup
  `ROS_PUBLISH dropped=15` messages; no SDK drops were logged in this run.
- All recorded CameraInfo headers exactly equal corresponding SDK-global CSV
  stamps. RGB-D device skew median/P95/max: 531/654.7/955 us; published global
  skew: 3628/3972.1/4197 us. The SDK's clock mapping adds a measurable difference;
  global headers were not replaced with device or receipt timestamps.
- Center depth: 2.359–2.363 m (median 2.361 m); valid depth coverage:
  73.188–73.669%. This verifies coarse metric units, not absolute accuracy.
- K/D/R/P, image grids and optical frame IDs matched throughout. Four static
  transforms were recorded in one `/tf_static` message; quaternion norms ranged
  from 0.9999999944 to 1.0, and the required chain resolved at observation times.
- Driver descriptors stayed at 40; RSS was 97632–99640 KiB and threads 31–34.
  Recorder descriptors stayed at 20, RSS 88672–129964 KiB, threads 22. Mean/peak
  CPU percentages relative to one core: driver 85.8/93.7%, recorder 67.0/71.8%.
  Both processes exited 0 after SIGINT without forced termination. This short
  sample does not establish long-duration memory stability.

The earlier 30 FPS bag retained 1714 pairs over 59.294 s (28.905 Hz), with zero
unmatched recorded pairs but a 1.843 s maximum source-header interval and a
2.182 s SDK reception stall. Its cause was not fully isolated. The final 15 FPS
selection is supported by the stable measured recording; sustained 30 FPS
recording is not accepted. Both bags and their logs are retained locally.

Receipt-minus-header values include SDK clock mapping and transport/processing;
they are not independently calibrated exposure-to-host latency. Visible
occlusion holes and missing returns remain. Image overlay inspection supports
plausible correspondence, not a new quantitative calibration-accuracy claim.

## Replay acceptance and evidence

The final 1x replay passed with no camera driver process running. All four camera
topics delivered exactly 887 messages each, plus one static-TF message; each
topic's serialized SHA-256 matched the stored bag exactly. All publishers observed
by the checker were `rosbag2_player`. The checker received 1836 clock messages,
verified advancing active ROS simulated time and resolved TF at image timestamps.
Player and checker exited 0. The first replay failed because the checker's
reliable clock subscription was incompatible with the player's best-effort QoS;
the corrected clock subscription was verified by this complete second replay.

Fourteen ROS contract tests and 21 existing native-capture tests passed. A fresh
native SDK 2.8.6 raw/aligned capture after ROS recording passed the existing
artifact checks: 1 mm/count, 239 us skew, raw/aligned centers 2.380/2.364 m.
No native capture code or system packages were changed. Final review tightened
recording-boundary checks; rechecking the complete bag passed and preserved the
exact counts/hashes used by the successful replay.

Final evidence under `data/outputs/femto_ros2/bringup_20260910/`:

- `acceptance_summary.json`, `local_dependencies.json`, final build logs and
  `driver_linked_libraries.txt`.
- `stationary_15fps_config.yaml`, `stationary_15fps_live.json`,
  `stationary_15fps_bag.json`, `stationary_15fps_final_bag.json`,
  `stationary_15fps_source_timing.json`,
  `stationary_15fps_replay.json` and the bag's `metadata.yaml`.
- `stationary_15fps_record_run.json` / `stationary_15fps_replay_run.json` preserve
  exact argv, exit status, runtime libraries, resources and driver-absence check.
- Matching driver/record/play/check logs, `stationary_15fps_sensor_timestamps.csv`,
  `ros_unit_tests.log`, `native_unit_tests.log`, and native regression artifacts.
- `run_check.py` is the bounded experiment harness; `analyze_timing.py` correlates
  CameraInfo headers with exact SDK-global stamps and measures source gaps.
  Reproduce correlation after sourcing the environment with
  `python3 data/outputs/femto_ros2/bringup_20260910/analyze_timing.py stationary_15fps 15`.
- Failed startup/TF/calibration checks, first clock-QoS replay, and the 30 FPS
  diagnostic bag remain alongside final evidence. Initial `source_and_build.json`
  describes the earlier blocked build; `acceptance_summary.json` is current.

These files, room images and bags remain local and ignored. The committed
configuration, patch, checker, tests and this record reproduce the verified setup.
A moving room recording is the next input needed before room-mapping acceptance;
this stationary bag proves the sensor/replay interface, not visual odometry.
