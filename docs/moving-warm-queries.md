# Moving RGB-D replay with bounded warm text queries

Status: `VERIFIED` on Jetson Orin Nano for one bounded 0.25x replay of the existing
forward/backward recording. Changing camera views feed SLAM, persistent semantic
memory, repeated text queries and explicit planning decisions. This is recorded-
data integration; sustained live throughput and physical navigation are unverified.

## Scope and preserved inputs

No runtime code changes were necessary. The local harness from
[warm text queries](warm-text-queries.md) uses the original 899-pair / 60.224296 s
bag, its previously verified typed-message reference, and six requests to one
loaded query encoder. The camera remains closed; query ROS publication is off.

The producer retains the current 1280 detector input, complete-crop square
padding, separate unlocalized views and retained-node mapping overlay. Optional
duplicate merging is off. The older moving experiments used 640 detection,
center crops, geometric-only encoding, graph-node merging and cold query processes.
Their source eligibility, query times and starts also differ. Their reports stay
unchanged; they are not controls for a causal accuracy or throughput comparison.

Before launch, exact requests were scheduled at 30/70/110/150/190/225 seconds
after player-process launch. The model initializes before SLAM/playback. Existing
1 GiB available-memory, 75 s external initialization and 45 s response guards,
subscriber readiness checks, final DDS acknowledgements and bounded owned-process
cleanup remain. All models, recordings and dependencies were already local.

## Actual queries while the view changes

Launch-to-READY takes **14.604 s**, including 12.178 s model loading. Each response
includes actual text encoding, a fresh committed snapshot, planning and applicable
HTML/PNG rendering. Source coverage below is relative to the first RGB timestamp.

| Request | Source coverage | Event / graph prefix | Full response | Selected evidence / planning |
| --- | ---: | ---: | ---: | --- |
| `a fridge` | 7.301 s | 141 / 138 | 2.618 s | Localized fridge record, 0.308607; invalid start, with insufficient object stand-off clearance |
| `a refrigerator` | 17.147 s | 325 / 308 | 1.109 s | Same provisional record, 0.308996; same planning refusals |
| `a kitchen sink` | 26.994 s | 512 / 498 | 1.601 s | Sink record, 0.276272; no route from unknown start |
| `a bottle` | 36.908 s | 700 / 688 | 0.537 s | One unlocalized source view, 0.256799; explicit refusal to use it as a 3D target |
| `an elephant` | 47.157 s | 893 / 877 | 1.546 s | No candidate above threshold; frontier planning refuses unknown start |
| `a fridge` | 55.798 s | 1058 / 1051 | 1.296 s | Localized fridge record, 0.313795, plus three separate unlocalized views; invalid start |

The bottle answer recalls source `16:4`, captured at **15.071 s**, after the
camera view has changed. Its 32x118 crop at `[12, 451, 44, 569]` matches original
pixels and visually shows part of a red-capped bottle at the image's left edge.
This is an assistant visual inspection, not a new operator identity label.
The original `insufficient_valid_depth` refusal remains; no position or target
is inferred from the crop. Its shorter response also skips route rendering.

Fridge and sink selected crops visually correspond to those fixtures. Cosine
scores remain uncalibrated and no recognition-accuracy claim follows from this
small, previously seen scene. Unknown rejection here covers one phrase only.

The first text encoding takes 1187.401 ms; the next five take 18.213–24.518 ms.
Snapshot work takes 106.727–968.678 ms. Complete response median/P95 is
1.421/2.363 s across six requests, or 1.296/1.590 s across the five later requests.
These are small-sample measurements, not model-only latency or steady service FPS.

## Map revisions and historical answers

Independent reconstruction observes **1,524 historical-node translation updates**
larger than 1e-6 m across consecutive graph revisions; the largest single update
is 0.004404 m. Each query uses the graph available in its own committed prefix,
including its original source-time observation/pose refusals. Final poses never
replace earlier query evidence.

Eligible geometric supports grow through 37/98/176/261/334/385 across the six
queries, with 10/19/23/24/26/29 provisional records. Comparing peer groups only
among source supports shared by consecutive snapshots finds no reassignment in
this run. New supports and records are added; this does not prove stable physical
object identity, nor a response to a large loop-closure correction.

After shutdown, prefix **1139 / graph 1125** has 59 eligible frames and 31
provisional records with 408 geometric supports. Six retrospective queries reuse
the exact original GPU text vectors. Fridge and sink remain selected; bottle
remains unlocalized; elephant remains unselected. Every closed query refuses stale
map evidence. Twelve reopening comparisons reproduce both copied during-query
prefixes and closed-journal results exactly, including geometry, ranks, crop/source
identities and planning evidence. Earlier report files are preserved.

The estimated trajectory reaches 1.022 m from its first pose, ends 0.161 m away,
and accumulates 4.459 m of path including small movements and pose noise. The
operator described roughly one meter forward/backward with additional small
movements; the distance was estimated. These numbers are not physical scale
accuracy, return error or drift measurements.

## Workload, resources and independent checks

| Measurement | Result |
| --- | ---: |
| Sensor / perception pairs | 899 / 899, no unmatched image/info stamps |
| Processed / explicit drops / inference failures | 893 / 6 / 0 |
| Tracked / reported lost odometry outputs | 898 / 0; one input without output |
| Accepted / refused processed source poses | 887 / 6: one missing odometry, five missing map TF |
| Mapping / graph / occupancy events | 60 / 60 / 60; 60 final graph nodes |
| Encoded / refused semantic keyframes | 59 / 1; original source-pose refusal |
| Encoded localized / unlocalized crops | 416 / 65 |
| Journal events | 1139 |
| Writer / semantic pending / RGB cache peaks | 3 / 1 / 32 |
| Independent pending / inference / pose-wait peaks | 1 / 1 / 8 |
| System peak RAM / minimum sampled available RAM | 5242 MB / 2261676 KiB |
| Query sampled peak RSS | 1423852 KiB |
| Query peak CUDA allocated / reserved | 228483584 / 243269632 bytes |
| Observer peak CUDA allocated / reserved | 332001280 / 356515840 bytes |
| Supervisor duration | 391.566 s |

No semantic queue/crop-budget omission or pending job remains. All six frame drops
occur outside request-response intervals by arrival time. Detection-plus-depth
median/P95 is 116.271/166.893 ms; arrival-to-result is 493.819/562.302 ms. The 65
unlocalized crops take 6.386 s of summed encoding time, median/P95
96.174/149.999 ms, during concurrent execution. Scene and scheduling differ from
the stationary run; these figures do not isolate an optimization gain.

Peak GPU temperature is 56.250 C; already nonzero swap rises from 1812 to 2121 MB.
Power mode remains 25 W. Every owned runtime process exits without forced
termination; telemetry has its expected SIGINT exit. Final native inspection finds
no runtime process and 4,977,868 KiB available RAM. Long-duration leak behavior
remains unmeasured.

All 52 focused online-memory/search tests pass in 11.842 s. Independent bag
checks verify every received RGB/depth array, metric depth samples, source-time
TF and all **481 source crops**. Independent receivers verify all 60 graphs and
60 grids. Scalar association/ranking checks cover all 12 during/closed reports,
with maximum geometry/3D-score/visual-score errors of
1.78e-15 m / 5.44e-8 / 5.36e-8, within predeclared 1e-12 m / 1e-6 tolerances.
These numerical agreement checks are not physical accuracy measurements.

All 303 declared original inputs and 15 runtime source hashes remain unchanged.
The local diagnostic summaries initially used two relative-time origins differing
by 4.369 ms (earliest sensor header versus first RGB). Coverage and plots now
consistently use first RGB; initial summaries and the correction note are retained.
Original absolute timestamps, runtime reports, ranks and geometry were unaffected.

## Review and reproduction

The single review contains all six actual decisions and six retrospective query
sections, the estimated trajectory, available native map previews and 100 verified
embedded PNGs. It does not require WebGL:

```bash
xdg-open data/outputs/warm_moving/20260916/review.html
```

Private evidence under `data/outputs/warm_moving/20260916/` includes predeclared
`acceptance.json`, supervisor/checker source, `unlocalized/`, original graph/grid
witnesses, copied historical prefixes, all verification logs, `summary.json`,
`cleanup.json`, the time-origin correction and the review. Raw room data stays out
of Git. The recorded command was:

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  data/outputs/warm_moving/20260916/run_trial.py unlocalized
```

For a repeat, copy the local harness to a fresh directory at the same depth; case
directories must not already exist. The shared runtime and models need no changes.

Next: prepare one bounded stationary live-camera acceptance of the current full
pipeline, beginning only after the operator confirms the camera is steady and the
current scene is ready. Keep navigation disabled and preserve any live failures.
