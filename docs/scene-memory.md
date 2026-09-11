# Persistent Object Memory

Status: `VERIFIED` for minimum offline SQLite memory on this Jetson, 2026-09-10.
The three measured M5 frames retain 18 source observations, including three
depth rejections. Thirteen representative observations support nine provisional
objects; two overlapping detections remain recorded without adding support.
The database can be queried from a new process after the importer exits.

## Run And Inspect

Use the existing native virtual environment. SQLite comes from Python's standard
library; the script reuses the existing NumPy-based source-association helper.
It does not load YOLO weights or require GPU access, ROS or a camera connection.
No dependency or model was downloaded for this step.

```bash
cd ~/projects/jetson-semantic-room-explorer
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  scripts/scene_memory.py --db data/outputs/scene_memory/NEW_RUN/memory.db \
  import data/outputs/object_observations/m5_20260910/trial_01/observations.json

.venv/bin/python scripts/scene_memory.py \
  --db data/outputs/scene_memory/NEW_RUN/memory.db list
.venv/bin/python scripts/scene_memory.py \
  --db data/outputs/scene_memory/NEW_RUN/memory.db find refrigerator
.venv/bin/python scripts/scene_memory.py \
  --db data/outputs/scene_memory/NEW_RUN/memory.db last_seen refrigerator
```

To query the already verified database, replace `NEW_RUN` with `m6_20260910`.
Outputs are JSON. `find` matches a complete label after trimming and case folding;
it returns all matching candidates. `last_seen` returns the candidates with the
latest original source timestamp, retaining ties. Unknown labels return
`NOT_FOUND` and an empty object list. This is closed-vocabulary retrieval, not
language understanding or a live statement that an object is still present.

## Evidence, Association And Persistence

`scripts/scene_memory.py` accepts a complete metric `MEASURED` M5 report. It
checks count consistency, finite coordinates, rigid transforms, camera/map point
agreement and source timestamps using the existing association helper. Rejected
depth cannot carry a camera/map point. Producer, map and exported-pose identities
are fixed within one database. This boundary consumes the saved M5 evidence;
it does not revalidate the bag or physically remeasure depth.

The four SQLite tables have direct roles:

| Table | Stored evidence |
| --- | --- |
| `metadata` | Frozen map/pose hashes, model/settings/runtime, coordinate conventions, producer limitations and association policy |
| `frames` | Unique node/source stamp and canonical original frame evidence, including every detection, camera calibration/pose, source hashes and depth statistics |
| `objects` | Provisional label, mean map surface point, distinct supporting-frame count, first/last source times, separate detector-confidence sum and last observation reference |
| `associations` | One decision per source detection, object ID or null, selected match distance and same-frame representative index |

Only runtime timing fields, first-call flags and annotation filenames are excluded
from canonical frame equality. Detection order is normalized by detection index.
Original run reports and PNGs remain in the local M5 directory. Importing the
same evidence again, including the second M5 run with different timings, adds no
frame, observation or support. Different evidence for an existing node or source
stamp causes a conflict; it never overwrites the old observation.

Association uses a documented baseline, without calibrated identity guarantees:

1. Replay all retained frames by original nanosecond source time. Within a frame,
   process higher detector confidence first, then detection index for ties.
2. A detection with the same label as an earlier representative in that frame is
   considered overlapping when its map point is within **0.35 m** and box
   intersection covers at least **50% of the smaller box**. Record its link and
   distance as `same_frame_overlap`, without another position/confidence update.
3. Other accepted detections select the nearest same-label object within 0.35 m,
   breaking equal-distance ties by object ID. An object already used by another
   representative in this frame cannot receive a second update. Unmatched
   detections create a new provisional object.
4. Each representative contributes equally to the map-point mean. Its detector
   confidence is accumulated separately and exposed as a mean. It is not used
   as a position weight or treated as a covariance. No uncertainty is fabricated.

Every accepted representative has a `new_object` or `nearest_match` decision.
Depth rejections have `depth_rejected` and null object/position association.
The raw detection and policy remain available to reconstruct each decision.
Close objects, wide boxes and viewpoint-dependent surface samples can still
cause false matches or splits; same-frame suppression is a heuristic.

New evidence triggers a deterministic replay of this small retained corpus.
This makes reversed frame order and different import batches yield identical
logical tables. Existing IDs remain identical for the same corpus, but adding
older evidence can renumber provisional objects. These IDs are not permanent
external identifiers. Rebuilding all associations is an offline baseline, not
an evaluated streaming/scaling design.

The import, raw evidence inserts and derived-object rebuild run in one SQLite
transaction with foreign keys enabled and a five-second lock timeout. Failures
roll back the entire import. Connections close explicitly on success and
exceptions. Queries open an existing database read-only and use one read
snapshot; a missing database is an error, not a newly created empty memory.
Unknown schemas or incompatible map/pose/producer/policy changes are refused.

## Measured Acceptance

Evidence: `data/outputs/scene_memory/m6_20260910/`. The source is
`data/outputs/object_observations/m5_20260910/trial_01/observations.json`, SHA256
`35c7738441daeaf665e0e725508bc2f13a6846cc0ca3dbef03d90eec32d821ec`.

| Result | Measurement |
| --- | --- |
| Frames / original detections | 3 / 18 |
| Depth-accepted / rejected | 15 / 3 |
| Supporting / same-frame overlap observations | 13 / 2 |
| New objects / cross-frame matches | 9 / 4 |
| Database size | 49152 bytes |
| Integrity / foreign-key checks | `ok` / zero violations |

Object 1 is the provisional `refrigerator`: three supporting frames (7, 14, 32),
mean point **[4.675447, 0.911362, -0.794313] m**, mean detector confidence
0.921856, first source time `1789080208207783000` ns and last source time
`1789080265488456000` ns. `last_seen` retains node 32's actual detection and depth
evidence. Map z is relative to the saved map origin, not measured floor height.

`integration.json` records 13 fresh CLI processes: successful imports/queries
plus three expected failures. Read-only queries and two duplicate imports left
the primary database byte-identical. Importing nodes 32, 14 and 7 separately
into another database produced the same complete logical SQL dump. All source
detections/provenance were retained, all nine means matched independently
computed source means, and no object had multiple supports from one frame.
Wrong pose identity and incomplete-report imports left the database unchanged;
a missing-database query failed without creating a file.

The first import's measured operation time was 29.850 ms. Ten subsequent
successful import/query operations had min/median/P95/max of
1.780/6.701/20.847/21.135 ms. Across all 13 CLI processes, wall time was
508.219/522.186/544.231/555.822 ms (min/median/P95/max), including interpreter
and dependency startup. These mixed operations on three frames are functional
timings, not a throughput or scalability benchmark. Runtime was Python 3.10.12,
SQLite 3.37.2 on aarch64.

Focused verification:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/memory -v
```

All **17 memory tests** pass, including native SQLite write-failure rollback,
source conflicts, unsupported schemas, duplicate imports, label/distance gates,
same-frame overlap, tied query candidates and reordered batches. The existing
**21 mapping/observation tests** also pass. Final code passes fresh import,
reopened query and duplicate-import checks in `final_check.json`, with the same
logical database as the initial verified run.

Nine candidates do not establish nine distinct real objects. The M5 likely
`laptop`/`oven` mislabels remain provisional, and chair identity is unconfirmed.
No manual label correction, mapping refinement, covariance estimation, live
integration, navigation or physical object-identity acceptance is claimed.
All room observations and SQLite artifacts remain local and ignored.

Next: connect these remembered candidates to an offline search-goal preview on
the existing map, before adding physical motion or upgrading perception models.
