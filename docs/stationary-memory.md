# Stationary graph retention and semantic memory

Status: `VERIFIED` for a controlled saved-data comparison on Jetson Orin Nano.
Keeping stationary source nodes restores eligible observations and text queries
under the current graph. Retrieval accuracy, useful live search, continuous
operation and physical navigation remain unverified.

The operator was asleep. Both trials used existing recordings at **0.25x** with
the camera closed. No new data, dependencies or motor commands were used.

## Cause and smallest change

The preceding live trial reported 53 rehearsal merges in 54 mapping updates,
retaining only node 1. Its first observation was rejected for missing source-time
map TF. Later valid observations belonged to nodes absent from the current graph,
so memory correctly excluded them. The current mapped camera node was also absent;
the query therefore had no eligible objects and could not establish a start.

The online overlay `config/rtabmap_online_preview.yaml` now adds:

```yaml
Mem/RehearsalSimilarity: "1.0"
RGBD/LinearUpdate: "0"
RGBD/AngularUpdate: "0"
```

RTAB-Map 0.23.7 calls rehearsal only when its similarity threshold is below 1;
the update parameters specify zero for both thresholds to retain stationary map
updates. See the official [Memory.cpp implementation](https://github.com/introlab/rtabmap/blob/0.23.7/corelib/src/Memory.cpp#L1064)
and [parameter definitions](https://github.com/introlab/rtabmap/blob/0.23.7/corelib/include/rtabmap/core/Parameters.h#L372).
Actual native parameter dumps and the comparison below verify this configuration
on the installed system. The earlier `latch: false` stays in place.

This preserves original source-node association without changing source-time TF,
committed-prefix visibility or graph membership rules. Missing poses remain
rejected. There is no latest-pose substitution or retrospective validation.
The overlay is for bounded online trials: the memory consumer rejects graphs
over 600 nodes; these parameters do not cap RTAB-Map's own graph growth. Continuous
operation requires a measured retention policy before this becomes a deployment
configuration.

## Preserved input and reproduction

Evidence root, local and ignored:
`data/outputs/stationary_memory/steady_20260916/`.

The original live bag has 947 RGB/depth pairs but three missing CameraInfo
messages. Its strict failed report remains unchanged. `prepare_subset.py` copied
the original database, retaining only 944 complete four-topic groups and static
TF: 3,777 messages. It excluded the nine existing messages from three incomplete
groups; it synthesized nothing. Original message IDs, receipt/header stamps,
compressed bytes, decoded message hashes and input/output file hashes are saved
in `subset_provenance.json`. The new `reference.json` passes the strict checker.
The bag's retained receipt interval is 64.800 seconds.

`baseline_01` uses the old overlay (`latch: false` only); `retained_01` adds the
three parameters above. Both use the same 944-pair subset, odometry/mapping
settings, YOLOv8n, MobileCLIP-S0, source code and 0.25x typed playback. Subscriber
discovery and final acknowledgements are bounded. Models start before playback;
queries run while playback is active with independent ROS receivers. These are
sequential functional trials, not repeated performance estimates.

Each directory retains exact commands, source/config snapshots, native parameter
dumps, raw graph/grid witnesses, resource telemetry and owned-process cleanup.
For a fresh trial on this Jetson, from the repository root in a fresh shell:

```bash
source scripts/rtabmap_odom_env.bash
python3 data/outputs/stationary_memory/steady_20260916/run_trial.py retained_02
```

This local supervisor requires the saved subset, installed environments and
models. It refuses an existing output directory or active camera/SLAM processes.
`baseline_01/rtabmap_online_preview.yaml` preserves the baseline; the current
configuration runs the retained-node variant. The saved `used_run_trial.py` and
`run.json` are the exact trial record, not a portable installation package.

## Measured comparison

| Measurement | Baseline | Retain stationary nodes |
| --- | ---: | ---: |
| Sensor-contract input pairs | 944 | 944 |
| Perception synchronized pairs | 944 | 943 |
| Perception processed / explicitly dropped | 622 / 322 | 621 / 322 |
| Accepted / refused source poses | 617 / 5 | 613 / 8 |
| Matched tracked odometry / reported lost | 943 / 0 | 943 / 0 |
| Mapping updates / rehearsal merges | 64 / 63 | 64 / 0 |
| Final active graph nodes | 1 | 64 |
| Encoded keyframes / actual crops | 45 / 35 | 44 / 33 |
| Final eligible frames / supporting observations | 0 / 0 | 44 / 33 |
| Final provisional object records | 0 | 3 |
| Committed events | 1,200 | 1,199 |
| Journal bytes | 5,804,032 | 6,533,120 |
| RTAB-Map database bytes | 44,781,568 | 44,507,136 |
| Writer queue peak, capacity 16 | 4 | 5 |
| Transaction P50 / P95 / max, ms | 8.681 / 21.519 / 162.350 | 9.492 / 35.384 / 496.941 |
| Peak system RAM, MB | 5,124 | 4,938 |
| Peak GPU temperature, C | 60.906 | 61.031 |
| Total supervisor duration, seconds | 398.469 | 400.947 |

Both observers received 944 messages on each of the four image/CameraInfo topics.
The changed run left one complete group unmatched by the perception synchronizer:
RGB stamp `1789529904445272000`, depth stamp `1789529904441584000` ns. It is not a
transport loss or an inference queue drop. Its semantic rejection is explicitly
`source_not_received` because no synchronized observation reached that stage.
Each run also has one sensor input without an odometry result. The changed run's
eight pose refusals are two missing odometry and six missing map TF; the baseline
has one and four respectively. Neither has failed or pending inference at close.

The changed run ends with 77 detections in 44 eligible frames: 44 fail depth and
33 support three provisional records. The records include overlapping bowl and
sink labels, so three records do not establish three distinct correct objects.
Both RTAB-Map databases store 64 nodes because unlinked nodes are kept; database
size does not measure current-graph membership. Journal size grows with retained
graph poses. Swap was already in use and rose during each trial (baseline
1,201–1,369 MB; changed 1,252–1,639 MB). The single-run RAM difference is not an
optimization claim. No long-duration resource-stability claim is made.

## Queries and visual review

All baseline queries have zero semantic support and publish only
`current_start_node_missing_from_graph`. With retained nodes:

| Actual query | Eligible frames / supports | Top cosine | Semantic result | Route result | CLI seconds |
| --- | ---: | ---: | --- | --- | ---: |
| `a fridge` | 13 / 7 | 0.272788 | Selects the apparent trash-bin/cabinet crop | NO_ROUTE | 30.240 |
| `a trash can` | 22 / 15 | 0.280325 | Selects the apparent trash-bin/cabinet crop | NO_ROUTE | 19.949 |
| `a bowl` | 33 / 24 | 0.157531 | No candidate above 0.25 | INVALID_START | 17.533 |

The first two queries select the same provisional object, whose detector label
is `refrigerator`. The fridge query is a visual false selection. The trash query
appears relevant but its crop includes substantial cabinet background; operator
identity review is pending. The bowl is visible in the full frame, but had no
eligible matching candidate at query time. A later bowl record does not validate
the earlier query.

The actual central fridge is detected in the example source frame at confidence
0.942. Its depth ROI has only 838/11,076 valid pixels (7.57%); the remaining pixels
are invalid zeros. All 621 processed frames retain an explicit refrigerator
`insufficient_valid_depth` rejection. The reason for those sensor holes is not
established here. A correct RGB label does not supply a valid 3D point.

Every actual start is the recorded camera projection, not a simulated free cell.
Its grid cell is unknown. Although the trash query finds an internal stand-off
candidate (1.004 m from the representative, conservative clearance 0.315 m), it
cannot produce a route from that start. All three independent receivers get
exactly one decision, zero goals and zero paths. Evidence ages are 2.440, 2.314
and 1.978 seconds, below the unchanged 10-second limit. The unchanged 0.25 m
clearance and route gates remain enforced. Reopening later correctly refuses
stale map evidence while retaining the semantic snapshot.

Open the self-contained review on the Jetson display when ready:

```bash
xdg-open data/outputs/stationary_memory/steady_20260916/retained_01/review.html
```

It embeds original RGB images, exact source crops, measured scores and occupancy
preview; no WebGL, video decoder, server or external assets are required. Original
source and crop pixels/hashes are checked by `build_review.py`; desktop browser
rendering and operator labels are not yet verified. Images remain local/private.

## Verification and next action

For each run, `verification.json`, `geometry_verification.json`,
`semantic_verification.json`, `search_verification.json` and `reopen_check.json`
are `VERIFIED`. Independent checks decode original pixels/depth units, reconstruct
TF using only received events before each decision, recompute geometry/vector
fusion and ranking, and compare every one of 64 graph/grid events with an
independent receiver. Goal candidates and unknown starts are checked against raw
occupancy even when the route is refused. Reopening preserves current and prior
journal results and bytes. `comparison.json` confirms the original live bag and
metadata are unchanged. All owned processes exited without forced termination
or leftovers; the camera was never opened. No Python runtime code changed in
this step; this configuration is verified by actual native A/B runs and parameter
dumps rather than a test that repeats YAML values.

Changed journal SHA-256:
`d528f06677b9f5637503c0d926e4810293a41103bca829907ad074a6b62e51d2`.
The prior semantic journal remains
`23991ad903fb09ee9567035bba2e4e0ef74eae976673c5f6295909c214a294ec`.

Next: have the operator review the three queries and original crops, then record
confirmed target labels before selecting a retrieval-quality change. No new
recording is needed for that review.
