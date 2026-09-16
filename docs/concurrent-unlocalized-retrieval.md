# Unlocalized retrieval during concurrent recorded playback

Status: `VERIFIED` on Jetson Orin Nano for one bounded, ordered baseline/enabled
comparison at 0.25x playback. The new visual path retrieves the stationary fridge
region before playback ends while SLAM, detection and encoding run together.
Stable recognition, real-time input and physical navigation remain unverified.

## Controlled scope

Both trials use the same 944-pair stationary recording, 1280 detector input,
complete-crop square padding, retained-node mapping overlay, model weights and
source code. The only producer option difference is
`--semantic-include-unlocalized`. Actual queried odometry/mapping parameters match,
apart from each run's fresh database path. Source images remain 1280x720.

The existing local supervisor is copied into a fresh experiment directory. It
retains its typed-message player, subscriber gate, 1 GiB available-memory guard,
45-second query timeout and bounded child cleanup. The camera remains closed.
Queries compute search previews without publishing goals or paths. An independent
ROS receiver still records graph/grid messages for verification.

The only tracked runtime change adds peak allocated/reserved CUDA byte counts to
the existing observer report after GPU initialization. Scheduling, inference,
depth/pose acceptance, text thresholds and planning rules remain unchanged.
All 44 relevant odometry/concurrency tests pass.

Before launch, exact phrases are scheduled at 40/95/150/205 seconds after the
player process starts: `a fridge`, `a bowl`, `a trash can`, `an elephant`.
Actual message playback begins after its subscriber gate; both clocks are saved.
Each query is a separate real GPU CLI process and reads its own committed prefix.
After shutdown, four new API queries reuse those exact GPU text vectors without
model reload or retroactive journal changes. Their timings are reported separately.

## What reached the query

| Query | During baseline playback | During enabled playback | After shutdown |
| --- | --- | --- | --- |
| `a fridge` | Old incorrect localized candidate | Same incorrect localized region, plus 10 selected unlocalized fridge views | Enabled run retains 45 selected fridge-region views |
| `a bowl` | No candidate above threshold | No candidate above threshold | Both runs select bowl/sink records covering the bowl region |
| `a trash can` | Old incorrect localized region | Same failure; no selected unlocalized view | Failure remains in both runs |
| `an elephant` | No candidate above threshold | No candidate above threshold | No selected candidate in either run |

The enabled fridge query reads event prefix 283 / graph event 270. It starts
38.927 seconds after actual playback begins and finishes at 67.345 seconds,
well before playback finishes. Top visual source `4:0` scores 0.285605; its crop
shows the fridge door and matches original bag pixels. All ten selected views
overlap the previously confirmed fridge region. The final top view `58:0` scores
0.288479, with 45 selected observations. These are source views, not 45 objects or
new operator confirmations. Every view retains its missing-depth refusal and has
no accepted 3D target.

Baseline/enabled fridge snapshots cover 13.058 / 14.866 seconds of source time;
model-startup variation changes the exact data available at each read. Other
checkpoints also differ. No claim of matched-prefix recognition improvement is
made. On the 91 proposals encoded from the same source timestamps/detection
indices in both runs, crop hashes and vectors are bit-identical.

At the final snapshots, the baseline bowl/sink scores are 0.253651 / 0.253645;
enabled scores are 0.253827 / 0.254391. The earlier bowl failures remain recorded.
Optional duplicate-track merging is not enabled in this comparison. Existing
depth holes, duplicate records and incorrect localized identity remain limitations.

During playback, fridge/trash decisions are `NO_ROUTE`; bowl/unknown decisions
are `INVALID_START`. Independent grid checks put each start in an unknown cell.
Selected unlocalized views also retain `unlocalized_visual_evidence` refusal.
All post-shutdown decisions refuse stale map evidence. No route is selected,
published or executed; timestamps are never refreshed to make old maps usable.

## Measured workload and resources

| Measurement | Baseline | Unlocalized enabled |
| --- | ---: | ---: |
| Complete sensor-contract pairs | 944 | 944 |
| Perception synchronized pairs | 943 | 944 |
| Processed / explicitly dropped frames | 611 / 332 | 612 / 332 |
| Accepted / refused processed source poses | 605 / 6 | 606 / 6 |
| Tracked / lost odometry outputs | 943 / 0 | 943 / 0 |
| Final graph nodes | 64 | 64 |
| Encoded / refused keyframes | 43 / 21 | 45 / 19 |
| Encoded crops | 92 | 160: 97 localized, 63 unlocalized |
| Journal events | 1,199 | 1,200 |
| Writer queue peak / capacity | 3 / 16 | 6 / 16 |
| Semantic pending peak / capacity | 2 / 8 | 1 / 8 |
| Peak system RAM, tegrastats MB | 5,356 | 5,481 |
| Observer peak CUDA allocated bytes | 328,331,264 | 329,904,128 |
| Observer peak CUDA reserved bytes | 354,418,688 | 356,515,840 |
| Supervisor duration | 419.192 s | 398.774 s |

Baseline has one unmatched complete sensor group; its semantic outcome explicitly
reports `source_not_received`. Both runs retain one pose-rejected keyframe;
19/18 additional requests refer to dropped observations. Each run has two missing
source-odometry and four missing-source-map-TF pose refusals. One sensor input has
no odometry output. No inference fails or pending job remains at close.

Both runs keep a 32-frame RGB cache; 579/580 evictions are counted. Independent
interval reconstruction gives pending/inference/pose-wait peaks 1/1/7 against
limits 1/1/8. There are no semantic queue or crop-budget omissions. The two extra
eligible keyframes in the enabled trial also add five localized crops; therefore
the 68-crop total difference is not entirely the optional visual work.

| Latency, median / P95 | Baseline | Enabled |
| --- | ---: | ---: |
| Detector call | 93.657 / 118.760 ms | 93.516 / 121.781 ms |
| Detection plus depth | 105.414 / 136.716 ms | 105.079 / 138.905 ms |
| Pose wait | 372.635 / 1,447.305 ms | 368.774 / 1,401.186 ms |
| Arrival to result | 489.992 / 1,604.385 ms | 491.204 / 1,550.531 ms |

The 63 extra visual crops take 5.927 seconds of summed encoding time, with
median/P95/max 88.797/142.961/164.901 ms. This includes concurrent contention;
standalone crop timings do not predict this cost. Peak GPU temperature is
55.375/55.218 C. Swap begins at an already nonzero 1,485/1,696 MB and peaks at
1,728/1,871 MB. Post-run power-mode inspection reports 25 W.

The eight during-playback CLI queries take 16.319–28.419 seconds each, including
10.951–18.387 seconds of model loading. Snapshot query work takes only
106–322 ms. Closed API queries with previously computed text vectors take
318–403 ms for the snapshot; they are not warm text-inference measurements.
Fresh process/model startup is a measured source of user-visible delay.

Single sequential trials do not isolate throughput changes, steady memory growth
or the cause of every dropped frame. Most drops occur outside the query-process
intervals: 270/332 baseline and 253/332 enabled, classified by frame arrival time.
Removing query startup alone should not be assumed to solve frame loss.

## Independent verification and evidence

The original bag is decoded independently for each run. Received RGB/depth bytes, metric
depth samples, source-time TF reconstruction and all 252 saved crop arrays verify.
All journal observations match producer evidence; graph/grid payloads match 64
independent messages of each kind per run. Geometry is recomputed from point
lists; scalar vector fusion and per-view selection reproduce all 16 actual
during/closed query reports. Maximum coordinate error is 6.67e-16 m and maximum
visual cosine error is 4.96e-8; these are numerical checks, not physical accuracy.

Copied during-query prefixes and closed journals reproduce 16 reopening checks
exactly. Source/model/feedback/previous-journal and declared runtime hashes remain
unchanged. All owned runtime processes close without forced termination;
telemetry receives its expected SIGINT. Native cleanup finds no matching runtime
processes and 4,824,140 KiB available RAM. This is bounded cleanup evidence.

Private evidence is under `data/outputs/unlocalized_concurrent/20260916/`:
`acceptance.json`, the adapted supervisor/check scripts, `baseline/`,
`unlocalized/`, source/configuration archives, raw ROS witnesses, per-run
verification reports, `comparison.json`, `cleanup.json`, test logs and
`review.html`. The local combined-review builder initially assumed an explicit
HTML body tag; its retained failure was fixed in that helper. Both native query
pages and runtime trials were unaffected. All 83 embedded review PNGs decode.

```bash
xdg-open data/outputs/unlocalized_concurrent/20260916/review.html
```

The recorded supervisor commands were:

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  data/outputs/unlocalized_concurrent/20260916/run_trial.py baseline
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  data/outputs/unlocalized_concurrent/20260916/run_trial.py unlocalized
```

These measured output directories already exist. To repeat, copy the local
supervisor/helpers into a fresh experiment directory at the same directory depth;
the supervisor refuses existing case directories. Public producer/query commands
and policies are in [online semantic memory](online-semantic-memory.md) and
[unlocalized visual evidence](unlocalized-visual-evidence.md).

The [bounded reusable-encoder follow-up](warm-text-queries.md) now measures this
startup reduction while preserving fresh reads and identity checks. That separate
trial leaves all cold measurements here unchanged; frame drops remain.
