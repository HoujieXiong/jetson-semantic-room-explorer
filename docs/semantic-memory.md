# Persistent image-text memory and semantic search

Status: `VERIFIED` for minimum saved-data indexing, text ranking and ROS preview
integration on Jetson Orin Nano. Retrieval accuracy, live operation and calibrated
presence/absence decisions remain unverified.

The new `semantic_memory.py` uses original RGB pixels from verified mapped frames
and the existing SQLite associations. Only depth-accepted geometric representatives
are encoded: at most one view per object per source frame. It saves every crop,
source timestamp, pixel/file hash and normalized 512-dimensional MobileCLIP vector
in a separate index. Objects use the normalized equal mean of their supporting
vectors; the mean's norm records view agreement. The original geometry database
and detector labels remain intact. The index is tied to the exact memory snapshot,
frames manifest, weights, official implementation and inference dependencies.

This is open-vocabulary **retrieval over existing YOLO proposals**. It cannot
retrieve an object the proposal stage missed. Geometry is still a provisional
surface-point association. An object's detector confidence, geometric support and
text cosine similarity remain separate; no similarity is reported as probability.
The official aspect-preserving resize/center crop can lose context from thin or
partial detections. False proposals and small crops affect retrieval quality.

`run_semantic_search.py` connects text encoding to the existing map planner using
explicit object IDs, not by converting the phrase into a YOLO label. The fixed
experimental filter keeps scores at least 0.25 and within 0.02 of the top score.
These thresholds were declared before the evaluation queries, and were not tuned
to improve the results. All candidates and scores remain in the evidence. Empty
selection means `NO_SELECTED_OBJECTS`, not proof that the object is absent; the
existing geometric frontier fallback can still propose a view. Optional ROS
publication reuses the checked preview interface, with no motion commands.

## Local environment and model

- Official source: [Apple MobileCLIP](https://github.com/apple-aiml-research/ml-mobileclip),
  commit `48faa0fea4b08d74188b3841771aca6ff2c92852`.
- Model: `mobileclip_s0`, 215,934,653 bytes; SHA256
  `809b408eff74f8058843e86a1f92967097d42ba782450e85b8f4867b7f0ca0b7`.
- Official source code is MIT licensed; weights have separate research-only terms
  in upstream `LICENSE_MODELS`. Model files are local, not committed.
- Separate environment: `~/projects/mobileclip-env`. Its `.pth` imports the
  baseline `.venv` packages without modifying them. Torch 2.8.0, torchvision
  0.23.0 and NumPy 1.26.4 remain the Jetson baseline. Inference additions are pinned
  in `requirements-semantic.txt`. Dataset/training and clip-benchmark packages
  from the upstream general requirements were not installed.
- FP32 CUDA inference uses official reparameterization and preprocessing. The
  text phrase is passed to the official tokenizer unchanged; overlong phrases
  fail explicitly instead of being silently truncated.

To recreate this arrangement from the repository root, after installing the
existing Jetson baseline and obtaining the pinned official source/checkpoint:

```bash
python3 -m venv --system-site-packages ../mobileclip-env
../mobileclip-env/bin/python - <<'PY'
from pathlib import Path
import sysconfig
Path(sysconfig.get_path('purelib'), 'jetson_baseline.pth').write_text(
    str(Path.cwd()/'.venv/lib/python3.10/site-packages')+'\n')
Path('/tmp/mobileclip-constraints.txt').write_text(
    'torch==2.8.0\ntorchvision==0.23.0\nnumpy==1.26.4\n')
PY
../mobileclip-env/bin/python -m pip install --upgrade pip
../mobileclip-env/bin/python -m pip install \
  -c /tmp/mobileclip-constraints.txt -r requirements-semantic.txt
../mobileclip-env/bin/python -m pip install --no-deps -e ../ml-mobileclip
```

## Run

Use a fresh output directory for every command. Index the new recording:

```bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
../mobileclip-env/bin/python scripts/semantic_memory.py build \
  --memory data/outputs/concurrent_rgbd/line_20260915/memory.db \
  --frames data/outputs/concurrent_rgbd/line_20260915/frames/frames.json \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --output data/outputs/mobileclip/manual_index
```

Query the already measured index and inspect the generated `queries.html`:

```bash
../mobileclip-env/bin/python scripts/semantic_memory.py query \
  --memory data/outputs/concurrent_rgbd/line_20260915/memory.db \
  --index data/outputs/mobileclip/line_20260915/index_02 \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --text 'a fridge' --text 'a bottle' --text 'an elephant' \
  --output data/outputs/mobileclip/manual_queries
```

The HTML file embeds its images and uses no WebGL or video codecs. The measured
11-query report is ready to view on the Jetson display:

```bash
gio open data/outputs/mobileclip/line_20260915/queries_final/queries.html
```

Run the text-to-search chain:

```bash
../mobileclip-env/bin/python scripts/run_semantic_search.py \
  --memory data/outputs/concurrent_rgbd/line_20260915/memory.db \
  --index data/outputs/mobileclip/line_20260915/index_02 \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --mapping data/outputs/concurrent_rgbd/line_20260915/attempt_01 \
  --text 'a fridge' --simulated-start-xy 3.05 -1.1256999999999997 \
  --output data/outputs/mobileclip/manual_search
```

To publish, source `/opt/ros/humble/setup.bash`, set the same localhost ROS domain
in both shells, start `tests/check_search_publication.py` with a 60-second duration,
and add `--publish-preview`. See [ROS preview details](ros-search-preview.md).
`semantic_search.json` links the complete ranking, selected IDs, map decisions
and publication outcome. A candidate can be semantically selected but have no
geometrically valid goal or route.

## Measured acceptance, 2026-09-15

- 63 crops from 19 source nodes form 17 indexed objects. All crop pixels and
  bounds independently match the original RGB frames and geometric associations.
  Every vector is finite/unit length; independent scalar sums reproduce all
  fused vectors and every query score/order. A second build reproduces all
  per-view vector bytes exactly; original map/memory/frames/weights stay unchanged.
- Final build: 23.732 s total, 10.096 s model load. Of 63 image encodes, the 62
  calls after the first have median 37.245 ms and P95 51.758 ms, including crop
  preprocessing and transfer. Peak process RSS is 1,478,696 KiB; peak PyTorch
  allocated CUDA memory is 237,129,216 bytes. These are separate accounting
  measures on shared-memory Jetson hardware, not additive system RAM totals.
- The final text batch has one cold 350.967 ms encode; the remaining ten calls
  range from 14.559 to 29.448 ms. Measurements are saved-data trials with no SLAM
  workload, not end-to-end camera frame-rate acceptance.
- All 39 memory and 103 search tests pass. Five real refusal cases verify changed
  memory, changed index, mismatched model, overlong text and preserved output reuse.
- Three full GPU/ROS cases run in separate processes. `a fridge` selects ID 1 but
  its object goal fails map clearance, so the existing frontier is published.
  `a kitchen sink` selects IDs 9/10 but neither route is available: five refusal
  decisions, zero goals/paths. `an elephant` selects no object and publishes a
  frontier. Successful previews deliver five copies of each topic; received
  waypoints and terminal poses match exactly. All publisher contexts close.

The complete predeclared query set is below. IDs and labels are provisional;
this small same-recording evaluation is not a held-out accuracy benchmark.

| Phrase | Top ID | Top cosine | Selected IDs |
| --- | ---: | ---: | --- |
| a bottle | 4 | 0.246 | none |
| a refrigerator | 1 | 0.306 | 1 |
| a kitchen sink | 9 | 0.257 | 9, 10 |
| a drinking container | 12 | 0.222 | none |
| a fridge | 1 | 0.307 | 1 |
| a transparent plastic bottle | 4 | 0.208 | none |
| a white refrigerator | 1 | 0.283 | 1 |
| a red chair | 2 | 0.167 | none |
| a bicycle | 5 | 0.156 | none |
| an elephant | 9 | 0.170 | none |
| a backpack | 12 | 0.168 | none |

The refrigerator and its synonym rank the visible refrigerator first. Bottle,
drinking-container and transparent-bottle retrieval are poor and fall below the
filter. The white-refrigerator phrase retrieves the reflective metal refrigerator;
color-attribute correctness is not established. All four unknown controls fall
below threshold. We retain these failures rather than treating a working message
pipeline as validated recognition quality. Crop review also reveals existing YOLO
errors, including a protein container labeled microwave.

Evidence: `data/outputs/mobileclip/setup_20260915/` contains installation plans,
model smoke test, the predeclared query set and focused test logs.
`data/outputs/mobileclip/line_20260915/` contains both indexes, query reports,
embedded crop HTML, independent `integration.json`, source-check harness, actual
ROS receivers and `failures/verification.json`. CuTR feasibility now supports an
[offline-only role](cutr-feasibility.md). The whole project still needs causal
online memory/query decisions, concurrent semantic resource validation, quality
evaluation and eventual mobile-base integration.
