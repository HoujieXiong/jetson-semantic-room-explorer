# Query stability across recorded prefixes

Status: `VERIFIED` for measuring the existing journals on the Jetson Orin Nano.
The measurement finds unstable bowl selection and a later reversal of duplicate
merging. Stable recognition and persistent physical identity are not verified.
Runtime code, thresholds, model inputs and defaults are unchanged.

## Bounded method

The audit reopens three original journals: stationary `retained_01`, stationary
`bowl_1280_pad_01`, and moving `line_20260915/attempt_02`. It checks the empty
prefix, every graph event, every semantic outcome, original query checkpoints and
the final prefix. The complete-crop case also includes the previously audited
prefixes 871 and 932. Every copy contains an exact contiguous original prefix.
These journals commit one event per transaction; cuts do not split atomic batches.

The existing `query_online` snapshot and `rank_snapshot` functions produce both
original and optional merge-mode results. An audit hook ranks several stored text
vectors against the same snapshot and records representative membership without
changing the functions. Independent standalone API calls verify the batched
results at boundaries. No new image/text inference, camera access or ROS
publication occurs. Text vectors match each journal's declared encoder identity;
no future image evidence contributes to a prefix.

| Journal | Prefixes per mode | Snapshots, both modes | Text rankings |
| --- | ---: | ---: | ---: |
| Original stationary | 133 | 266 | 798 |
| Complete-crop stationary | 134 | 268 | 804 |
| Forward/backward motion | 125 | 250 | 1,000 |
| Total | 392 | 784 | 2,602 |

Stationary phrases are `a bowl`, `a fridge`, and `a trash can`. Motion phrases are
`a fridge`, `a refrigerator`, `a bottle`, and `an elephant`. The fixed filters
remain cosine >= 0.25 and within 0.02 of the highest score.

The stationary bowl-region proxy is IoU >= 0.5 with `[499,274,586,312]`. The
previously rejected region uses `[431,312,594,705]`. A record counts for a region
only when every current representative overlaps it; mixed records are reported
separately. No mixed bowl records occur here. These fixed-scene proxies are not
new operator annotations or moving-camera ground truth.

The time axis uses stored `available_elapsed_s`: producer-reported availability
before queueing and SQLite commit completion. It is not an exact durable-commit
timestamp. Source time is recorded separately relative to the first source
observation. These are retrospective results, not actual concurrent queries at
every plotted time. Sampling covers graph/semantic changes, not every event.
A further audit checks 183 event prefixes inside observed transition brackets,
including sampled endpoints, in both modes. It does not claim exhaustive coverage
outside those brackets.

## Bowl selection improves but still drops out

The original stationary journal first has bowl-region geometry at prefix 940 and
an embedding at 943, after the original unsuccessful query at 932. It has only
28 sampled prefixes with rankable bowl-region evidence; scores range from
0.148821 to 0.161973. None passes. Optional merging changes none of its 133
sampled results.

The complete-crop journal first has bowl-region geometry at prefix 61 and an
embedding at 65. The first bowl selection also occurs at 65. Across its 126
prefixes with rankable bowl-region evidence:

| Measurement | Original association | Optional merge |
| --- | ---: | ---: |
| Bowl-region selected samples | 105 / 126 | 113 / 126 |
| Minimum / maximum bowl-region cosine | 0.248069 / 0.253747 | 0.248943 / 0.253747 |
| Observed selection-loss prefix | 463 | 479 |
| Observed selection-recovery prefix | 644 | 581 |
| Recorded availability at loss, s | 106.237 | 113.083 |
| Recorded availability at recovery, s | 148.883 | 135.821 |

These counts reuse highly correlated observations and are **not recognition
accuracy percentages**. No selected bowl record is replaced by a wrong-region
candidate during the sampled dropouts; scores fall below the fixed threshold.
Boundary checks confirm each listed change at its semantic event. The two
previously successful query prefixes still pass, but they do not establish
stability over the recording.

## A one-pixel sample change reverses merging

The optional policy first merges tracks 2/3 at graph prefix 232, after the second
shared-frame witness. It remains merged at 80 sampled prefixes. At graph prefix
941, node 51 introduces a conflicting depth-sample identity and both records
return. The conflict persists through the final prefix 1200.

Node 51's source observation is event 936, mapping is 940, graph is 941 and
semantic result is 944. The association changes before its new embeddings arrive:

| Original detection | sink, index 2 | bowl, index 3 |
| --- | ---: | ---: |
| Sampled pixel | [549, 296] | [550, 296] |
| Depth, m | 1.439 | 1.439 |
| Inlier depth P10 / P90, m | 1.433 / 1.447 | 1.433 / 1.447 |

Box IoU is 0.980930; projected map points differ by 0.001917895 m. Source-checked
crops visually show the same bowl region, but the exact-pixel condition fails.
The system follows its declared conservative rule. This exposes sensitivity to
sample placement; it does not establish that ignoring all conflicting frames
would be safe. At the end both modes again retain 18 sink plus 37 bowl supports.
The two association transitions reassign existing supports, so object IDs cannot
be treated as persistent physical identities.

## Retained failures and motion regression

In the original stationary journal, fridge and trash queries select the rejected
region at all 125 rankable samples. In the complete-crop journal they do so at all
126 rankable samples, in both modes. Persistent wrong answers remain failures.

All 125 motion snapshots have identical rankings between modes and no qualifying
merge. Both fridge phrases pass in all 113 rankable snapshots. Bottle and elephant
queries never pass; their maximum top scores are 0.245764 and 0.189366. There are
12 snapshots with no semantic support, including startup and six early loss
episodes after an initial selection. Source exclusions show active-graph node
replacement and embeddings not yet committed. From semantic prefix 151 onward,
both fridge phrases remain selected at all remaining sampled prefixes. A query
with no eligible vectors does not establish that the fridge disappeared.

## Verification and limits

Independent source-event pose reconstruction, association, matrix connectivity,
representative selection and scalar fusion verify 120 boundary snapshots.
Maximum geometry disagreement is `8.89e-16` m and score disagreement `6.33e-8`.
Four hundred standalone API queries exactly reproduce the batched rankings;
original query checkpoints match their saved reports. Another 366 API calls
inspect every event inside state-change brackets and confirm the transitions.
All recorded inputs and runtime source hashes remain unchanged.

Every current planning attempt refuses: 400 stale-evidence decisions, 130
graph/grid stamp mismatches, four missing-graph decisions and 250 incompatible
grid-policy decisions. The latter belong to the older motion journal, which
predates occupancy integration. Graph/grid mismatches occur at separately
committed event boundaries. No goal is selected and no motion is requested.

The main audit takes 205.753 s with peak process RSS 196,192 KiB; independent
verification takes 55.366 s and event-boundary refinement 29.178 s. These are
audit execution times, not GPU inference or real-time pipeline benchmarks.
Cleanup finds no remaining audit/query/camera/SLAM processes and 5,275,872 KiB
available RAM. Runtime code did not change, so existing unit suites were not
rerun; verification here exercises the actual saved evidence and query APIs.

Private evidence is in `data/outputs/query_stability/20260916/`: the predeclared
`acceptance.json`, `measurement.json`, `summary.json`, `verification.json`,
`boundary_refinement.json`, `node51_evidence.json`, `timing_contract.json`,
`cleanup.json`, compressed snapshots, exact local audit scripts and logs.
`review.html` embeds the original crops and `stability.png`; `stability.svg` is
also available for export. Room data and generated artifacts remain uncommitted.

For local reproduction with the unchanged declared inputs and runtime, copy
`acceptance.json` and the five audit `.py` files to a fresh sibling directory.
Run `measure.py`, `analyze.py`, `verify.py`, `refine_boundaries.py`, then `plot.py`
with `.venv/bin/python` and `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2`. Measurement
has a 1,200 s bound, a 1 GiB available-RAM guard and a 2 GiB free-disk guard.

Next: validate shared-depth-region evidence for near-identical proposals, then
make the smallest justified optional association change that tolerates sampling
jitter while preserving distinct-object refusals and the fixed query gates.
