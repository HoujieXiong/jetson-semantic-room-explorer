# RTAB-Map RGB-D Odometry On Recorded Femto Data

This is an offline odometry experiment on the Jetson Orin Nano. It estimates
`odom -> camera_link` from the existing second room-walk bag. There is no mapping
node, map frame, loop closure, external pose reference, or camera activation.
The user approved this experiment and its missing dependencies on 2026-09-10
after choosing to evaluate existing data before recording again.

## Runtime And Dependencies

The experiment uses official ROS 2 Humble ARM64 binary packages, with RTAB-Map
core and ROS odometry version 0.23.7. The upstream packages declare BSD licenses;
dependency license files remain in the extracted packages. The main versions are:

| Package suffix after `ros-humble-` | Debian version |
| --- | --- |
| `rtabmap` | `0.23.7-1jammy.20260717.005239` |
| `rtabmap-msgs` | `0.23.7-1jammy.20260717.005316` |
| `rtabmap-conversions` | `0.23.7-1jammy.20260804.195813` |
| `rtabmap-sync` | `0.23.7-1jammy.20260805.001538` |
| `rtabmap-util` | `0.23.7-1jammy.20260805.004806` |
| `rtabmap-odom` | `0.23.7-1jammy.20260805.011000` |

The approved manifest contains 36 packages: 35 downloaded (21,665,814 bytes) and
one previously cached diagnostic-updater archive reused. Each archive's SHA-256
matched the cached APT metadata before `dpkg-deb -x` extracted it. The declared
extracted size totals 125,119,488 bytes. No system installation or maintainer
script ran. This is an addition to the existing Jetson ROS environment, not a
portable dependency installer or an RTAB-Map source-build verification.

Local reproducibility artifacts:

```text
~/projects/rtabmap_odom_ws/debs/       # retained verified archives
~/projects/rtabmap_odom_ws/deps/       # extracted runtime
data/outputs/rtabmap_odom/preflight_20260910T230308Z/
  dependency_plan.json               # exact packages, versions, hashes and URLs
  dependencies_prepared.json         # verified archive paths and hashes
  prepare_dependencies.py            # exact download/extraction procedure
  download.log
  ldd_final.txt
  runtime_parameters.yaml
  runtime_libraries.txt
```

`prepare_dependencies.py` replays only the approved manifest; retained archives
also allow local extraction without a new download. For another machine, first
inspect its installed dependencies and resolve a new plan rather than assuming
this Jetson's missing-package list is complete. Ask before downloading newly
required components; approval for this manifest has already been given.

Use a fresh shell with system Python and
[`scripts/rtabmap_odom_env.bash`](../scripts/rtabmap_odom_env.bash). It uses system
Humble cv_bridge and OpenCV 4.5d, confirmed in the running process's library
mappings. The camera driver uses a separate OpenCV 4.8 overlay. Mixing those
overlays would invalidate this runtime; the helper rejects the camera overlay
and an active virtual environment. ROS domain 43 and localhost communication
isolate this experiment from the camera's domain 42.

## Input, Output And Measurement Contract

The input is `room_walk_02` from
`data/outputs/femto_ros2/room_walk_20260910T223548Z/`: a 94.487476504-second bag
with 1411 RGB-D pairs. Its matching `room_walk_02_bag.json` is the passing sensor
reference. Previous driver-stopped replay verified every image byte, header,
CameraInfo and static transform. See [the camera evidence](camera-ros2.md).

- Both delivered images are undistorted 1280x720, with matching calibration in
  `camera_color_optical_frame`: color `rgb8`, registered depth `16UC1` millimeters,
  zero invalid. The original hardware depth source is 640x576. No resizing,
  invented depth, or timestamp rewriting is introduced here.
- RGB, depth and RGB CameraInfo are synchronized within 5 ms. Published stamps
  have up to 4.149 ms skew in this bag; exact timestamp synchronization would
  reject valid pairs. These are the recorded SDK-global stamps, not device time.
- The odometry pose uses meters and retains the later RGB/depth header stamp.
  The checker requires matching `/odom` and `/odom_info_lite` stamps and verifies
  each against an input pair. On tracked results, `/tf` must equal the pose and
  connect to the recorded color optical frame at that exact observation time.
- `use_sim_time` is enabled and `/clock` must advance. Full replay must reproduce
  both CameraInfo streams' counts and serialized hashes. The lightweight checker
  does not repeat image hashing while benchmarking the odometry process.
- Automatic reset is disabled. Lost results remain explicit, with the upstream
  null quaternion; their CSV position/rotation cells are empty. Never plot those
  null messages as returns to the origin. Processing omissions and reported
  tracking losses are counted separately.

The configuration retains the upstream F2M visual odometry defaults:
`Odom/Strategy=0`, `Reg/Strategy=0`, `Vis/FeatureType=8` (GFTT/ORB). There is no
IMU, external guess or pose filter. Per-run parameter dumps retain all defaults.

The source corresponding to the installed ROS version is tag `0.23.7-humble`,
commit `c25a091c2a682f0e0f4e8d19d807953e7f1a8161`:
[RGB-D synchronization/stamps](https://github.com/introlab/rtabmap_ros/blob/c25a091c2a682f0e0f4e8d19d807953e7f1a8161/rtabmap_odom/src/nodelets/rgbd_odometry.cpp),
[odometry publication and replay policy](https://github.com/introlab/rtabmap_ros/blob/c25a091c2a682f0e0f4e8d19d807953e7f1a8161/rtabmap_odom/src/OdometryROS.cpp).
Copies of these two source files are saved with the preflight evidence.

## Watch The Recording

Local review videos are exported under
`data/outputs/rtabmap_odom/trials_20260910/video_review/`:

- `room_walk_02_review.mp4`: the complete RGB recording at normal speed;
  1411 frames, 94.533 seconds, 26.14 MB.
- `loss_18_to_25s_half_speed.mp4`: source seconds 18–25 at half speed, covering
  the first sustained loss in the quarter-speed odometry experiment;
  105 frames, 14.068 seconds, 2.50 MB.

The original 1280x720 RGB view is retained above a separate caption strip. The
`SOURCE` counter uses the same source-time origin as the measurement report.
Look near `SOURCE 21.104 s`; the short clip's player timeline starts at zero
and runs at half speed, so its player time is different from the source counter.
Pause the short clip at player time **6.163 seconds** to see that source frame.
`TRACKED`, `LOST`, inliers and matches are the saved 0.25x trial's diagnostics,
not a new odometry run or an independently verified pose.

These H.264 MP4 files are local, lossy viewing copies without audio or metric
depth. The original bag is unchanged. On a computer connected over SSH, download
the short clip and open it with an existing video player. Run this command on
that computer, replacing `JETSON_IP` with the address used for SSH:

```bash
scp jeffx@JETSON_IP:~/projects/jetson-semantic-room-explorer/data/outputs/rtabmap_odom/trials_20260910/video_review/loss_18_to_25s_half_speed.mp4 .
```

The export procedure is saved beside the videos as `export_video.py`. It reuses
the installed PyAV/libx264 encoder and ROS compression reader, joins odometry by
exact source stamp, and verifies every decoded output frame and presentation
timestamp against the source. It also compares the complete serialized RGB hash
with the passing bag reference. Reproduction from the repository root uses:

```bash
source /opt/ros/humble/setup.bash
.venv/bin/python data/outputs/rtabmap_odom/trials_20260910/video_review/export_video.py
```

The exporter refuses to overwrite either existing video. Preserve existing
exports when repeating it in a new local output directory.

On 2026-09-10, both outputs decoded completely as H.264, 1280x816 including the
caption strip. RGB input count and serialized hash matched the passing bag
report; every decoded presentation timestamp matched its intended source-based
time to within one microsecond. `export_report.json` and `export.log` retain
this verification. `loss_at_21_104s.png` is a decoded preview of the first long
loss, showing the measured 7 inliers from 130 matches. The video and preview do
not establish which factor caused the matching failure.

## Reproduce On This Jetson

Keep the camera driver stopped. From the repository root, source the environment
in each of three fresh terminals. Use a new output path for every attempt.

Terminal 1 starts the upstream odometry executable with the checked-in config:

```bash
source scripts/rtabmap_odom_env.bash
"${RTABMAP_ODOM_PREFIX}/lib/rtabmap_odom/rgbd_odometry" --ros-args \
  --params-file config/rtabmap_rgbd_odometry.yaml \
  -r rgb/image:=/camera/color/image_raw \
  -r depth/image:=/camera/depth/image_raw \
  -r rgb/camera_info:=/camera/color/camera_info
```

Terminal 2 starts the bounded measurement before playback:

```bash
source scripts/rtabmap_odom_env.bash
/usr/bin/python3 tests/check_rtabmap_odometry.py \
  --reference data/outputs/femto_ros2/room_walk_20260910T223548Z/room_walk_02_bag.json \
  --duration 403 \
  --output data/outputs/rtabmap_odom/replay_new/measurement.json
```

Start Terminal 3 within about five seconds of the checker. The 403-second
measurement budget includes roughly 25 seconds beyond the bag's quarter-speed
duration for startup and draining:

```bash
source scripts/rtabmap_odom_env.bash
ros2 bag play data/outputs/femto_ros2/room_walk_20260910T223548Z/room_walk_02 \
  --rate 0.25 --clock 30 --delay 2 --read-ahead-queue-size 40 \
  --wait-for-all-acked 5000 --disable-keyboard-controls
```

After both player and checker finish, save `ros2 param dump /rgbd_odometry` and
stop Terminal 1 with Ctrl-C. Inspect all exit statuses and the JSON/CSV; a checker
exit of zero and `status: MEASURED` mean the measurement contract passed, even
when odometry reported losses. They do not certify a usable trajectory.

The actual unattended runs used the bounded local harness
`data/outputs/rtabmap_odom/trials_20260910/run_trial.py`. It saves exact commands,
config, runtime parameters/libraries, per-second RSS/descriptors/threads/CPU
ticks, process logs, results and exit statuses. Every child is closed in a
`finally` block, with forced termination recorded if needed. From the sourced
environment, this creates a new attempt; the existing attempts must remain intact:

```bash
/usr/bin/python3 data/outputs/rtabmap_odom/trials_20260910/run_trial.py NEW_NAME 0.25
```

Focused checker tests:

```bash
source scripts/rtabmap_odom_env.bash
/usr/bin/python3 -m unittest discover -s tests/odometry -v
bash -n scripts/rtabmap_odom_env.bash
```

## Measured Results, 2026-09-10

Both complete bag replays finished on this Jetson with the driver absent. Each
reproduced all 1411 CameraInfo messages per stream and their reference hashes.
All output pose/info stamps matched source pairs; all tracked poses matched TF
and connected to the optical frame at the observation timestamp.

| Measurement | 1x, latest-frame policy on | 0.25x, policy off |
| --- | --- | --- |
| Input RGB-D pairs | 1411 | 1411 |
| Odometry results | 466 | 1410 |
| Inputs without a result | 945 | 1 (final pair) |
| Tracked / lost results | 100 / 366 | 420 / 990 |
| Lost fraction of results | 78.54% | 70.21% |
| Processing median / P95 / max | 168.29 / 239.88 / 326.86 ms | 183.90 / 239.05 / 349.26 ms |
| Longest observed loss | 75.373 s | 60.766 s |
| Validated pose/TF pairs | 100 | 420 |
| Clock messages | 2900 | 11373 |
| Odometry RSS range | 154780–277096 KiB | 152928–324896 KiB |
| Odometry descriptors / threads | 19 / 31–36 | 19 / 31–36 |
| Harness wall time, including startup/draining | 131.499 s | 417.781 s |
| Player / checker / odometry exit status | 0 / 0 / 0 | 0 / 0 / 0 |

Relative to the first source stamp, observed loss intervals were:

- 1x: 16.750–17.286 s and 18.559–93.931 s.
- 0.25x: 19.430–19.564 s, 21.104–81.870 s and 89.040–94.467 s.

The quarter-speed run processed all but the final input pair, yet still lost
tracking for most of the recording. Its long failure starts well before the end
handling. This does not establish a unique cause: frame matching, scene content,
motion and the default configuration need diagnosis. Logs report insufficient
inliers and later projected points outside the camera. There was no automatic
reset; eventual recovery is not a measured loop closure.

Twelve focused tests passed, covering lost/null poses, non-finite values,
observed-loss intervals, source stamps, altered replay, missing outputs, stopped
clock and missing TF. Three CLI rejection checks preserved prior outputs and
rejected invalid duration. A real ROS run with no input exited 1 after its bounded
wait and saved an `INCOMPLETE` report with zero observations. Syntax and diff
checks passed. Both experiment
process groups closed without forced termination. Feature maps and allocations
can contribute to RSS growth; these two short runs do not establish leak freedom.

Evidence root: `data/outputs/rtabmap_odom/trials_20260910/` (ignored):

- `rate_1/` and `rate_025/`: `measurement.json`, trajectory `.csv`, `run.json`,
  `config.yaml`, `parameters.yaml`, and full odometry/player/checker logs.
- `summary.json` and `analyze.py`: derived metrics and their reproduction.
- `odometry_trials.png` / `.pdf`: source-time position, inliers, processing time
  and explicit loss intervals. Null poses are gaps, not zero positions.
- `unit_tests_final.log`, `cli_checks.json`, `no_input_timeout.json` / `.log`,
  `checker_during_trials.py`, and
  `final_process_check.json` (no experiment process remained).
  Final checker edits protect existing outputs, retain incomplete status on CSV
  failure and guarantee cleanup if writing the report fails; measurement
  callbacks and checks are unchanged.

## Interpretation

The first run used 1x playback and the upstream default
`always_process_most_recent_frame=true`. Logs explicitly reported replay timing
drops and recommended disabling that option for bursty offline replay. The
second run uses 0.25x playback and `false`, now in the checked-in config. Both
rate and input policy changed: this is a practical offline diagnostic, not an
experiment isolating the effect of playback rate alone.

Neither setting guarantees every input reaches the odometry worker. The bag
preserves actual receipt timing, including a previously measured 693 ms maximum
color CameraInfo receipt gap. Slower playback reduces compute pressure but does
not repair recorded blur, viewpoint changes, missing depth, or delayed arrival.
Do not label inputs without a result as missing camera frames.

Reported loss intervals run from the first lost output until the next tracked
output or the last source stamp. They describe the algorithm's observed state
across intervening unprocessed frames. A tracked result is the algorithm's own
assessment; no ground truth establishes absolute pose accuracy. Return to the
start was reported by the operator, followed by camera handling. No stationary
endpoint or geometric loop closure should be inferred from that report.
