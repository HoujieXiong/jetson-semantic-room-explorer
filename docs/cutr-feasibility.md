# CuTR RGB-D feasibility on Jetson

Status: `VERIFIED` for standalone official-sample and Femto inference. The guarded
concurrent attempt did not complete a CuTR frame. CuTR remains an **offline research
comparison**, not the default perception backend or a verified object map.

The user authorized the official source, RGB-D weights, a minimal official sample
and isolated dependencies. The existing YOLO, camera, SLAM and semantic environments
were preserved. Source timestamps and frozen map poses remain explicit; these
experiments do not establish live CuTR localization or physical box accuracy.

## Source and environment

- [Official Apple source](https://github.com/apple-aiml-research/ml-cubifyanything),
  commit `00e9cb1f9c1b478bf49e08fea4d88e486794cfc1`, stored in
  `~/projects/ml-cubifyanything`.
- [Official RGB-D checkpoint](https://ml-site.cdn-apple.com/models/cutr/cutr_rgbd.pth):
  396,866,874 bytes, SHA256
  `856b89c62c49d518998eeef52db16eadede5c354c6e2dfb291e16fd2887a4217`.
  Resumed interrupted transfers are retained in the setup logs; ZIP CRC checks pass.
- Source uses the Apple Sample Code License; weights use the separate research
  terms in upstream `LICENSE_MODEL`. The CA-1M data is CC BY-NC-ND 4.0. Weights and
  data remain local and ignored.
- The official sample subset contains the first three complete frames from
  `ca1m-val-42898570.tar`: 42 unchanged member payloads, 2,826,240 bytes. Only the
  first 16 MiB of the 826,767,360-byte archive was downloaded. Member names, sizes
  and hashes are recorded in `setup_20260915/sample_subset.json`. Subset SHA256:
  `885d97b0d01bc00d939a21b0425814ccd6861cebad83d97f7bed87d066962fd7`.
- Isolated `~/projects/cutr-env` reuses the baseline Torch 2.8.0, torchvision 0.23.0,
  NumPy 1.26.4 and existing MobileCLIP environment's timm 1.0.29. Only
  `webdataset==0.2.86`, `tifffile==2025.5.10`, and `braceexpand==0.1.7` were added.
  Source imports through a `.pth`; two failed editable-install attempts remain
  recorded. Unused Rerun and DDS capture dependencies were not installed.

The first GPU trial failed in `torch.linalg.inv(K)` with the missing cuSOLVER
symbol `cusolverDnXsyevBatched_bufferSize`. The small explicit patch
[`cutr_jetson_intrinsics.patch`](../patches/cutr_jetson_intrinsics.patch) performs
only calibration-matrix inversion on CPU and copies the result back. The model
still runs on CUDA; system CUDA/PyTorch were not replaced. The patched package's
aggregate Python-source SHA256 is
`19852d14c870a545b18934b5f770be7802e034a396a4eb8e986ad126053761a5`.

To reproduce the environment after the existing baseline and semantic setup:

```bash
python3 -m venv --system-site-packages ../cutr-env
../cutr-env/bin/python - <<'PY'
from pathlib import Path
import sysconfig
site = Path(sysconfig.get_path('purelib'))
repo = Path.cwd()
(site/'jetson_baseline.pth').write_text(
    str(repo/'.venv/lib/python3.10/site-packages')+'\n'+
    str(repo.parent/'mobileclip-env/lib/python3.10/site-packages')+'\n')
(site/'cutr_source.pth').write_text(str(repo.parent/'ml-cubifyanything')+'\n')
PY
../cutr-env/bin/python -m pip install --no-deps \
  webdataset==0.2.86 tifffile==2025.5.10 braceexpand==0.1.7
# Apply once to the pinned, clean upstream checkout; inspect an existing patch first.
git -C ../ml-cubifyanything apply \
  "$PWD/patches/cutr_jetson_intrinsics.patch"
```

## Input and output contract

`scripts/benchmark_cutr.py` uses the official model factory, checkpoint, data reader,
augmentor and preprocessor in FP32 on CUDA. It limits samples/repeats to ten each,
sets a 40% PyTorch allocator cap, requires fresh output and retains incomplete
reports on failures. The measured command also has a wall-time limit. Output
contains every selected score, 2D box, optical-camera 3D center, local XYZ box
dimensions, rotation and eight corners. Coordinates are meters. The upstream class
index is not an object name; these are class-agnostic geometry proposals.

Official RGB is 768x1024 and depth is 192x256 (width x height), with supplied
intrinsics and gravity. The Femto adapter starts from the verified rectified
1280x720 RGB and registered uint16 depth, then produces RGB 1024x576 and depth
256x144. RGB uses area resize; depth uses nearest-exact original integer pixels,
then divides millimeters by 1,000. Zero remains invalid; no holes are filled.
The official intrinsic resize uniformly scales rows by 0.8 and 0.2 respectively.
It does not apply a separate half-pixel correction. Official preprocessing pads
RGB to 1024x1024 and depth to 256x256. These input sizes are not native camera
stream profiles; the native depth stream was 640x576 before SDK registration.

These bags have no IMU gravity. `--assume-map-z-up` explicitly enables the frozen
camera-pose estimate of gravity, with the same yaw removal as upstream capture.
It assumes map +Z is physical up, preserves the optical-camera down direction,
and rejects nonrigid or excessively tilted inputs. Agreement with the upstream
formula verifies the adapter, not the physical assumption. Predictions also retain
map centers/corners from the named frozen poses; they are not fused into memory.
Boxes crossing the camera plane stay in JSON but are omitted from image drawing.

## Commands and viewing

From the repository root, use new output directories:

```bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
timeout --signal=INT --kill-after=10s 180s ../cutr-env/bin/python \
  scripts/benchmark_cutr.py --model ../ml-cubifyanything/checkpoints/cutr_rgbd.pth \
  --sample-tar data/outputs/cutr/setup_20260915/official_three_frames.tar \
  --repeats 3 --output data/outputs/cutr/manual_official

timeout --signal=INT --kill-after=10s 180s ../cutr-env/bin/python \
  scripts/benchmark_cutr.py --model ../ml-cubifyanything/checkpoints/cutr_rgbd.pth \
  --frames data/outputs/concurrent_rgbd/line_20260915/frames/frames.json \
  --nodes 9 26 49 --assume-map-z-up --repeats 3 \
  --output data/outputs/cutr/manual_femto
```

The measured images open in the Jetson image viewer without WebGL or video codecs:

```bash
gio open data/outputs/cutr/femto_20260915/attempt_01/sample_0.png
gio open data/outputs/cutr/femto_20260915/attempt_01/sample_1.png
gio open data/outputs/cutr/femto_20260915/attempt_01/sample_2.png
```

## Standalone measurements

Three frames were each repeated three times. Warm statistics use all eight calls
after the first, including preprocessing, GPU transfer and synchronized inference.
They exclude input loading, output serialization, overlay drawing and disk writes;
reciprocal latency is not full-pipeline FPS. Peak RSS and CUDA memory overlap on
Jetson shared memory and must not be added.

| Measure | Official sample | Femto nodes 9, 26, 49 |
| --- | ---: | ---: |
| Model construction, weight load and GPU transfer | 2.043 s | 2.094 s |
| First inference | 4.087 s | 3.450 s |
| Warm P50 / P95 | 1.803 / 1.839 s | 1.793 / 1.832 s |
| Peak process RSS | 3,949,600 KiB | 3,865,600 KiB |
| Peak CUDA allocated | 2,095,106,048 bytes | 2,095,192,576 bytes |
| Peak CUDA reserved | 2,447,376,384 bytes | 2,407,530,496 bytes |
| Boxes at the fixed 0.25 threshold, by frame | 9, 7, 8 | 81, 86, 84 |

Repeated predictions are identical within each trial. Multiple visible cabinets,
counter objects, table structures and doors receive plausible cuboids, but the
Femto overlays also contain overlapping proposals and excessive extents. Counts
are proposals, not distinct objects. There are no manually labeled 3D references
or precision/recall claims, and the threshold was not retuned to make overlays
look cleaner. Estimated gravity and transfer from the official capture domain
remain unvalidated quality factors.

On the same three original Femto frames, the existing YOLO-plus-depth script finds
6/7/6 detections and accepts 5/6/3 depths. Its surface point is a different quantity
from a learned complete-object center. Saved best 2D IoU matches are diagnostic
comparisons, not labels or geometric error ground truth.

Evidence is under `data/outputs/cutr/`: `setup_20260915/` preserves installation,
source/sample hashes, failure and test logs; `official_20260915/attempt_01` retains
the original cuSOLVER failure, `attempt_02` the successful official run;
`femto_20260915/attempt_01` contains Femto outputs and `yolo_comparison` the
unchanged baseline comparison. `concurrent_20260915/` contains the bounded replay
supervisor, resource trace and independent verification.

## Guarded concurrency and decision

The existing 60.224-second, 899-pair bag was replayed at 0.25x with native RTAB-Map
and baseline GPU YOLO. A separate process attempted the saved Femto CuTR frames
while that workload was active; this was a resource probe, not a live CuTR topic
subscriber. The supervisor declared a 2,800,000 KiB minimum starting headroom,
a 1,048,576 KiB stop threshold and a 180-second CuTR deadline before running.

CuTR started at elapsed 45.404 s. At 63.486 s, `/proc/meminfo` reported
970,392 KiB available (947.65 MiB), below the guard. SIGINT stopped CuTR at 66.161 s
before any completed inference. Tegrastats peaked at 6,500 MB reported RAM and
830 MB swap. This was a controlled refusal, not an observed CUDA out-of-memory
exception. It does not prove that every possible memory configuration fails;
it does establish that this guarded workload has not passed coexistence acceptance.

The baseline subscriber saved a complete measurement: all 899 pairs, 893 processed,
six explicit queue drops, zero inference failures, 887 accepted source-time poses
and six refusals. Odometry produced 898 tracked outputs, zero lost and one input
without a result. Native map database integrity passes with 60 nodes. Perception,
odometry, mapping and player exited 0; CuTR and tegrastats exited on the intended
SIGINT. No forced kill or surviving owned process was recorded.

The outer supervisor itself remains `INCOMPLETE`: near process exit its `/proc`
reader raced with process teardown and raised `KeyError: 'VmRSS'`. The original
log, supervisor source and report are preserved. The local harness now explicitly
handles a zombie/exited process without inventing a zero RSS, but this repaired
harness was not rerun. A separate verifier checks the completed sensor report,
reconstructs causal TF, checks original image bytes and depth math, verifies map
integrity and confirms source hashes and child cleanup. Its `VERIFIED` result
applies to those artifacts and the diagnosed guard outcome; it does not relabel
the interrupted supervisor as successful. Runtime parameter queries after the
resource loop were not reached.

The decision is to retain CuTR for offline research. The cadence implied by
standalone inference latency is below the roadmap's approximately 1 Hz keyframe
target, concurrent headroom was
insufficient under the declared guard, and Femto box quality remains unvalidated.
No CuTR results enter production scene memory or search. YOLO-plus-depth remains
the measured baseline; MobileCLIP continues to provide text similarity separately.

## Verification and remaining work

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../cutr-env/bin/python \
  -m unittest discover -s tests/cutr -v
```

All ten tests pass in 0.255 s, covering known gravity/rotation, independent box
corners, metric resize with holes, invalid poses/resolution, empty/nonfinite
predictions, bounded input and output preservation. Independent checks on real
outputs reproduce corners with maximum error 2.988e-7 m and upstream gravity
with maximum element difference 2.636e-8. These are numerical agreement checks,
not physical accuracy. All resized depth pixels match exact 5:1 center sampling;
source intrinsics, timestamps, map transforms and file hashes agree.

A second Femto trial with the finalized serialization/diagnostics produces all
nine prediction lists identically to the first. Its new per-image omission counts
are zero; all cuboids were drawable. The first isolated timing table above remains
the performance evidence. Final evidence: `setup_20260915/geometry_verification.json`,
`geometry_tests_final.log`, `final_check.json`, `baseline_after.json`, and
`concurrent_20260915/attempt_01/verification.json`. The first independent verifier
also had a NumPy-integer JSON serialization error; the fixed verifier and both
logs remain saved. No model predictions were altered to pass verification.

The next integration step is causal online memory/query during existing-bag
playback, using only information already received. Frozen final map poses cannot
stand in for online pose revisions. This step needs no new physical capture;
accuracy refinement and eventual mobile-base navigation remain separate work.
