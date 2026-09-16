# Bounded bowl retrieval during recorded RGB-D playback

Status: `VERIFIED` on Jetson Orin Nano for a bowl-region candidate reaching the
actual concurrent query, with independent source and prefix checks. This is one
0.25x saved-data trial. Stable recognition, unique object identity, live throughput
and physical navigation remain unverified.

The operator previously confirmed the displayed bowl and fridge crops. The new
query's best crop covers that same bowl region; it was visually inspected by the
assistant and verified against original pixels. It has not received a separate
operator label. The original three rejected queries remain unchanged.

## Small implementation change

The existing concurrent observer accepts `--imgsz 1280 --semantic-square-pad`.
`inference_config` permits the two measured sizes, 640 and 1280, with unchanged
confidence 0.25 and CUDA device. Warmup, real inference, the report and journal
use that same configuration. The writer rejects unsupported sizes or changed
confidence/device/depth policy before creating a journal.

The encoder keeps the complete RGB crop on a black square before its official
transform, as established by the [candidate audit](candidate-audit.md). Its mode
is part of the stored encoder identity. Online text queries read that mode before
model loading and require the full identity to match the committed snapshot.
Old journals keep their exact mode and results. Default detection size and
preprocessing, crop evidence, depth/pose/keyframe rules, thresholds and planning
remain unchanged. No new dependency or persistent service is added. The frozen
observation finalizer retains its original 640-only contract; this trial uses
the online journal.

## Input and measured results

The same complete-message stationary subset contains 944 synchronized RGB-D pairs
and 3,777 original ROS messages. It is replayed at 0.25x with the existing retained-
node mapping overlay, bounded queues, 1 GiB available-memory guard, three real
query processes and independent ROS receivers. The camera stays closed. Settings,
source copies, input hashes, commands, telemetry and exits are saved with the run.

| Measurement | Original 640 / center crop | 1280 / complete crop |
| --- | ---: | ---: |
| Sensor-contract input pairs | 944 | 944 |
| Perception synchronized pairs | 943 | 944 |
| Processed / explicitly dropped | 621 / 322 | 604 / 340 |
| Unmatched complete sensor groups | 1 | 0 |
| Accepted / refused source poses | 613 / 8 | 598 / 6 |
| Tracked / lost odometry outputs | 943 / 0 | 943 / 0 |
| Final graph nodes | 64 | 64 |
| Encoded keyframes / crops | 44 / 33 | 44 / 94 |
| Final provisional records | 3 | 5 |
| Committed journal events | 1,199 | 1,200 |
| Writer queue peak, capacity 16 | 5 | 3 |
| Peak system RAM, MB | 4,938 | 5,436 |
| Supervisor duration, s | 400.947 | 420.316 |

These sequential functional trials are not repeated performance measurements.
The changed run explicitly rejects 20 keyframes: 19 dropped source observations
and one refused source pose. Six processed-frame poses fail: two missing source
odometry and four missing source map TF. There are no failed or pending jobs at
close. One sensor input has no odometry result. Five records do not establish
five correctly identified physical objects.

Actual queries all finish before playback ends:

| Query | Committed prefix | Selected records and cosine | Result |
| --- | ---: | --- | --- |
| a fridge | 276 | ID 1, refrigerator: 0.274371 | Prior wrong region remains a failure |
| a trash can | 543 | ID 1, refrigerator: 0.253444 | Prior wrong region remains a failure |
| a bowl | 871 | ID 3, bowl: 0.251707; ID 2, sink: 0.250144 | Both best views cover the bowl region |

At the bowl query, the bowl record has 28 geometric/semantic supports and the sink
record has 11. Best crops come from nodes 37 and 44 at `[499,274,585,312]` and
`[506,274,592,312]`; the source image is the shallow bowl left of the fridge.
These likely duplicate records arise under the existing label-constrained
association policy. They are not two confirmed physical targets. Their small
margins above 0.25 make this a fragile result, not calibrated presence confidence.

All three decisions are `NO_ROUTE`: every selected object route refuses an
`unknown_cell` start. Each independent receiver gets exactly one decision, zero
goals and zero paths. No movement is commanded or executed.

The true central fridge appears in all 604 processed frames but every detection
fails `insufficient_valid_depth`, with valid fractions 6.84-11.46% against the
unchanged 25% requirement. This trial does not resolve those holes or supply a
3D fridge target. The 80-class detector still has no trash-can class.

## Same source-time cutoffs and independent checks

Actual queries are scheduled by supervisor elapsed time, so they read source data
4.286/4.286/3.282 seconds earlier than the respective original queries. To avoid
mistaking timing differences for a retrieval improvement, separate copies of both
journals are truncated at each original query's source-time cutoff. Each retains
only a contiguous committed prefix before the first later observation, mapping,
graph or occupancy header. Only the existing integer/double header-roundtrip
nanosecond tolerance is allowed; no future event is inserted or reordered.

At the original bowl cutoff `1789529900158789000` ns:

- The original prefix 932 still has one wrong-region object, score 0.157531,
  and selects nothing. Its 25 bowl-region proposals are all non-keyframes.
- The new prefix 932 selects bowl/sink records at 0.251519/0.250144. Forty
  bowl-region proposals have accepted depth/pose, eligible keyframes and committed
  image vectors. Region counts use IoU >= 0.5 with the confirmed reference box;
  this is a static-scene audit proxy, not fresh operator annotations.
- Both original fridge/trash cutoff results remain failures. All six copied
  prefixes reproduce independent point-list association and scalar semantic
  fusion. Reopening their planning evidence now refuses stale data; the reports
  clearly distinguish this retrospective comparison from actual online queries.

The original observations, operator feedback, models and input bag remain
byte-identical. All 94 new crop arrays match original bag pixels; valid depth is
checked in millimeters and independently projected into meters. TF reconstruction
uses only transforms received before each original pose decision. Maximum
independent point error is `8.89e-16` m, a numerical check rather than physical
accuracy. Scalar query scores agree within `4.92e-8`; six cutoff snapshots agree
in geometry within `4.45e-16` m. All 64 received graph/grid revisions match the
independent ROS witness. Closed-journal and earlier-recording reopening pass.

A separate real GPU query of the untouched legacy journal reproduces the entire
old snapshot, ranking, text vector and planning evidence exactly. Its encoder
identity is refused by the new padded journal. Invalid CLI size and missing
semantic-model options fail before GPU work/output creation. There are 28 mapping,
40 online-memory/semantic/search and 15 semantic-memory tests passing; the changed
semantic contract test also passes its focused rerun.

## Timing and resources

Over 604 processed frames, detector call time has mean 95.908 ms, median 93.219 ms
and P95 122.818 ms. Detection plus depth has mean 108.044 ms, median 105.111 ms and
P95 138.971 ms. Arrival-to-result latency, including pose waits, has mean 709.809 ms,
median 494.721 ms and P95 1,553.313 ms. Full query CLI times are
28.234/20.771/21.480 seconds, including their separate model loads. These are
concurrent saved-data measurements, not real-time camera FPS claims.

Peak GPU temperature is 58.312 C. Swap rises from a preexisting 1,068 MB to
1,437 MB. Telemetry power has median 6,673 mW and maximum 9,052 mW; the post-run
power-mode query reports 25 W. All owned processes exit without forced termination
or leftovers; telemetry is stopped with the expected SIGINT. Native post-check
finds 5,227,320 KiB available RAM. This is bounded cleanup evidence, not proof of
long-duration resource stability.

## Local reproduction and evidence

Acceptance and comparison evidence is in
`data/outputs/bowl_replay/steady_20260916/`. The complete measured trial is in
`data/outputs/stationary_memory/steady_20260916/bowl_1280_pad_01/`.
Generated outputs and room images stay local/private.

The existing local supervisor was copied with the two explicit observer options:

```bash
source scripts/rtabmap_odom_env.bash
python3 data/outputs/stationary_memory/steady_20260916/run_complete_crop.py fresh_run
```

Use a fresh run name. Source/model environments and the complete-message subset
must already exist. The supervisor refuses an active camera/SLAM process and owns
its bounded child lifecycle. Public observer/query commands are documented in
[online semantic memory](online-semantic-memory.md).

The evidence includes `acceptance.json`, `summary.json`, `cutoff_verification.json`,
`cutoff_math_verification.json`, `legacy_verification.json`, `cleanup.json`, exact
local check scripts and test logs. The trial has `verification.json`,
`geometry_verification.json`, `semantic_verification.json`,
`search_verification.json`, `reopen_check.json` and raw witnesses. Its journal SHA256
is `e2c793d624dc93524cd88f8761377da595acffdb45e29f2cb10125c268d65daa`.

To view the actual bowl query with its original scene and duplicate candidate:

```bash
xdg-open data/outputs/bowl_replay/steady_20260916/review.html
```

This page embeds source-checked PNGs and needs no WebGL or video decoder. It was
opened successfully on the Jetson desktop; no further operator review is claimed.

Follow-up: [shared-frame RGB-D evidence](coobserved-tracks.md) now supports an
optional query-time merge of these duplicate tracks. It removes eight duplicate
votes at each saved prefix while preserving the original trial and default mode.
