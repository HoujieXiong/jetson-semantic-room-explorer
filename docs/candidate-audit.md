# Why the stationary queries had the wrong candidates

Status: `VERIFIED` for a saved-data candidate audit and bounded GPU comparisons
on the Jetson. The original three operator-rejected results remain failures.
No live defaults or retrieval thresholds changed. Complete-crop encoding is now
an opt-in offline index mode; higher-resolution detection remains diagnostic.

Evidence is local/private in `data/outputs/candidate_audit/steady_20260916/`.
Inputs are the three frozen query prefixes from
`data/outputs/stationary_memory/steady_20260916/operator_review_20260916/`.
No camera, movement, model download or ROS publication was needed.

## Where the original candidates disappeared

| Original query | Processed frames | Accepted source poses | Eligible mapped frames | Encoded crops | Rankable objects |
| --- | ---: | ---: | ---: | ---: | ---: |
| `a fridge`, prefix 356 | 204 | 199 | 13 | 7 | 1 |
| `a trash can`, prefix 612 | 305 | 298 | 22 | 15 | 1 |
| `a bowl`, prefix 932 | 467 | 460 | 33 | 24 | 1 |

**Fridge:** every processed frame contains a refrigerator-labeled detection at
the central fridge. All 13/22/33 eligible frames reject that detection for
`insufficient_valid_depth`; none gets an image embedding under the current
depth-accepted-only policy. Valid fractions across the 33 eligible frames range
from 6.56% to 9.49%, below the unchanged 25% requirement. Original zero pixels
account for the invalid samples. RGB detection confidence is about 0.94 in the
three selected source frames; this does not compensate for missing geometry.

**Bowl:** no processed observation in any of these prefixes has a bowl label.
There are 1/1/25 sink-labeled proposals near the visible bowl. Each has an accepted
pose and depth, but none is the source of a received mapping keyframe in its
query prefix. Therefore none enters the current mapped-frame memory or semantic
candidate pool. This is a combination of proposal instability and keyframe
selection; it is not a semantic threshold rejection of an encoded bowl in the
original runs. Later bowl/sink records cannot repair an earlier query.

**Trash can:** the actual loaded YOLOv8n model has 80 labels and no trash-can
class. It can still produce a box with a wrong label, which MobileCLIP might rank,
but there is no dedicated trash-can proposal class. The refrigerator-labeled
region already rejected by the operator is the only surviving object in these
prefixes. It passes depth and gets misleading text scores. Neither its detector
label nor passing cosine score establishes a correctly bounded trash-can target.

The images are already registered 1280x720 RGB8 and uint16 millimeter depth.
Exact original pixel hashes and intrinsics agree; the code converts RGB to BGR
for the detector and retains RGB for MobileCLIP. This audit found no image-file
mix-up, RGB/BGR mismatch or millimeter/meter conversion error. It does not explain
the physical cause of the fridge's missing depth or certify registration quality
across all pixels.

## Same weights and thresholds, different detector input size

Three original RGB-D pairs were decoded from the complete-message subset, using
the exact source stamps for nodes 14, 9 and 21. Their RGB/depth bytes match the
frozen observations. The local YOLOv8n weights, 0.25 detection threshold, original
pixels, intrinsics and depth policy stay fixed; only `imgsz` is compared at
640 and 1280. Calls reuse `infer_rgbd` and `depth_observation` in an isolated
diagnostic process; the repository's `INFERENCE` default remains 640.

| Source node | 640 input | Additional 1280 proposal | Detection score | Inner-ROI depth |
| --- | --- | --- | ---: | --- |
| 14 | Central fridge and wrong region | Bowl, `[499,274,585,312]` | 0.515 | 100% valid; 1.437 m |
| 9 | Central fridge and wrong region | Sink, `[499,274,586,312]` | 0.407 | 100% valid; 1.437 m |
| 21 | Central fridge and wrong region | Bowl, `[499,274,586,312]` | 0.436 | 100% valid; 1.437 m |

These new crops visually cover the shallow bowl on the counter left of the
fridge. After viewing the new bowl and central-fridge crops on the Jetson
monitor, the operator replied **"they are correct"**. The acceptance is recorded
in `operator_positive_review.json`, tied to the displayed node-21 crops and page
hashes. It does not label each adjacent frame individually, accept the old wrong
region, or validate depth/geometry. The 1.437 m value is the sampled optical
depth, not a newly measured physical range.
The fridge remains depth-rejected and the wrong-region proposal remains present
at both resolutions. A higher resolution alone does not fix these queries.

After the first call for each size, the two remaining detection-call times are
53.427/47.073 ms at 640 and 90.863/100.870 ms at 1280. First calls are
3,951.282/322.513 ms respectively. These are three near-identical saved frames,
not throughput estimates or concurrent SLAM benchmarks. Peak process RSS is
1,284,536 KiB and peak CUDA allocation 69,837,312 bytes for this comparison.

## Image encoding also discards crop content

The installed official MobileCLIP-S0 transform is `Resize(256)` followed by
`CenterCrop(256,256)` and `ToTensor`. Its implementation was inspected directly
at `../ml-mobileclip/mobileclip/__init__.py`, with the pinned source/model already
documented in [semantic memory](semantic-memory.md).

For an 86–87 by 38 pixel bowl proposal, the square center crop retains only about
44% of its width. The original saved crop still contains the whole proposal;
the loss occurs later in the encoder transform. With the unchanged transform,
the new bowl-region proposals still score only 0.132–0.138 for `a bowl`.

One deterministic diagnostic variant centers the complete source crop on a
square RGB(0,0,0) canvas before the unchanged official transform. No interpolation
or invented RGB-D geometry is inserted into the original evidence. The padded
image vectors are stored separately and are never mixed into the old memory.
The original saved text vectors use the exact same model, tokenizer and encoder
identity; text preprocessing is unchanged.

| Source node | Detector label | Original crop encoding | Complete-crop square padding | Fixed 0.25 filter |
| --- | --- | ---: | ---: | --- |
| 14 | Bowl | 0.1384 | 0.2453 | No candidate |
| 9 | Sink | 0.1315 | 0.2531 | Candidate |
| 21 | Bowl | 0.1365 | 0.2592 | Candidate |

All scores are cosine similarities, not confidence probabilities. The combination
of higher-resolution proposals and complete-crop encoding supplies a bowl-region
candidate in two of these three diagnostic frames. Padding alone cannot create a
proposal absent at 640. These computations occurred after recording and do not
replace the original causal query results.

The result is close to the threshold and does not resolve the other failures.
The wrong-region crop still passes fridge/trash queries in the 1280/padded
comparison. RGB-only fridge candidates would still lack 3D support, and some
scores remain ambiguous with the wrong region. No depth, semantic, freshness,
start or clearance gate was relaxed. These results do not justify changing the
global detector/encoder defaults or claiming three successful queries.

## Verification, review and reproduction

`verification.json` checks all three source RGB-D pairs, all 15 detector crop
pixel arrays, actual valid-depth counts, metric back-projections and source-pose
transforms. Recomputed 640 detections exactly match the saved boxes/depth results;
all three existing geometric-support image vectors match their old stored vectors
with maximum absolute difference zero. Independently summed padded-vector dot
products agree within `3.93e-8`. All original query/journal/crop/review hashes are
unchanged. The native post-run check finds no remaining experiment, camera or
SLAM processes; available RAM is 4,810 MB. This is bounded cleanup evidence,
not a long-duration resource test.

Local evidence includes:

- `audit.json`: exact prefix-stage counts, exclusions and non-keyframe proposals.
- `selected_sources.json`, `node_*.npz`: original source observations and pixels.
- `resolution_comparison.json`: actual loaded classes and six detector calls.
- `crop_text_comparison.json`, `padding_comparison.json`: separate image vectors
  and measured scores for each variant, with the original text vectors.
- `audit_saved.py`, `extract_sources.py`, `compare_resolution.py`,
  `compare_crop_text.py`, `compare_padding.py`, `verify_audit.py`: exact local
  diagnostic code. The extraction uses the separate ROS environment; detector
  inference uses `.venv`, and encoding uses `../mobileclip-env`.

These are controlled diagnostic experiments, not a new supported replay runner.
To inspect the result without running models or the camera:

```bash
xdg-open data/outputs/candidate_audit/steady_20260916/review.html
```

The self-contained page shows the original scene with the new measured boxes,
enlarged source crops and the comparison tables. It needs no WebGL or video
decoder. After the operator could not see the new bowl proposal in chat,
`xdg-open` returned zero in the active Jetson desktop session. The operator then
confirmed the new displayed targets; the original page
is kept unchanged so its recorded hash remains verifiable. The refreshed
`verification.json` checks the separate positive feedback and crop/page hashes
without rewriting the frozen negatives.

## Optional complete-crop index and another recording

`scripts/semantic_memory.py build --square-pad` now centers the complete RGB crop
on a black square before the unchanged official transform. Odd extra padding goes
to the bottom/right. Saved evidence PNGs remain the original rectangular pixels.
The index encoder identity records `square_pad: true`; queries reconstruct that
mode and require the full identity to match. Legacy indexes omit the field and
retain their exact encoder identity and behavior. Text preprocessing, thresholds,
geometry and the live consumer are unchanged. No new dependency was added.

The acceptance checks were saved in `padding_acceptance.json` before native
verification. A different existing recording, `line_20260915`, was indexed through
the actual build CLI: 63 supports, 17 objects, all original crop pixels unchanged.
Fresh query CLIs ran all 11 previously frozen phrases on both old and padded
indexes. This recording was not used to choose padding, but its queries have
previously been inspected; this is a regression comparison, not a blind accuracy
benchmark.

| Phrase | Original top cosine / selected IDs | Padded top cosine / selected IDs |
| --- | --- | --- |
| a bottle | 0.245764 / none | 0.258314 / 17 |
| a refrigerator | 0.306087 / 1 | 0.309842 / 1 |
| a kitchen sink | 0.257108 / 9, 10 | 0.264784 / 9 |
| a drinking container | 0.221816 / none | 0.226088 / none |
| a fridge | 0.306761 / 1 | 0.314258 / 1 |
| a transparent plastic bottle | 0.208445 / none | 0.249786 / none |
| a white refrigerator | 0.282685 / 1 | 0.276968 / 1 |
| a red chair | 0.167334 / none | 0.146885 / none |
| a bicycle | 0.155955 / none | 0.183126 / none |
| an elephant | 0.170175 / none | 0.162205 / none |
| a backpack | 0.168191 / none | 0.179904 / none |

Refrigerator selections persist and all four negative-control phrases stay below
the filter. Bottle ID 17 now passes, but this new candidate has not been
operator-reviewed. The sink loses one selected ID and some scores decline; no
new labels establish whether those changes improve accuracy. The transparent
bottle remains below 0.25, despite rounding near the threshold. This supports
keeping padding optional, without promoting it as a global recognition fix.

Verification on this Jetson:

- 15 semantic math/persistence/review tests and 39 online memory/semantic/search
  tests pass. Pixel tests cover wide, tall, square, odd padding and invalid input.
- Default image vectors for three original supports remain byte-exact; all old
  11-query rankings and text vectors are exactly reproduced. The supported padded
  encoder reproduces the three diagnostic bowl vectors with zero maximum error.
- Real query calls explicitly refuse a non-boolean mode and an inconsistent
  encoder identity, leaving incomplete reports with no rankings.
- Independent scalar fusion agrees within `4.36e-8`; query scores agree within
  `3.31e-8`. All 63 original crop pixels/hashes and source inputs are unchanged.
- The existing `run_semantic_search.py` consumes the padded index successfully.
  `a fridge` selects ID 1; its goal is refused for insufficient map clearance and
  frontier fallback returns `INVALID_START` / `unknown_cell` for recorded node 1.
  No goal/path, ROS publication or motion is produced.
- Build time is 25.830 s including 10.228 s model load. The first encode takes
  478.962 ms; the remaining 62 have mean 41.521 ms, median 40.274 ms and P95
  52.721 ms. Peak RSS
  is 1,455,984 KiB and peak allocated CUDA memory is 237,129,216 bytes. These
  shared-memory accounting figures are not additive and are not a concurrent
  throughput benchmark.

Local evidence: `padding_line_index/`, `padding_line_queries/`,
`legacy_line_queries/`, `padding_search/`, `padding_native_check.json`,
`padding_verification.json`, `check_padding_native.py`, `verify_padding.py`,
and the focused test logs. `padding_cleanup.json` records no remaining
experiment/camera/SLAM processes and 4,982,160 KiB available RAM after verification.
This bounded snapshot is not a leak benchmark.
[Semantic-memory commands](semantic-memory.md) show how to use the opt-in mode.
No new capture was needed.

Follow-up: the [bounded bowl replay](bowl-replay.md) now verifies that these
explicit options can reach an actual online query and pass at the original source
cutoff. The result has small score margins and duplicate bowl/sink records;
fridge-depth and trash-proposal failures remain open.
