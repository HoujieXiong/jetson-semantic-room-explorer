# Observation-To-Search Replay

Status: `VERIFIED` on the Jetson, 2026-09-11, for chronological import of saved
observations, frozen memory prefixes and source-associated search decisions.
The bottle query changes from missing to remembered when accepted depth evidence
arrives. Earlier snapshots remain unchanged after later imports.

## Run And Inspect

```bash
cd ~/projects/jetson-semantic-room-explorer
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  scripts/replay_observation_search.py \
  --observations data/outputs/object_observations/m5_20260910/trial_01/observations.json \
  --mapping data/outputs/rtabmap_slam/mapping_02 \
  --label bottle \
  --simulated-start-xy 1.65 0.08366 \
  --output data/outputs/observation_replay/NEW_RUN
```

Use a new output directory for every invocation. All inputs and dependencies
are local. The replay consumes existing detections, depth results and final map
poses; it does not run inference, capture, ROS or physical motion.

`replay.json` records source identity, original nanosecond timestamps, per-frame
query detections and depth rejection reasons, import counts, snapshot hashes,
query/branch/outcomes and links to each search report. Paths in it are relative
to `replay.json`. Each `node_ID/` contains a frozen `memory.db` and the existing
`search/search.json`, goal/route/frontier reports and PNGs. Paths inside
`search.json` remain relative to that file. Full original observations are
retained in SQLite and linked to the unchanged source report.

The measured transition can be inspected on the Jetson display:

```bash
xdg-open data/outputs/observation_replay/replay_20260911/bottle/node_7/search/frontier/frontier.png
xdg-open data/outputs/observation_replay/replay_20260911/bottle/node_14/search/route/object_4.png
```

## Snapshot And Failure Contract

The existing observation validator checks the whole source report and sorts
frames by source timestamp. The frozen map/pose loader validates its identity
before any memory import. For each frame, the replay copies the preceding
private, closed SQLite file to a new node directory and imports the accumulated
prefix using the existing transactional importer. Previously imported frames
are duplicates; exactly the newly arriving frame is added. No earlier snapshot
is reopened for writing. This small offline corpus does not need a new database
schema, replay framework or SQLite snapshot service.

The existing search command runs against that new prefix. Future copies/imports
cannot invalidate earlier search reports' memory hashes. The replay checks
snapshot and search-report hashes at completion and checks that the original
observation file has not changed. Producer settings, association rules, source
timestamps and all accepted/rejected detections remain intact; only the existing
memory normalization excludes timing/annotation fields and sorts detections.

`REPLAY_COMPLETE` means every prefix produced a completed search decision or
refusal. Inspect each `search_status`: an invalid start can produce
`INVALID_START` in the frontier branch or `NO_ROUTE` with per-object
`INVALID_START` outcomes in the object branch. A completed replay does not mean
an object was physically found. No extra stopping/confidence rule is added.

Input, identity and processing errors propagate with nonzero exit. Once the
output directory exists, `replay.json` remains `INCOMPLETE`, retaining completed
steps, the failing `active_stage`/`active_node`, and expected input/I/O/database
error details. A failed step may have partial files. Reusing an output directory
fails without modifying its earlier reports; a previous successful report is
not success for the rejected invocation. Missing start arguments fail before
creating output.

The existing importer requires at least one accepted observation in a report.
Therefore the earliest prefix must contain an accepted observation of some
label; a first frame containing only rejections fails explicitly. Later frames
with only rejected detections are supported because the cumulative prefix has
accepted evidence. This boundary was tested without changing the memory policy.

## Measured Evidence

Local evidence: `data/outputs/observation_replay/replay_20260911/`, including
`integration.json`, `verify_replay.py`, `verification.log`, `search_tests.log`,
`memory_tests.log`, `final_check.json`, per-command logs and generated snapshots.
The original source SHA256 is
`35c7738441daeaf665e0e725508bc2f13a6846cc0ca3dbef03d90eec32d821ec`.

The primary timeline uses the explicit simulated start **[1.65,0.08366] m**:

| New node | Original source time (ns) | Prefix detections / provisional objects | Bottle evidence and decision |
| --- | --- | --- | --- |
| 7 | 1789080208207783000 | 7 / 3 | Detection 5 rejected: `insufficient_valid_depth`; `NOT_FOUND` → frontier group 39, in-place -Y view |
| 14 | 1789080215242330000 | 13 / 7 | Two accepted observations create candidates 4/6; `FOUND` → object routes of 0.75/0.60 m |
| 32 | 1789080265488456000 | 18 / 9 | No new bottle observation; both candidates, source times and support counts remain unchanged |

Candidate 4's goal is **[1.55,0.73366] m**, reached through 16 grid cells;
candidate 6's is **[1.70,0.63366] m**, through 13 cells. The reused route checker
reports minimum segment clearance approximately **0.257391 m** for each,
against the unchanged assumed 0.25 m policy. Both objects remain provisional,
with one supporting frame each and last-seen time from node 14, even after node
32 is imported. No additional support or current-presence claim is fabricated.

Prefix databases contain exactly nodes [7], [7,14] and [7,14,32], and occupy
32768/45056/49152 bytes. Independent SQL checks reproduce every normalized
source frame/detection, preserve the rejected bottle's null object association,
and pass integrity/foreign-key checks. The final complete logical SQL dump equals
the original M6 database, retaining 18 observations, 13 supports, two overlaps,
three rejections and nine provisional objects.

All **78 search tests** and **17 memory tests** pass. Fifteen new replay tests
exercise real temporary SQLite and synthetic maps through the existing search
functions; only PNG rendering is stubbed. They cover time ordering, transitions,
prefix isolation, full-import equivalence, duplicates, rejection-only frames,
invalid starts, source corruption, partial failure and output protection.

Fourteen fresh CLI processes, each bounded at 90 seconds, verify:

- Primary, repeated and reversed-input bottle replays: identical decisions and
  byte-identical corresponding snapshots after sorting by source time.
- A replay with explicit simulated coordinates [-0.002109,-0.03223] m: all
  prefixes refuse the unknown-cell start while preserving the memory transition.
  These coordinates coincide with recorded node 1 but are explicitly simulated
  inputs to this command, not newly measured localization.
- Incompatible pose identity and source timestamp disagreement: exit 1,
  `INCOMPLETE` before imports, with no database or PNG.
- Missing start: exit 2; reused output: exit 1 with all previous evidence intact.
- Three fresh duplicate imports into isolated copies: zero added frames, byte
  hashes unchanged. Three fresh read-only snapshot queries reproduce the missing/
  remembered results and preserve snapshot hashes.

All original input hashes remain unchanged. Existing memory and search runtime
files are unchanged. All **40 PNGs** decode; node 7's frontier and both node 14
bottle-route overlays were visually inspected.

Across the four completed three-prefix replays, operation-time
min/median/P95/max is **9738.501/11035.504/11060.200/11060.587 ms**; process
wall time is **10644.382/11929.296/11954.510/11954.601 ms**. These mixed normal/
refusal runs include source checks, imports, copies and rendering; wall time
includes dependency startup. They are functional timings, not sustained live
performance. Runtime: Python 3.10.12, SQLite 3.37.2, NumPy 1.26.4 and OpenCV
4.11.0 on aarch64.

The map and optimized poses are final frozen exports shared by every prefix.
There is no claim of causal online mapping, observations acquired at selected
goals, new coverage or motion. Map/floor accuracy, partial tracking, provisional
labels/identity and actual localization remain unresolved. Next, connect the
existing RGB-D observation producer to this replay for one offline command from
saved RGB-D frames to search decisions.
