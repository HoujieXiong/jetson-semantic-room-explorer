# Reusing the text encoder for bounded queries

Status: `VERIFIED` on Jetson Orin Nano for one stationary recorded-data run at
0.25x, plus four identical-prefix GPU comparisons. This reduces repeated query
startup; it does not establish recognition accuracy, real-time capture or navigation.

## Small implementation and ownership

`online_search_preview.py --session-requests N` owns one MobileCLIP-S0 encoder
and calls the existing search composition for each JSON-lines request. There is
no new service, dependency, model, ranking policy or geometry cache. The ordinary
`--text` command remains available. Python API callers can supply a caller-owned
`encoder` to `query_text` or `run`; its loaded identity must match the journal.

Initialization checks the full declared encoder identity. Every request checks
it again before encoding its exact phrase, including checkpoint, implementation,
packages, device, preprocessing policy and square padding. The actual SQLite
snapshot independently checks identity during ranking, including changes between
precheck and snapshot acquisition. Each request reconstructs associations and
geometry from a new committed prefix. It does not refresh evidence timestamps.
Localized and unlocalized results, fixed thresholds and planning refusals remain.

The main-thread Linux session accepts 1–32 requests, each a newline-terminated
JSON object containing only `text`, at most 4,096 bytes. It stops at its request
limit or clean EOF. Malformed input, incompatible identity, encoding failure,
output collision or timeout fails explicitly. Initialization/idle/response timers
are 60/60/45 seconds. Native calls can defer Python signal handling; the recorded
supervisor also enforces external initialization/response deadlines and bounded
SIGINT/TERM/KILL cleanup. It stops the trial below 1 GiB available system RAM.
The session has no ROS publication or simulated-start mode.

Standard output contains one `READY` object followed by one completion object
per request; model/render diagnostics use standard error. Each response names
`request_NNN/`, containing the existing `search.json`, `query/query.json`, crop
review HTML and applicable preview PNG. `session.json` records completion or
failure, timings and process resource peaks. Model initialization is separate
from request latency; a reused request reports `load_ms: 0` and
`encoder_reused: true`. CUDA/RSS peaks are process lifetime measurements.

## Measured concurrent behavior

The same 944-pair stationary recording, retained-node mapping, 1280 detector,
complete-crop square padding and unlocalized producer option are reused. Exact
phrases are scheduled at 40/95/150/205 seconds after player-process launch.
The producer initializes first, then the query process becomes ready before
SLAM and playback start.
The camera stays closed; no goal/path is published and no motion occurs.

One-time process launch to `READY` takes **14.660 s**, including **13.759 s** of
model initialization. Full response includes text inference, a fresh snapshot,
planning, review rendering and protocol delivery:

| Exact phrase | Preserved cold response | Reused encoder response | Text encoding | Snapshot work |
| --- | ---: | ---: | ---: | ---: |
| `a fridge` | 28.419 s | 3.445 s | 1,346.255 ms | 64.781 ms |
| `a bowl` | 19.173 s | 1.513 s | 18.396 ms | 128.838 ms |
| `a trash can` | 16.324 s | 1.190 s | 25.672 ms | 200.412 ms |
| `an elephant` | 16.319 s | 0.822 s | 19.382 ms | 274.610 ms |

The first request still pays first text-inference and renderer costs. Across all
four responses, median/P95 is 1.351/3.155 s; for the three later responses it is
1.190/1.480 s. These are small-sample descriptive statistics. There is no claim
that steady response time is just the 18–26 ms text-encoding time.

Fresh event prefixes advance through **180, 438, 669, 927**, with graph events
175, 427, 658, 927. Fridge retrieves six separate unlocalized source views, top
`4:0` at 0.285605, while the incorrect localized region remains selected. Bowl
selects the previously confirmed image region at 0.250959. Trash retains the old wrong region;
elephant has no selected candidate. Fridge/bowl/trash have no route; elephant
refuses an unknown start. Final prefix 1200 / graph 1188 retains 45 fridge views
and two bowl-region records. All closed queries refuse stale map evidence.

The cold run reads different prefixes. For example, its fridge snapshot covers
14.866 s of source time versus 9.309 s here. Faster responses change when the
snapshot is acquired; changed bowl selection is not an accuracy improvement
attributable to encoder reuse. Wrong identities, marginal scores and duplicate
records remain visible. No threshold or association option was changed.

| Measurement | Preserved cold enabled run | New warm run |
| --- | ---: | ---: |
| Sensor / perception pairs | 944 / 944 | 944 / 944 |
| Processed / explicitly dropped | 612 / 332 | 614 / 330 |
| Tracked / lost odometry outputs | 943 / 0 | 943 / 0 |
| Accepted / refused source poses | 606 / 6 | 609 / 5 |
| Encoded / refused keyframes | 45 / 19 | 45 / 19 |
| Encoded localized / unlocalized crops | 97 / 63 | 96 / 63 |
| Final graph nodes / journal events | 64 / 1200 | 64 / 1200 |
| Peak system RAM, tegrastats MB | 5481 | 5374 |
| Observer peak CUDA allocated / reserved bytes | 329904128 / 356515840 | 330952704 / 379584512 |
| Supervisor duration | 398.774 s | 402.068 s |

The new query process peaks at 228,483,584 allocated and 243,269,632 reserved
CUDA bytes, with sampled RSS at most 1,420,520 KiB. Writer/pending-semantic queues
peak at 7/1 within capacities 16/8; RGB cache peaks at 32. Independent scheduling
intervals give pending/inference/pose-wait peaks 1/1/7. One input lacks odometry;
source-pose refusals are one missing odometry and four missing map TF cases.
No inference fails, semantic queue overflows, crop-budget omissions or pending
jobs remain at close. One semantic keyframe is pose-rejected and 18 are dropped.

Detection-plus-depth median/P95 is 107.026/136.682 ms; arrival-to-result is
492.288/1539.237 ms, compared with 491.204/1550.531 ms previously. **329 of the
330 dropped frames occur outside request-response intervals**, classified by
arrival time. A loaded model also remains resident between queries. This single
comparison does not isolate a throughput or memory delta, or identify all drop
causes. GPU temperature peaks at 55.281 C; already nonzero swap rises from
1703 to 1896 MB. Final read-only power-mode inspection reports 25 W.

## Result preservation and verification

All 52 focused online-memory/search tests pass, including real SQLite commits,
immutable earlier reports, exact phrases, identity changes, malformed/oversized
requests, EOF, idle timeout, output collision and request limits.

Four new frozen copies preserve the exact during-query prefixes and original
source timestamps. A fresh GPU CLI and one reusable GPU encoder independently
encode each phrase against those same prefixes. The predeclared maximum allowed
vector/score error is 1e-6, with exact ranking order and crop identities. Measured
vector and semantic differences are **zero**, also matching the original concurrent
reports. Geometry, source evidence and snapshots match exactly. Old map timestamps
remain old; all copied-prefix planning decisions refuse stale evidence.

These standalone cold commands take 13.293–15.930 s; warm calls take
0.179–0.452 s after separate 10.141 s initialization. Their stale-map branch skips
route/frontier rendering and has no concurrent SLAM, so these are not the warm
concurrent-response numbers. Actual tokenizer overflow and padding mismatch fail
explicitly; a normal API query still succeeds after the tokenizer refusal.

Independent bag decoding verifies all 159 crops, raw RGB/depth pixels, metric
projection and source-time transforms. Recomputed scalar geometry/3D/visual
scores have maximum errors 4.45e-16 m / 5.51e-8 / 4.96e-8. All eight during/closed
queries and eight reopening comparisons pass. Independent subscribers verify
64 graph and 64 occupancy messages. All 157 common-source crops/vectors match
exactly between the preserved cold and new runs. The 104 declared original input
hashes and trial runtime source hashes remain unchanged.

All owned processes exit without forced termination; telemetry has its expected
SIGINT exit. Final native inspection finds no runtime process and 5,246,764 KiB
available RAM. This bounded run is not a long-duration resource-leak acceptance.
The browser review contains 12 query sections and 79 verified embedded PNGs.

## Run and inspect

From the repository root, using a fresh output directory:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  ../mobileclip-env/bin/python scripts/online_search_preview.py \
  --db data/outputs/warm_queries/20260916/unlocalized/online.db \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --session-requests 4 --output data/outputs/manual_warm_query <<'JSONL'
{"text":"a fridge"}
{"text":"a bowl"}
{"text":"a trash can"}
{"text":"an elephant"}
JSONL
```

This saved journal produces retrospective retrieval and stale-map refusals.
A caller querying a concurrently written journal sends each next JSON line after
receiving the preceding completion. The producer remains the owner of that journal.

```bash
xdg-open data/outputs/warm_queries/20260916/review.html
```

Private evidence is under `data/outputs/warm_queries/20260916/`: predeclared
acceptance and preserved hashes, supervisor/checker source, `unlocalized/`,
`frozen/`, verification logs, `comparison.json`, `cleanup.json` and the review.
For another replay, copy the local harness into a fresh directory at the same
depth; it refuses existing case directories. The recorded launch was:

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  data/outputs/warm_queries/20260916/run_trial.py unlocalized
```

The [moving-recording follow-up](moving-warm-queries.md) now verifies six queries
across changing views and graph revisions, including a remembered bottle view
without a 3D target. It preserves all stationary measurements here.
