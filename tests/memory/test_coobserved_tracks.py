"""Real SQLite track consolidation, conflicting evidence and per-frame vote counts."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np

from test_scene_memory import detection, frame, report
from observe_rgbd_objects import depth_observation
from scene_memory import import_report, merge_coobserved_tracks, query_contents, shared_depth_region


def pair(node, *, box=(.1, .1, 20.1, 20.1), pixel=(10, 10), point=(0, 0, 2), labels=('bowl', 'sink')):
    a = detection(0, label=labels[0], confidence=.9)
    b = detection(1, label=labels[1], confidence=.8, box=box, point=point)
    b['depth']['pixel_uv'] = list(pixel)
    return frame(node, [a, b])


def sampled_pair(node, raw=None, boxes=((10., 10., 110., 90.), (11.2, 10., 111.2, 90.))):
    raw = np.full((100, 120), 2000, dtype=np.uint16) if raw is None else raw
    k = [100., 0., 60., 0., 100., 50., 0., 0., 1.]
    detections = []
    for index, box in enumerate(boxes):
        estimate = depth_observation(raw, k, box)
        row = detection(index, label=('bowl', 'sink')[index], confidence=.9-index*.1,
                        box=box, point=estimate['camera_point_m'])
        row['depth'] = estimate
        detections.append(row)
    result = frame(node, detections)
    result['camera_info'] = {'width': 120, 'height': 100, 'k': k}
    return result


class CoobservedTrackTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def evaluate(self, *frames):
        path = self.root/f'{len(list(self.root.iterdir()))}.db'
        import_report(path, report(*frames))
        with closing(sqlite3.connect(path)) as c, c:
            c.row_factory = sqlite3.Row
            original = c.execute('SELECT evidence_json FROM frames ORDER BY node_id').fetchall()
            review = merge_coobserved_tracks(c)
            result = query_contents(c)
            self.assertEqual(c.execute('SELECT evidence_json FROM frames ORDER BY node_id').fetchall(), original)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            decisions = [tuple(r) for r in c.execute('SELECT node_id,detection_index,object_id,decision,representative_index FROM associations ORDER BY node_id,detection_index')]
        return result, review, decisions

    def test_repeated_witnesses_keep_one_vote_and_original_detector_evidence(self):
        first, second = pair(1), pair(2)
        second['detections'][1]['detection_confidence'] = .95
        q, review, decisions = self.evaluate(first, second)
        self.assertEqual(q['counts']['objects'], 1)
        obj, = q['objects']
        self.assertEqual((obj['object_id'], obj['label'], obj['support_count']), (1, 'bowl', 2))
        self.assertEqual(obj['last_observation']['detection']['label'], 'sink')
        self.assertAlmostEqual(obj['mean_detection_confidence'], .925)
        self.assertEqual(decisions, [(1, 0, 1, 'new_object', None), (1, 1, 1, 'same_frame_overlap', 0),
                                     (2, 0, 1, 'same_frame_overlap', 1), (2, 1, 1, 'nearest_match', None)])
        self.assertEqual(review['merged'][0]['support_count_before'], 4)
        self.assertEqual(review['merged'][0]['support_count_after'], 2)
        self.assertEqual(review['merged'][0]['detector_labels'], ['bowl', 'sink'])

    def test_one_witness_does_not_gain_evidence_from_a_later_frame(self):
        q, review, _ = self.evaluate(pair(1))
        self.assertEqual(q['counts']['objects'], 2)
        self.assertEqual(review['unresolved'][0]['reason'], 'insufficient_shared_frames')
        later, _, _ = self.evaluate(pair(1), pair(2))
        self.assertEqual(later['counts']['objects'], 1)
        self.assertEqual(q['counts']['objects'], 2)

    def test_overlapping_container_and_separate_nearby_targets_are_not_duplicates(self):
        for kwargs in [{'box': (2, 2, 18, 18)}, {'box': (25, 0, 45, 20)},
                       {'pixel': (11, 10), 'point': (.02, 0, 2)}, {'point': (0, 0, 2.01)},
                       {'point': (.01, 0, 2)}]:
            with self.subTest(kwargs=kwargs):
                q, review, _ = self.evaluate(pair(1, **kwargs), pair(2, **kwargs))
                self.assertEqual(q['counts']['objects'], 2)
                self.assertFalse(review['merged'])
                self.assertEqual(review['unresolved'][0]['reason'], 'conflicting_shared_frame')

    def test_one_conflicting_shared_frame_blocks_other_agreeing_frames(self):
        q, review, _ = self.evaluate(pair(1), pair(2), pair(3, box=(25, 0, 45, 20)))
        self.assertEqual(q['counts']['objects'], 2)
        self.assertEqual(len(review['unresolved'][0]['witnesses']), 2)
        self.assertEqual(len(review['unresolved'][0]['conflicts']), 1)

    def test_missing_sample_evidence_and_singletons_do_not_merge(self):
        first, second = pair(1), pair(2)
        for f in [first, second]:
            del f['detections'][1]['depth']['pixel_uv']
        q, review, _ = self.evaluate(first, second)
        self.assertEqual(q['counts']['objects'], 2)
        self.assertFalse(review['merged'])
        q, review, _ = self.evaluate(frame())
        self.assertEqual(q['counts']['objects'], 1)
        self.assertEqual(review['merged'], [])

    def test_transitive_links_without_direct_pair_evidence_remain_unresolved(self):
        q, review, _ = self.evaluate(pair(1), pair(2), pair(3, labels=('sink', 'cup')),
                                     pair(4, labels=('sink', 'cup')))
        self.assertEqual(q['counts']['objects'], 3)
        self.assertFalse(review['merged'])
        self.assertEqual(review['unresolved'][-1]['reason'], 'incomplete_pairwise_evidence')

    def test_all_pairwise_witnesses_allow_a_group_but_still_one_vote_per_frame(self):
        frames = []
        for node in [1, 2]:
            f = pair(node)
            f['detections'].append(detection(2, label='cup', confidence=.7))
            f['accepted_observations'] = 3
            frames.append(f)
        q, review, _ = self.evaluate(*frames)
        self.assertEqual(q['counts']['objects'], 1)
        self.assertEqual(q['counts']['supporting_observations'], 2)
        self.assertEqual(len(review['merged'][0]['pair_witnesses']), 3)

    def test_merge_cannot_relax_the_running_geometry_gate(self):
        frames = [pair(1), pair(2)]
        frames += [frame(n, [detection(label='sink')]) for n in range(3, 11)]
        frames += [frame(11, [detection(label='bowl', point=(.3, 0, 2))]),
                   frame(12, [detection(label='bowl', point=(.44, 0, 2))])]
        q, review, _ = self.evaluate(*frames)
        self.assertEqual(q['counts']['objects'], 2)
        self.assertFalse(review['merged'])
        self.assertEqual(review['unresolved'][-1]['reason'], 'merged_distance_gate')

    def test_actual_shared_surface_allows_different_samples_and_one_frame_vote(self):
        first, second = sampled_pair(1), sampled_pair(2)
        a, b = first['detections']
        self.assertEqual([a['depth']['pixel_uv'], b['depth']['pixel_uv']], [[60, 50], [61, 50]])
        self.assertEqual(shared_depth_region(a, b, first)['shared_inlier_lower_bound'], 1920)
        q, review, decisions = self.evaluate(first, second)
        self.assertEqual(q['counts']['objects'], 1)
        self.assertEqual(q['counts']['supporting_observations'], 2)
        witness = review['merged'][0]['pair_witnesses'][0]['frames'][0]
        self.assertFalse(witness['same_depth_sample'])
        self.assertEqual(witness['shared_depth_region']['status'], 'SUPPORTED')
        self.assertEqual(witness['shared_depth_region']['shared_inlier_fraction_lower_bound'], .96)
        self.assertEqual(sum(d[3] == 'same_frame_overlap' for d in decisions), 2)

    def test_sparse_overlapping_rois_do_not_prove_shared_inlier_sets(self):
        raw = np.zeros((100, 120), dtype=np.uint16)
        raw[:, ::2] = 2000
        first, second = sampled_pair(1, raw), sampled_pair(2, raw)
        a, b = first['detections']
        self.assertNotEqual(a['depth']['pixel_uv'], b['depth']['pixel_uv'])
        evidence = shared_depth_region(a, b, first)
        self.assertEqual(evidence['shared_inlier_lower_bound'], 0)
        self.assertEqual(evidence['reason'], 'insufficient_guaranteed_shared_inliers')
        q, review, _ = self.evaluate(first, second)
        self.assertEqual(q['counts']['objects'], 2)
        self.assertFalse(review['merged'])

    def test_occluding_depth_layers_and_contained_boxes_do_not_add_region_witnesses(self):
        raw = np.full((100, 120), 1900, dtype=np.uint16)
        raw[:, 60:] = 2100
        first = sampled_pair(1, raw)
        a, b = first['detections']
        self.assertTrue(all(d['depth']['status'] == 'ACCEPTED' for d in [a, b]))
        self.assertEqual(shared_depth_region(a, b, first)['reason'], 'insufficient_guaranteed_shared_inliers')
        q, review, _ = self.evaluate(first, sampled_pair(2, raw))
        self.assertEqual(q['counts']['objects'], 2)
        self.assertFalse(review['merged'])
        raw[:, ::2], raw[:, 1::2] = 1900, 2100
        boxes = ((10., 10., 110., 90.), (12.2, 10., 112.2, 90.))
        first = sampled_pair(3, raw, boxes)
        self.assertEqual(shared_depth_region(*first['detections'], first)['reason'], 'ambiguous_depth_spread')
        q, review, _ = self.evaluate(first, sampled_pair(4, raw, boxes))
        self.assertEqual(q['counts']['objects'], 2)
        self.assertFalse(review['merged'])
        boxes = ((10., 10., 110., 90.), (30., 30., 90., 70.))
        q, review, _ = self.evaluate(sampled_pair(5, boxes=boxes), sampled_pair(6, boxes=boxes))
        self.assertEqual(q['counts']['objects'], 2)
        self.assertFalse(review['merged'])

    def test_region_witness_refuses_conflicting_depth_calibration_and_missing_evidence(self):
        for kind in ['depth', 'camera_point', 'map_point', 'outside', 'missing', 'intrinsics', 'rejected']:
            with self.subTest(kind=kind):
                f = sampled_pair(1)
                a, b = f['detections']
                if kind == 'depth':
                    b['depth']['depth_m'] += .001
                elif kind == 'camera_point':
                    b['depth']['camera_point_m'][0] += .01
                elif kind == 'map_point':
                    b['map_point_m'][0] += .01
                elif kind == 'outside':
                    b['depth']['pixel_uv'] = [35, 50]
                elif kind == 'missing':
                    del b['depth']['inlier_depth_p90_m']
                elif kind == 'intrinsics':
                    f['camera_info']['k'][0] = 200.
                else:
                    b['depth']['status'] = 'REJECTED'
                self.assertEqual(shared_depth_region(a, b, f)['status'], 'REJECTED')
        f = sampled_pair(1)
        f['detections'][1]['depth']['inlier_pixels'] = 2001
        with self.assertRaisesRegex(ValueError, 'pixel counts'):
            shared_depth_region(*f['detections'], f)

    def test_region_witness_still_needs_two_frames_and_rejects_any_later_conflict(self):
        q, review, _ = self.evaluate(sampled_pair(1))
        self.assertEqual(q['counts']['objects'], 2)
        self.assertFalse(review['merged'])
        third = sampled_pair(3)
        third['detections'][1]['depth']['depth_m'] += .001
        third['detections'][1]['depth']['camera_point_m'][2] += .001
        third['detections'][1]['map_point_m'][2] += .001
        q, review, _ = self.evaluate(sampled_pair(1), sampled_pair(2), third)
        self.assertEqual(q['counts']['objects'], 2)
        self.assertEqual(review['unresolved'][0]['reason'], 'conflicting_shared_frame')


if __name__ == '__main__':
    unittest.main()
