# Concurrent RGB-D Perception And SLAM

Status: `VERIFIED` on the Jetson, 2026-09-11, for bounded concurrency at 0.25x replay.

This measurement runs GPU perception while RTAB-Map processes the same original
`room_walk_02` recording. It uses online TF at each original RGB-D timestamp.
The previously verified offline demo instead uses final optimized map poses.
Neither a completed measurement nor a slowed replay establishes real-time
tracking, geometric accuracy or physical navigation.

## Run On This Jetson

The existing local harness has been adapted from the earlier mapping trial:

```bash
cd ~/projects/jetson-semantic-room-explorer
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 /usr/bin/python3 \
  data/outputs/concurrent_rgbd/trial_20260911/run_trial.py NEW_ATTEMPT
```

Use a new attempt name. The harness and room artifacts stay local and ignored.
It starts the native GPU measurement process, waits for its readiness marker,
starts the existing odometry/mapping commands and replays the 94.487-second bag
at 0.25x. It records process resources and `tegrastats`, queries actual node
parameters through the existing bounded helper, then closes its own children.
There is no camera driver, new capture, model download or physical movement.

The measurement process can also replace Terminal 3's checker in the existing
[mapping instructions](rtabmap-mapping.md#run-on-this-jetson):

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  tests/check_concurrent_perception.py \
  --reference data/outputs/femto_ros2/room_walk_20260910T223548Z/room_walk_02_bag.json \
  --model yolov8n.pt --duration 403 \
  --output data/outputs/concurrent_rgbd/NEW_RUN/measurement.json
```

Wait for `READY` before starting bag playback. The process performs one synthetic
zero-RGB GPU warmup before subscribing; this produces no retained observation.
Use a bounded supervisor such as the local harness: an unresponsive native GPU
call cannot be safely interrupted by cancelling its Python thread. The harness
records any forced termination as a failed cleanup condition during acceptance.

The GPU process uses native `.venv` OpenCV and NumPy with installed ROS message/TF
bindings. It does not import `cv_bridge`. RTAB-Map remains in separate processes
with its existing system OpenCV libraries. No Python environment was replaced.

## Queue, Time And Failure Contract

The measurement subclasses the existing mapping checker and reuses the original
sensor contract checker. Four-topic synchronization has a ten-message queue per
topic and a 5 ms RGB/depth limit. Each image must match its CameraInfo timestamp
exactly, with matching rectified RGB/depth calibration. Full serialized topic
hashes and counts must equal the verified bag.

Every synchronized pair is offered for perception. One frame may wait while
one worker performs inference. Up to eight completed detection results, without
image buffers, may await their source poses. A full pending slot rejects the new
pair with
`DROPPED: pending_queue_full`. Original timestamps and pixel hashes remain in
every pair's record, including drops. Synchronizer omissions are listed separately.
Subscription callbacks validate and enqueue data; they never call the detector.

Inference starts with camera-frame geometry and does not wait for SLAM. After
prediction, the main thread checks the exact source odometry result and queries
`map -> camera_color_optical_frame` at that original timestamp. A missing pose
uses a two-second timeout threshold after prediction completes, checked by the
main loop (the measured maximum overshoot was about 15 ms). Tracking loss
or unavailable source odometry/TF creates an explicit pose rejection. A valid
pose is frozen using only transforms received when the result is finalized;
later optimization cannot rewrite that recorded observation. TF receipt times
and transforms are retained so this cutoff can be reconstructed independently.
The main thread services pose waits while the GPU handles the next image.

The shared `infer_rgbd` function retains the established YOLO settings and robust
depth policy. Pose-rejected frames can still produce camera-frame depth points;
they have no map points. Depth-rejected detections have neither point. This
measurement does not import online observations into the frozen-map SQLite memory.

`measurement.json` contains the existing SLAM/sensor checks plus every pair's
state, pose evidence, detections, callback and latency distributions. A completed
report has no queued/in-flight work. Sensor corruption, inference errors or
unresolved work at the duration limit fail explicitly and leave `INCOMPLETE`
evidence. `run.json` records source/code hashes, commands, resources and child
exits; the separately generated `verification.json` is the acceptance result.

The measured latency stages are arrival-to-dispatch, GPU prediction,
prediction-plus-depth processing, post-prediction pose waiting, and arrival-to-result. The
last includes scheduling and pose waiting; it is not model-only latency. Host
RSS, whole-device RAM/swap, GPU load, temperature and power have different scopes
and must not be added together as independent memory allocations.

## Focused Verification

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/odometry -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/mapping -v
```

The new tests use real ROS messages, synchronization and TF, with controlled
futures at the GPU boundary. They cover bounded pending work, explicit overflow,
lost/missing/late source poses, preservation of the finalized pose, worker
failure, image/calibration disagreement and incomplete work. Actual GPU behavior
is measured separately in the full trial and the offline demo regression.

## Measured Comparison

Both complete trials received the original **1411 RGB-D pairs**, with identical
full source topic hashes and no synchronizer omissions. The first waited for TF
before inference. The final implementation overlaps those stages:

Open the measured comparison on the Jetson display with
`xdg-open data/outputs/concurrent_rgbd/trial_20260911/scheduling_comparison.png`.

| Measurement | Wait before inference | Overlap inference and pose waiting |
| --- | ---: | ---: |
| Processed / explicitly dropped pairs | 618 / 793 | 1402 / 9 |
| Frames with accepted / rejected online poses | 482 / 136 | 1109 / 293 |
| Prediction median / P95 (ms) | 79.773 / 98.756 | 70.483 / 91.100 |
| Arrival-to-result median / P95 (ms) | 600.078 / 822.668 | 501.363 / 1222.399 |
| Callback median / P95 (ms) | 5.150 / 19.890 | 5.143 / 18.809 |

The change reduces queue drops from **56.2% to 0.64%**. Tail latency is higher
in the second run; the populations differ because many more frames are retained.
Do not claim uniform latency improvement or a language-level speedup. Final
pre-inference queue waiting has median/P95 **7.934/10.397 ms**, while post-prediction
pose waiting has median/P95 **397.804/1110.800 ms**. Observed queue peaks are
exactly **one pending input, one inference job and eight pose-waiting results**.
There are no unresolved jobs or inference failures at completion.

The second run produces **5022 detections**, including **3832 accepted camera
depth points**, **1190 depth rejections**, and **3434 map-localized observations**.
Pose rejection reasons are 272 tracking losses, 13 missing source odometry results
at the timeout, and eight unavailable source map transforms. These observations
are not confirmed distinct objects. Depth acceptance does not override pose loss.

Independent verification reread original bag images, checked every pair's pixel
hashes and every accepted depth against its raw millimeter pixel, and reconstructed
each accepted map pose using only TF events received by its finalization cutoff.
Pose reconstruction error is zero; independent camera/map-point arithmetic
differs by at most 8.882e-16 m. This checks association/math, not physical accuracy.

Odometry processes 1410 frames: **1138 tracked and 272 lost**, with one input
without an output. Mapping stores 76 nodes, retains 64 final graph poses and
provides 75 source-time map observations under the existing mapping checker.
Its SQLite database passes integrity checks. The first trial tracked 1141 frames;
these runs do not establish a tracking-quality improvement.

Final-trial perception RSS peaks at **1321688 KiB**; odometry at 335084 KiB and
mapping at 441476 KiB. Whole-device `tegrastats` RAM peaks at **3951 MB**, swap at
249 MB, GPU temperature at **53.875 C**, and reported module power at **7451 mW**.
Median/P95 CPU use is **62.28/70.82% of one core** for the perception/checker
process and 92.57/103.62% for odometry. These are sampled process measurements,
not pure Python execution costs. GPU load median/P95 is 43/98%; resource samples
include startup and shutdown. There are 381 samples with all four main processes
alive. No long-duration memory-leak or real-time throughput acceptance is claimed.

Both trials finish with exit 0 for perception, odometry, mapping and playback,
without forced termination or remaining child process entries. Original bags,
weights and the earlier map stay unchanged. Actual ROS parameters and library
paths are saved. All **35 odometry/concurrency tests** and **21 depth/mapping
tests** pass; the real GPU offline regression reproduces the preceding 18
detections, 15 accepted points, three rejections and bottle search timeline.

Evidence: `data/outputs/concurrent_rgbd/trial_20260911/`, including test logs,
offline regression/check, `attempt_01` and `attempt_02` run/measurement/verification
reports, source snapshots, parameter dumps and resource logs. The first sources
and verifier remain archived; later changes do not replace the measured baseline.

The next step finalizes this new concurrent map and its observations into a
separate frozen scene memory and search preview. Online TF and final optimized
poses must remain separately identified; this step alone does not implement
causal online memory/search or physical navigation.
