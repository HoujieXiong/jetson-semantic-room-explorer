# Coordinate perception with source-frame odometry

Status: `VERIFIED` for one matched nominal-1x saved-data replay per policy on the
Jetson Orin Nano, 2026-09-16. Camera capture and navigation stayed off.

The new optional `--perception-selection odometry` mode increases usable source
coverage in this trial: accepted poses rise from 104 to 223, and encoded map
keyframes from 21 to 50. Recognition errors and incomplete synchronization remain.

## Why this change

The previous [live measurement](live-warm-queries.md) processed 287 frames, but
209 never received their own odometry result. Longer pose waits cannot recover
those missing results. Conversely, 157 odometry sources were dropped by
perception. The old 979-input counter counted CameraInfo pairs; only 975 image
pairs arrived, of which 740 lacked odometry. Original reports remain unchanged.

`tests/check_concurrent_perception.py` now optionally retains up to 16 original
RGB-D pairs, for at most two seconds from their arrival, awaiting an exact-stamp,
tracked OdomInfo message. A selected pair enters the existing one-pending,
one-worker queue. Cache eviction, timeout, tracking loss and inference queue
overflow have explicit outcomes. Source-time map TF is still required afterward.
No nearby pose, reconstructed color, final map pose or invented metadata is used.
The default `all` policy remains available for comparison.

The capacity follows the original live receipt trace: source odometry TF arrived
after at most 14 newer image pairs, P95 nine. This TF trace is a sizing proxy,
not a measurement of OdomInfo arrival. Sixteen pairs bound additional image payload
to 73,728,000 bytes (70.3 MiB), excluding existing queues and metadata. The smaller
alternative of consuming RTAB-Map's processed RGB-D message was probed: its RGB
was `mono8`, inner stamps had an 86 ns float-roundtrip difference on the inspected
frame, and depth CameraInfo was empty. It could not preserve original color input.

Reports now distinguish actual image pairs, four-topic synchronized groups and
image/odometry overlap. The older metadata-derived counter names remain, with an
explicit CameraInfo basis. Queue wait starts after selection; selection wait and
arrival-to-result timing preserve the additional waiting cost.

## Fixed experiment and measured result

The original live bag is strictly `INCOMPLETE`. An explicit copy retains 973
complete four-topic groups from its 975 image pairs, excluding two groups with
missing metadata and metadata outside retained groups. Pixels, stamps, calibration
and retained compressed messages are unchanged; nothing is synthesized. Independent
disk readback passes counts, content hashes and synchronization. The original
bag, original memory and operator A/B labels stay immutable.

Baseline runs first, candidate second, with the same subset at nominal 1x,
most-recent-frame odometry, retained map nodes, YOLO1280, square-padded MobileCLIP
crops, unlocalized evidence, fixed queries and thread settings. Only perception
selection differs. Both use the existing replay writer (16 queued events, one FULL
transaction per event); no concurrent camera/recorder load. This differs from the
previous live run, which is diagnostic evidence rather than a matched control.

| Measurement | Baseline `all` | Candidate `odometry` |
| --- | ---: | ---: |
| Actual received image pairs | 973 | 973 |
| Four-topic synchronized groups | 948 | 944 |
| Images not reaching a synchronized group | 25 | 29 |
| Processed / explicitly dropped groups | 292 / 656 | 225 / 719 |
| Tracked odometry / reported lost outputs | 250 / 0 | 244 / 0 |
| Processed sources with their own odometry | 108 | 225 |
| Accepted source-time map poses | 104 | 223 |
| Missing source odometry / map TF refusals | 184 / 4 | 0 / 2 |
| Encoded keyframes / all map nodes | 21 / 57 | 50 / 55 |
| Localized / unlocalized encoded crops | 22 / 47 | 64 / 109 |
| Final provisional objects / geometric supports | 2 / 22 | 3 / 64 |
| Arrival-to-result median / P95, ms | 2242.069 / 2411.682 | 383.400 / 688.680 |
| Detection-plus-depth median / P95, ms | 133.776 / 218.833 | 150.607 / 278.884 |
| Peak system RAM, MB | 5213 | 5222 |

The candidate makes 237 exact-source selections: 225 processed and 12 dropped
by the existing pending queue. Other drops are 663 cache evictions and 44 timeouts.
Independent cache peak is 16; processed-frame selection wait median/P95 is
196.765/249.403 ms. Pending/inference/pose-wait peaks are 1/1/8 versus 1/1/6.
Writer peaks are 8/6; semantic pending peaks are 2/2, with the existing 32-frame
RGB cache. No inference failure or unfinished job occurs.

Semantic refusals change from 33 dropped-source, two pose and one absent-source
keyframe to two dropped-source, one pose and two absent-source keyframes. All
received images match the source reference; missing synchronized groups remain
separately reported, without being relabeled as inference drops or successes.

Publisher scheduling lag median/P95/max is 5.795/35.137/126.366 ms versus
6.782/56.491/190.881 ms. Playback including final acknowledgements takes
68.241/66.025 s; maximum final acknowledgement wait is 2.954/0.737 s. The RGB source
interval is 65.165 s. Nominal 1x does not imply identical wall-time delivery.

Available RAM stays above 2,292,096/2,220,536 KiB. Observer CUDA allocated peaks
are both 330,952,704 bytes; reserved peaks are 354,418,688/356,515,840. Query CUDA
allocated/reserved peaks are 228,483,584/243,269,632 for both. GPU temperature
peaks at 55.093 C. Existing swap ranges 1668–1927/1793–2217 MB. All owned processes
close without forced termination; final native inspection finds no runtime process
and 5,401,524 KiB available RAM, with power still 25 W. This is not a long-run leak
test or a repeatable memory-delta measurement.

## Queries and identity failure

Four actual requests run at 18/30/42/54 seconds after player-process launch.
Full responses for fridge/bowl/sink/elephant take 3.771/0.717/1.053/0.827 s versus
3.946/0.813/1.206/0.881 s, after separate 12.744/15.860 s launch-to-READY times.
Each reads a fresh committed prefix before playback ends. At the first query,
usable frames increase from five to twelve; final usable frames from 21 to 50.

The localized fridge candidate is still wrong: both first queries select the
same bin/cabinet crop, with aggregate scores 0.275998/0.274308. Separate visual
retrieval finds the fridge at 0.298617/0.301901, but it retains
`insufficient_valid_depth` and supplies no 3D target. These new views were inspected
by the assistant; original exact A/B operator labels are preserved separately.
Bowl, sink and elephant remain unselected. Fridge routes refuse the unknown start;
other requests refuse the frontier start. Closed queries refuse stale maps.
No target or path is selected, published or executed.

Eight actual queries and eight closed queries pass source, geometry, scalar
ranking and graph/grid witness checks. Sixteen copied-prefix/closed reopening
comparisons preserve answers exactly. All 242 encoded crops match original pixels;
100 commonly processed sources have identical detection/depth results, and all
26 commonly encoded source crops/vectors are identical. Maximum geometry error
is 4.45e-16 m, 3D-score error 3.75e-8 and visual-score error 6.17e-8, within
1e-12 m / 1e-6 declared numerical tolerances. These are not physical accuracy or
identity measurements.

## Verification and evidence

Focused commands used from the repository root:

```bash
source scripts/rtabmap_odom_env.bash
.venv/bin/python -m unittest discover -s tests/odometry
.venv/bin/python -m unittest discover -s tests/online_memory
```

Results: 51 odometry/concurrency tests and 52 online-memory tests pass. After the
final cache-timing instrumentation, all six selection tests pass again. A first
repeat command accidentally replaced ROS PYTHONPATH and failed before tests ran;
the corrected invocation and both logs are retained.

Private evidence is under `data/outputs/coordinated_frames/20260916/`: predeclared
`acceptance.json`, original overlap/receipt diagnostics, native processed-message
probe, explicit subset/readback, archived runtime sources, both trials, independent
checkers, exact source outcomes, `comparison.json`, tests and `cleanup.json`.
An initial subset preparation API assumption was corrected before copying data;
its failure log remains. The admission checker's initial all-groups assumption was
also corrected to retain the observed synchronization gaps, with its original
source and accounting note saved. Neither correction changes runtime results.

The exact trial commands used, with fixed thread settings, are recorded in
`run_trial.py`, `run.json` and `acceptance.json`. Existing result directories are
exclusive; do not overwrite them when repeating the experiment. The plain browser
review has 16 query sections and 101 verified embedded PNGs, requiring no WebGL:

```bash
xdg-open data/outputs/coordinated_frames/20260916/review.html
```

Learning: shared source selection yields more usable memory even with fewer
detections. It does not establish identity, remove depth holes, or authorize a
route. One trial per policy does not establish sustained live throughput.

Next action: use the saved operator-confirmed A/B evidence to validate an explicit
identity-refusal path before an incorrect localized candidate can become a target.
