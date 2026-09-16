# Causal online MobileCLIP text retrieval

Status: `VERIFIED` for bounded recorded-data queries on Jetson Orin Nano.
Retrieval quality, continuous live operation and changing-map navigation remain
unverified.

The concurrent recorded-data producer can now encode delivered RGB keyframes and
persist their original crop evidence and MobileCLIP vectors in the same SQLite
journal as observations and graph revisions. A text query reads one committed
prefix and derives both geometry and semantic associations from that prefix.
No saved final pose, prebuilt object index or future image is imported.

## Ownership and bounded scheduling

`tests/check_concurrent_perception.py --memory-db PATH --semantic-model CHECKPOINT`
loads the existing official MobileCLIP-S0 encoder in the isolated semantic Python
environment, alongside the unchanged GPU YOLO model. There is one additional
encoding worker. The existing ROS callbacks, one pending YOLO frame and eight
pose-wait slots remain unchanged.

The producer retains at most 32 original 1280x720 RGB8 arrays (88,473,600 bytes,
excluding other in-flight views/overhead). An actual received mapping event
requests its source frame, using the existing integer/double timestamp-roundtrip
tolerance. There are at most eight pending keyframe requests and one active
encoding job. A request waits at most five seconds for its source observation to
be finalized. Dropped source frames, original pose refusals, missing/evicted RGB,
queue overflow and shutdown cancellation retain explicit reasons.

By default, only originally accepted poses and depth-accepted proposals can be encoded.
The crop implementation, RGB ordering, official preprocessing, vector dimension,
weights/source/package identity and text tokenizer are shared with
[the frozen semantic path](semantic-memory.md). At most 16 crops are encoded per
keyframe in confidence order; remaining detections retain `crop_budget` omissions.
This caps work even on a crowded frame. Inference errors propagate and make the
trial incomplete. Partial files from a failed job cannot supply a query vector.

The optional `--semantic-include-unlocalized` producer flag also encodes
depth-rejected proposals after accepted proposals within the same crop budget.
Their source views appear in a separate ranking with no 3D object or navigation
target. The new path passes two historical-source GPU experiments; simultaneous
SLAM/detection performance remains unverified. See
[unlocalized evidence, measured results and limitations](unlocalized-visual-evidence.md).

Each successful keyframe stores original source/pixel identity, detector index,
clipped exclusive crop bounds, lossless PNG/file/pixel hashes, normalized 512-D
vectors, encoding times and request/start/completion availability. The sole
journal writer checks an earlier mapping request and accepted observation before
committing a semantic event. A unique node constraint rejects duplicate outcomes.
Vectors belong to original observations, never to a long-lived object number.

## Query and revision contract

`query_online` still supports the existing label-only API and old journals. The
optional text-vector path uses the same SQLite read transaction and derived
association tables. Frozen memory/index readers remain separate.

For each current geometric object, text ranking includes only its current
`new_object`/`nearest_match` representatives with embeddings already committed in
that prefix. Same-frame overlapping proposals do not add votes. Vectors are fused
with the existing equal-mean normalization and cosine ranking. Supports without
vectors and reasons are returned explicitly; an object's semantic support count
can be smaller than its geometric support count. An object with no available
vector cannot be ranked.

A graph revision may move, split or merge object associations. The query rebuilds
those associations and reassigns original vectors accordingly; old object IDs are
not reused as permanent semantic identities. Results name their session, event
prefix, graph hash and source semantic events. Later commits do not alter an
already returned result. Nodes outside the active graph remain excluded even
though their original pixels/vectors persist.

Online text-query and search-preview CLIs optionally accept
`--merge-duplicate-tracks`. It requires repeated shared-frame box/depth evidence
before consolidating different-label tracks, and retains one representative per
source frame. The result records its policy, original labels and merge witnesses.
Canonical detector labels are retained, not inferred from query text. This mode
is restricted to complete list/text snapshots; defaults and label-only queries
keep their original behavior. See the [contract and measurements](coobserved-tracks.md).

The existing experimental selection threshold remains cosine >= 0.25 and within
0.02 of the highest score. Exact text is passed unchanged, without substituting a
YOLO label. Empty support returns `NO_SEMANTIC_SUPPORT`; rankings below threshold
return `NO_CANDIDATE_ABOVE_THRESHOLD`. Neither is proof of room-wide absence.
Similarity is not probability, physical object identity or a navigation decision.

## Run on the existing Jetson data

No new recording, model download or package installation is needed on this
Jetson. Use a fresh output path; local model/environment setup is documented in
[semantic memory](semantic-memory.md). The observer command is:

```bash
source scripts/rtabmap_odom_env.bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
../mobileclip-env/bin/python tests/check_concurrent_perception.py \
  --reference data/outputs/online_memory/line_20260915/normalized_reference.json \
  --model yolov8n.pt --duration 301 \
  --memory-db data/outputs/online_semantic/manual/online.db \
  --semantic-model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --output data/outputs/online_semantic/manual/measurement.json
```

For the bounded stationary comparison, add `--imgsz 1280 --semantic-square-pad`
to the observer command. The size is explicitly recorded in the journal;
confidence, device and depth gates stay fixed. `--semantic-square-pad` requires
`--semantic-model` and records the encoder identity used for the complete crop.
Text-query CLIs read that identity before model loading and verify it again at
the committed query snapshot. Existing journals keep their original mode; mixing
encoder identities is refused. Defaults remain 640 and official center cropping.
See [the bounded bowl replay](bowl-replay.md) for measured results and limitations.

It requires the recorded SLAM nodes and player. The local bounded supervisor
starts/stops them, uses the previously verified typed-message player and launches
independent queries during playback:

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  data/outputs/online_semantic/line_20260915/run_trial.py manual_run
```

The supervisor refuses an existing camera/SLAM process, bounds text-query
processes to 45 seconds and stops if available system memory drops below 1 GiB.
It preserves exact commands, source/configuration copies, input hashes, process
exits and resource samples. These helpers live with the ignored room recording.
They issue no camera or motor commands.

Query an active or closed journal from another process:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../mobileclip-env/bin/python \
  scripts/online_semantic_memory.py \
  --db data/outputs/online_semantic/manual/online.db \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --text 'a fridge' --output data/outputs/online_semantic/manual_query
```

The fresh output directory contains `query.json` and `queries.html`. The HTML
embeds the top three original crops and needs no WebGL or codec. Every CLI query
loads its own GPU text encoder; its full latency includes model loading. This
is a bounded acceptance interface, not a continuously warm query server.

## Focused verification

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/online_memory -v
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/odometry -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/memory -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/search -v
```

Known-axis tests exercise delayed embeddings, writer commits during query
construction, graph-driven association changes, partial semantic support,
model/schema mismatch, future evidence, rejected poses, altered pixels/crop
metadata, duplicate outcomes, crop/queue budgets, cache eviction, worker failure
and cleanup. They use real SQLite and lossless image files. Actual GPU encoding,
source-bag crop equality and independent scalar ranking need the recorded-data
integration evidence below.

## Measured acceptance, 2026-09-15

Successful evidence: `data/outputs/online_semantic/line_20260915/attempt_02/`.
The existing 899-pair, 60.224 s recording runs at nominal 0.25x. The full trial
takes 354.556 s including model loads, independent CLI queries and cleanup.
Source images, model weights, prior label journal and frozen semantic index remain
byte-identical. No dependency download, physical capture or motor command occurs.

| Check | Measured result |
| --- | --- |
| Input / YOLO | 899 synchronized pairs; 893 processed, six explicit drops, zero inference failures |
| Source poses | 888 accepted; one missing odometry and four missing-map-TF refusals |
| SLAM | 898 tracked outputs, zero reported tracking loss, one input without output; 60 map nodes |
| Semantic outcomes | 59 encoded keyframes / 226 crops; one original pose refusal; no semantic queue or crop-budget drop |
| Bounds | RGB cache peak 32 frames; pending keyframe peak 1/8; existing pending/inference/pose-wait peaks 1/1/7 |
| Journal | 1,079 events, 8,724,480 bytes, integrity passed; 60 semantic outcomes in the same prefix history |
| Final active graph | 20 eligible frames, 93 detections, 67 geometric/semantic supports, 16 provisional objects |
| Reopen / compatibility | Semantic and geometry results identical; bytes unchanged; original label-only journal still reproduces its old result |
| Cleanup | All observer, player, mapper, odometry and query processes exit 0; telemetry SIGINT; no forced stop or remaining owned PID |

The fixed four phrases include all outcomes, including the unsuccessful bottle
query. No thresholds were tuned after seeing these results:

| Phase / phrase | Prefix / graph event | Available semantic supports | Top detector label / cosine | Selection |
| --- | --- | ---: | --- | --- |
| Before playback: `a fridge` | 0 / none | 0 | none | NO_SEMANTIC_SUPPORT |
| During: `a fridge` | 141 / 130 | 4 | refrigerator / 0.294846 | ID 1 |
| During: `a refrigerator` | 504 / 490 | 38 | refrigerator / 0.296559 | ID 1 |
| During: `an elephant` | 856 / 850 | 53 | microwave / 0.165465 | none above threshold |
| After playback: `a bottle` | 1079 / 1065 | 67 | oven / 0.245764 | none above threshold |

All three during-playback decisions precede playback completion. Their current
geometric supports have no missing embeddings in these particular snapshots;
partial/missing embedding behavior is separately tested. Snapshots are taken
after text encoding, while the producer can continue receiving observations.

Visual review confirms the refrigerator crop. The elephant query's top crop is
a dark labeled container, with no selected candidate. Bottle retrieval remains
poor: a dark appliance section ranks first, while a visible light-colored
dispenser/bottle ranks third at 0.213572. This is inspection of a few original
crops, not a held-out accuracy or room-inventory benchmark. Review on the Jetson:

```bash
gio open data/outputs/online_semantic/line_20260915/attempt_02/during_refrigerator/queries.html
gio open data/outputs/online_semantic/line_20260915/attempt_02/after_playback/queries.html
```

Latency includes the actual concurrent workload. First crop encoding is
517.881 ms; the remaining 225 encodes have P50/P95 80.330/120.574 ms. These encode
times include preprocessing/transfer, exclude PNG saving, and are not camera FPS.
During-query model loads are 10.740–12.538 s and text encodes 421.708–556.012 ms.
Snapshot/association/ranking computation is 82.922/203.222/271.545 ms, but complete
CLI wall times are **14.914/16.125/14.106 seconds**, including interpreter/import
startup. A continuously loaded query service has not been measured.

Perception arrival-to-result P50/P95 is 496.530/556.319 ms; callback P95 is
19.608 ms. Writer queue peak is 2/16, commit P50/P95/max
11.557/23.568/111.558 ms. Producer RSS peaks at 2,096,968 KiB. Tegrastats system RAM
peaks at 5,136 MB and swap ranges 880–948 MB, including pre-existing system use.
No 1 GiB available-memory guard refusal occurs. Shared-memory Jetson accounting
is not additive, and this one bounded trial does not establish leak freedom or
real-time throughput.

Independent checks decode the original bag and compare all 226 PNG crops, bounds,
source timestamps and hashes. They reconstruct source-time TF from received
events, derive each graph prefix and association separately, and use scalar sums
to check vector fusion, cosine scores, best views, missing supports and selection.
Maximum scalar score error is 3.88e-8; geometry error is 8.89e-16 m. These are
numerical consistency checks, not physical accuracy. The observed graphs contain
135 historical translation updates above 1 micrometer, largest 0.003423 m.

All 207 focused tests pass: 25 online-memory, 40 odometry/concurrency, 39 frozen
memory/semantics and 103 search tests. Compilation and whitespace checks pass.
Exact local helper/source/config snapshots, resource samples and query artifacts
are retained with `verification.json`, `geometry_verification.json`,
`semantic_verification.json`, `reopen_check.json` and `crop_review.json`.
The original-journal regression is in the parent directory.

Attempt 01 remains INCOMPLETE: the initial no-support query exits successfully,
but the local supervisor races with process exit while sampling `/proc` before
playback starts. Both owned processes and memory/semantic workers close. The
supervisor now counts that specific exit-sampling race and relies on the child
exit code, preserving all other failures and the memory guard. Successful attempt
02 has no forced cleanup. No failed run is relabeled successful.

The subsequent [causal search preview](online-search-preview.md) now connects
these queries to received occupancy grids and ROS decisions. The original
semantic journal and retrospective query command remain unchanged.
