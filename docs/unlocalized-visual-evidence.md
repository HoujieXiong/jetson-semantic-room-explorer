# Text retrieval of unlocalized RGB evidence

Status: `VERIFIED` on Jetson Orin Nano for two bounded historical-source GPU
experiments. Depth-rejected source crops can now appear in a separate text-query
ranking. They have **no accepted 3D location or navigation target**. A subsequent
[concurrent playback comparison](concurrent-unlocalized-retrieval.md) also passes
at 0.25x; live-camera throughput remains unverified.

## Minimal optional path

The existing producer accepts `--semantic-include-unlocalized`, requiring
`--semantic-model`. Its declared journal policy lets the same worker encode
depth-rejected proposals after depth-accepted proposals. The existing limits
remain 32 cached RGB frames, eight pending requests, one worker, five seconds
for source availability and 16 crops per keyframe. Accepted proposals retain
priority; omissions and worker failures remain explicit. Defaults are unchanged.

The source observation still needs an accepted original pose and a mapped
keyframe. Each extra sample retains the source timestamp, node/detection indices,
original lossless crop and hashes, encoding times, `UNLOCALIZED` status and
original depth-rejection reason. Journal validation refuses invented object IDs
or geometry on these samples. No depth filling or threshold change is involved.

Text queries return an additional `semantic.unlocalized` section. It ranks
individual source views in the current graph, using only vectors committed in
the query's prefix. The `observation_id` is a session-scoped `node:index` source
key, not a persistent physical object identity. Results include observation,
mapping and semantic event numbers and encoding completion time. Views are not
fused or counted as distinct objects. Missing embeddings retain their reasons.

The exact text, encoder identity and cosine >=0.25 / top-score-window 0.02 filter
are unchanged. Localized and unlocalized rankings apply that filter separately;
they do not compete for one winning object. Existing encoder identity includes
the original geometric sampling/fusion description; the journal's explicit
extended capture policy declares the separate per-view path. The numerical
encoder, preprocessing and geometric fusion are unchanged.

The existing HTML review labels visual matches **3D location unavailable** and
shows source keys and depth refusals. Diagnostic images remain separate from
selected matches. A visual-only result has `UNLOCALIZED_CANDIDATES_SELECTED`
status. The planner refuses selected visual evidence; it cannot provide an
object goal or trigger frontier planning on its own. When localized candidates
also exist, their original planning checks and decisions remain in effect.
This does not validate the identity of those localized candidates.

## Experiment and provenance

The predeclared trial uses every mapped source with a processed observation and
accepted original pose in two existing journals: 44 stationary and 59 motion
keyframes. Exact original RGB timestamps were decoded from their bags; all 103
1280x720 RGB arrays match the stored pixel hashes. No new camera capture,
detection, pose estimation, model download or operator labeling occurred.

Each fresh experimental journal imports the original **nonsemantic** events
without changing their payloads or availability times. It has a new session ID,
records the original session/hash and retains the original monotonic origin.
The real GPU worker appends new vectors at actual current encoding availability.
Original journals and old query prefixes are never backfilled. Final graph
eligibility still limits retrieval: all 44 stationary frames and 20 motion frames
are eligible in the final snapshots. This is historical source import plus new
encoding, not a concurrent replay or evidence of earlier live-query success.

Stationary encoding retains complete-crop square padding; motion retains its
original center-crop preprocessing. The real official MobileCLIP-S0 checkpoint
and source/package identity exactly match each original journal. Source selection
and phrases were fixed before inference, independent of text scores.

## Measured results

| Measurement | Stationary | Motion |
| --- | ---: | ---: |
| Encoded keyframes | 44 | 59 |
| Original accepted-depth crops | 94 | 226 |
| Additional unlocalized crops | 62 | 65 |
| Unlocalized views in final graph | 62 | 26 |
| Additional encoding time, summed | 2.438 s | 2.487 s |
| Additional crop encoding median / P95 | 37.205 / 53.036 ms | 37.104 / 47.971 ms |
| Additional PNG storage | 1,532,379 bytes | 2,606,946 bytes |
| Whole experiment, including queries/import/load | 44.368 s | 52.637 s |
| Model load | 13.250 s | 10.214 s |
| Peak process RSS | 1,629,260 KiB | 1,673,360 KiB |
| Peak CUDA allocated / reserved | 246,697,472 / 270,532,608 bytes | Same |

Both runs finish with the worker and writer closed, no encoding refusal or
crop-budget omission, cache peak 32 and pending peak one. These sequential
worker trials measure functional cost, not sustained concurrency or leak rates.
Peak RSS includes the experiment's imported events, queries and image cache;
it is not a measured memory increase relative to a matched concurrent control.
Final query API calls take 361–669 ms stationary and 326–672 ms motion.

| Exact phrase | Stationary unlocalized result | Motion unlocalized result |
| --- | --- | --- |
| `a fridge` | 44 selected views; top `58:0`, 0.288479 | One selected view `49:0`, 0.289817 |
| `a refrigerator` | Not part of this trial | Same view `49:0`, 0.290435 |
| `a bowl` | None; highest 0.166000 | None; highest 0.198643 |
| `a trash can` | None; highest 0.194167 | None; highest 0.216674 |
| `an elephant` | None; highest 0.162622 | None; highest 0.204221 |
| `a bottle` | None; highest 0.202045 | None; highest 0.219612 |

The stationary fridge selections overlap the operator-confirmed box by
0.9041–1.0 IoU in the stationary image coordinates. Inspected top crops show the
fridge door. They are 44 correlated observations, not 44 objects or independently
confirmed labels. The exact previously confirmed node-21 source was dropped by
`pending_queue_full` in the complete-crop source journal. It remains ineligible;
the experiment retrieves the corresponding region in other recorded frames,
not that exact confirmed image. No exception forces it into the ranking.

The old localized fridge/trash candidate is unchanged and remains an operator-
rejected region. It still passes the original localized ranking even when the
new visual ranking displays the fridge. Bowl's original localized results also
remain unchanged; optional duplicate merging still produces its existing
four-record / 83-support snapshot. Unknown/bottle refusal remains explicit.
This milestone restores inspectable image evidence; it does not solve incorrect
localized identity, unreliable recognition or the stationary fridge's depth.

## Verification and use

All 447 PNG crops match the extracted source pixels. All 320 original vectors,
crop bounds and hashes are bit-identical after re-encoding. Imported nonsemantic
events, geometry, default and optional merged localized rankings are unchanged.
Independent scalar cosine/threshold calculations match every checked visual
ranking, with maximum score error 4.79e-8. Four saved encoding checkpoints per
recording reproduce exactly after reopening: 44 text queries, with no future
embeddings in the initial prefix. All 31 declared original inputs retain hashes.
Pre-change and current implementations also reproduce 29 original-journal
queries exactly, including seven actual historical query prefixes.

The 47 online-memory/semantic/search, 57 memory and 44 odometry/concurrency tests
pass (148 total). New cases cover visual-only CLI status, source pixels/time,
two separate views, graph withdrawal, defaults, forbidden geometry, altered
depth reasons, crop-budget priority, worker accounting and refusal to plan from
visual evidence. An initial test fixture compared nondeterministic route timing;
the retained failure was corrected to compare route decisions and geometry.

A fresh real GPU search CLI exactly reproduces the new stationary text vector
and ranking. It takes 14.509 s overall, including 11.442 s model load; the snapshot
query takes 491.819 ms. Peak RSS is 1,373,716 KiB and peak allocated CUDA memory
228,483,584 bytes. The old map is stale, so planning refuses; it also records the
explicit refusal for selected unlocalized views. Motion queries retain the older
incompatible-grid refusal. Fresh-grid unit cases separately verify the specific
visual-only refusal without masking it behind map age. No ROS publication or
motion is performed.

Open the measured review without WebGL or a video codec:

```bash
xdg-open data/outputs/unlocalized/20260916/gpu_cli/query/queries.html
```

Run another query with a fresh output directory:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../mobileclip-env/bin/python \
  scripts/online_semantic_memory.py \
  --db data/outputs/unlocalized/20260916/stationary/online.db \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --text 'a fridge' --output data/outputs/unlocalized/manual_fridge
```

For a future producer trial, add `--semantic-include-unlocalized` to the existing
[recorded-data observer command](online-semantic-memory.md). Old journals keep
their policy and do not acquire extra crops from a query flag.

Private evidence: `data/outputs/unlocalized/20260916/`, including `acceptance.json`,
original source/implementation hashes, `prepare.py`, `trial.py`, `verify.py`,
`regression.py`, per-recording source manifests/arrays/journals/checkpoints,
`verification.json`, `original_regression.json`, `cli_verification.json`,
`gpu_cli/` and test logs. Original room images, crops, journals and generated
reports remain untracked.

The subsequent [concurrent trial](concurrent-unlocalized-retrieval.md) measures
the same path with SLAM, detection and queries running together, retaining source,
timing and planning gates. Its remaining query-startup cost motivates the next step.
