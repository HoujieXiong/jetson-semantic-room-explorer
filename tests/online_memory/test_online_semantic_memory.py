"""Causal crop evidence, revision-scoped fusion, bounded queues and real SQLite."""

from contextlib import closing
import copy
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from online_scene_memory import OnlineMemoryWriter, query_online
from online_semantic_memory import OnlineSemanticCapture, POLICY, encode_keyframe, query_text
from test_online_scene_memory import STAMP, context, graph, observation


IDENTITY = {'test_encoder': 'known_unit_axes'}


def axis(index):
    value = np.zeros(512, dtype=np.float32)
    value[index] = 1
    return value


class KnownEncoder:
    def __init__(self, vector=None):
        self.vector = axis(0) if vector is None else vector
        self.seen = []

    def encode(self, crop, image=False):
        self.seen.append(crop.copy())
        return self.vector, 1.


class OnlineSemanticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root/'online.db'
        self.writer = OnlineMemoryWriter(self.db, {**context(), 'semantic_encoder': IDENTITY, 'semantic_policy': POLICY})
        self.addCleanup(self.close)
        self.clock, self.seq = 10., 0
        self.rgb = np.arange(4*5*3, dtype=np.uint8).reshape(4, 5, 3)
        self.crops = self.root/'online.crops'
        self.rows = []

    def close(self):
        try:
            self.writer.close()
        except RuntimeError:
            if self.writer.thread.is_alive():
                raise

    def flush(self):
        deadline = time.monotonic()+3
        while self.writer.stats['events_committed'] < self.seq:
            self.writer.check()
            if time.monotonic() > deadline:
                self.fail('Writer did not commit')
            time.sleep(.005)

    def send(self, kind, payload):
        self.clock += 1
        self.writer.submit(kind, payload, self.clock)
        self.seq += 1
        self.flush()

    def source(self, node=1, pose='ACCEPTED'):
        stamp = STAMP+(node-1)*10**9
        row = observation(stamp, pose)
        row['rgb_pixels_sha256'] = hashlib.sha256(self.rgb.tobytes()).hexdigest()
        row['camera_info'] = {'width': 5, 'height': 4}
        row['detections'][0]['box_xyxy'] = [1.2, .2, 4.5, 3.5]
        self.send('mapping', {'node_id': node, 'stamp_ns': stamp})
        self.send('observation', row)
        self.rows.append(row)
        return row

    def encoded(self, row, node=1, vector=None):
        self.crops.mkdir(exist_ok=True)
        self.clock += .1
        result = encode_keyframe(KnownEncoder(vector), row, self.rgb, node, self.crops, lambda: self.clock)
        result['requested_elapsed_s'] = self.clock
        return result

    def query(self, vector=None):
        return query_online(self.db, text_vector=axis(0) if vector is None else vector, encoder_identity=IDENTITY)

    def test_coobserved_merging_uses_only_prefix_witnesses_and_one_vector_per_frame(self):
        earlier = None
        for node in (1, 2):
            stamp = STAMP+(node-1)*10**9
            row = observation(stamp)
            row.update(camera_info={'width': 5, 'height': 4},
                       rgb_pixels_sha256=hashlib.sha256(self.rgb.tobytes()).hexdigest())
            first = row['detections'][0]
            first.update(label='bowl', box_xyxy=[0., 0., 5., 4.])
            first['depth']['pixel_uv'] = [2, 2]
            second = copy.deepcopy(first)
            second.update(detection_index=1, label='sink', detection_confidence=.8)
            row['detections'].append(second)
            self.send('mapping', {'node_id': node, 'stamp_ns': stamp})
            self.send('observation', row)
            encoded = self.encoded(row, node)
            encoded['samples'][1]['vector'] = axis(1).tolist()
            self.send('semantic', encoded)
            self.send('graph', graph({n: [1., 0., 0.] for n in range(1, node+1)}, stamp))
            merged = query_online(self.db, text_vector=axis(1), encoder_identity=IDENTITY,
                                  merge_duplicates=True)
            if node == 1:
                earlier = merged
                self.assertEqual(earlier['counts']['objects'], 2)
                self.assertFalse(earlier['association_review']['merged'])
        self.assertEqual(earlier['counts']['objects'], 2)
        self.assertEqual(merged['counts']['objects'], 1)
        self.assertEqual(merged['counts']['supporting_observations'], 2)
        self.assertEqual(merged['semantic']['available_supports'], 2)
        self.assertEqual(merged['semantic']['selected_object_ids'], [])
        self.assertEqual(merged['semantic']['ranking'][0]['cosine_similarity'], 0.)
        self.assertIn('coobserved_duplicates', merged['context']['association_policy'])
        original = self.query(axis(1))
        self.assertEqual(original['counts']['objects'], 2)
        self.assertEqual(original['semantic']['available_supports'], 4)
        self.assertEqual(original['semantic']['selected_object_ids'], [2])
        self.assertNotIn('association_review', original)
        with self.assertRaisesRegex(ValueError, 'complete list/text query'):
            query_online(self.db, 'find', 'bowl', merge_duplicates=True)

    def test_delayed_embedding_cannot_change_earlier_query_and_reopen_matches(self):
        row = self.source()
        self.send('graph', graph({1: [1, 0, 0]}))
        before = self.query()
        self.assertEqual(before['semantic']['status'], 'NO_SEMANTIC_SUPPORT')
        result = self.encoded(row)
        self.send('semantic', result)
        after = self.query()
        self.assertEqual(after['semantic']['selected_object_ids'], [1])
        self.assertEqual(before['snapshot']['event_seq'], 3)
        self.assertEqual(before['semantic']['ranking'], [])
        with Image.open(self.root/result['samples'][0]['crop']) as im:
            np.testing.assert_array_equal(np.asarray(im), self.rgb[:, 1:5])
        self.writer.close()
        reopened = self.query()
        self.assertEqual(after['snapshot'], reopened['snapshot'])
        self.assertEqual(after['semantic'], reopened['semantic'])

    def test_revision_changes_association_and_semantic_fusion_not_original_crops(self):
        a, b = self.source(1), self.source(2)
        self.send('graph', graph({1: [1, 0, 0], 2: [1.1, 0, 0]}))
        self.send('semantic', self.encoded(a, 1, axis(0)))
        self.send('semantic', self.encoded(b, 2, axis(1)))
        before = self.query()
        rank = before['semantic']['ranking']
        self.assertEqual(len(rank), 1)
        self.assertAlmostEqual(rank[0]['cosine_similarity'], 2**-.5, places=6)
        self.assertEqual(rank[0]['geometry']['semantic_support_count'], 2)
        self.send('graph', graph({1: [1, 0, 0], 2: [3, 0, 0]}))
        after = self.query()
        self.assertEqual([r['cosine_similarity'] for r in after['semantic']['ranking']], [1., 0.])
        np.testing.assert_allclose(after['semantic']['ranking'][1]['geometry']['map_point_m'], [3, 0, 2])
        self.assertEqual(after['semantic']['ranking'][0]['best_view'], rank[0]['best_view'])
        self.send('graph', graph({2: [3, 0, 0]}))
        self.assertEqual(self.query()['semantic']['status'], 'NO_CANDIDATE_ABOVE_THRESHOLD')

    def test_partial_support_is_explicit_and_unknown_query_selects_nothing(self):
        a = self.source(1)
        self.source(2)
        self.send('graph', graph({1: [1, 0, 0], 2: [1.1, 0, 0]}))
        self.send('semantic', self.encoded(a))
        query = self.query(axis(2))['semantic']
        self.assertEqual(query['status'], 'NO_CANDIDATE_ABOVE_THRESHOLD')
        self.assertEqual(query['available_supports'], 1)
        self.assertEqual(query['ranking'][0]['geometry']['support_count'], 2)
        self.assertEqual(query['missing_supports'][0]['node_id'], 2)

    def test_commit_during_query_does_not_leak_later_embedding(self):
        import online_scene_memory as online
        row = self.source()
        self.send('graph', graph({1: [1, 0, 0]}))
        encoded = self.encoded(row)
        original = online.rebuild_objects
        def commit_later(connection):
            self.send('semantic', encoded)
            original(connection)
        with patch('online_scene_memory.rebuild_objects', side_effect=commit_later):
            before = self.query()
        self.assertEqual(before['snapshot']['event_seq'], 3)
        self.assertEqual(before['semantic']['status'], 'NO_SEMANTIC_SUPPORT')
        self.assertEqual(self.query()['semantic']['selected_object_ids'], [1])

    def test_model_mismatch_and_old_label_journal_refused(self):
        with self.assertRaisesRegex(ValueError, 'encoder or policy mismatch'):
            query_online(self.db, text_vector=axis(0), encoder_identity={'other': True})
        old = self.root/'old.db'
        writer = OnlineMemoryWriter(old, context())
        writer.close()
        with self.assertRaisesRegex(ValueError, 'encoder or policy mismatch'):
            query_online(old, text_vector=axis(0), encoder_identity=IDENTITY)
        self.assertEqual(query_online(old)['status'], 'NO_GRAPH')
        with self.assertRaisesRegex(ValueError, 'no declared semantic encoder'):
            query_text(old, self.root/'missing_model.pt', 'a bowl', self.root/'refused_query')
        self.assertTrue((self.root/'refused_query/query.json').exists())
        with self.assertRaisesRegex(ValueError, 'encoder or policy mismatch'):
            query_online(self.db, text_vector=axis(0), encoder_identity={**IDENTITY, 'square_pad': True})

    def test_missing_source_or_future_evidence_fails_writer(self):
        row = self.source()
        result = self.encoded(row)
        result['started_elapsed_s'] = self.clock+100
        self.writer.submit('semantic', result, self.clock+1)
        with self.assertRaisesRegex(RuntimeError, 'writer failed'):
            self.writer.close()
        self.assertEqual(self.query()['semantic']['semantic_event_count'], 0)

    def test_refused_pose_cannot_gain_an_embedding(self):
        row = self.source(pose='REJECTED')
        result = self.encoded(row)
        self.writer.submit('semantic', result, self.clock+1)
        with self.assertRaises(RuntimeError):
            self.writer.close()

    def test_wrong_rgb_cache_and_existing_crop_are_not_silent_fallbacks(self):
        row = self.source()
        self.crops.mkdir()
        wrong = self.rgb.copy(); wrong[0, 0, 0] += 1
        with self.assertRaisesRegex(ValueError, 'Cached RGB'):
            encode_keyframe(KnownEncoder(), row, wrong, 1, self.crops, lambda: self.clock)
        self.encoded(row)
        with self.assertRaises(FileExistsError):
            self.encoded(row)

    def test_invalid_vector_crop_hash_and_duplicate_outcome_fail(self):
        from online_semantic_memory import validate_semantic
        row = self.source()
        result = self.encoded(row)
        with closing(sqlite3.connect(self.db)) as connection:
            for field, value in [('vector', [0.]*512), ('crop_sha256', 'bad'),
                                 ('box_xyxy_exclusive', [0, 0, 5, 4]), ('crop', '../outside.png')]:
                bad = copy.deepcopy(result)
                bad['samples'][0][field] = value
                with self.assertRaises(ValueError):
                    validate_semantic(connection, self.writer.context, bad, self.clock+1)
        self.send('semantic', result)
        self.writer.submit('semantic', result, self.clock+1)
        with self.assertRaises(RuntimeError):
            self.writer.close()

    def test_real_worker_queue_bound_cache_eviction_and_cleanup(self):
        row = self.source()
        capture = OnlineSemanticCapture(KnownEncoder(), self.writer, self.crops, lambda: self.clock)
        self.addCleanup(capture.close)
        for i in range(POLICY['rgb_cache_frames']+1):
            capture.remember({'source_stamp_ns': STAMP+i}, self.rgb)
        self.assertEqual(len(capture.images), POLICY['rgb_cache_frames'])
        capture.request({'node_id': 1, 'stamp_ns': STAMP})
        capture.pump(self.rows)
        self.assertEqual(capture.stats['rejections'], {'source_rgb_evicted': 1})
        for node in range(2, POLICY['pending_keyframes']+3):
            self.send('mapping', {'node_id': node, 'stamp_ns': STAMP+node*10**9})
            capture.request({'node_id': node, 'stamp_ns': STAMP+node*10**9})
        self.assertEqual(len(capture.pending), POLICY['pending_keyframes'])
        self.assertEqual(capture.stats['rejections']['semantic_queue_full'], 1)
        capture.close()
        self.writer.close()
        self.assertFalse(capture.images)
        self.assertTrue(capture.closed)
        self.assertFalse(any(t.name.startswith('mobileclip_keyframe') for t in threading.enumerate()))

    def test_real_worker_encodes_only_after_source_finalization(self):
        row = self.source()
        encoder = KnownEncoder()
        capture = OnlineSemanticCapture(encoder, self.writer, self.crops, lambda: self.clock)
        self.addCleanup(capture.close)
        capture.remember(row, self.rgb)
        capture.request({'node_id': 1, 'stamp_ns': STAMP})
        unfinished = copy.deepcopy(row); unfinished['status'] = 'AWAITING_POSE'
        capture.pump([unfinished])
        self.assertIsNone(capture.active)
        capture.pump([row])
        capture.close()
        self.writer.close()
        self.assertEqual(capture.stats['encoded_crops'], 1)
        np.testing.assert_array_equal(encoder.seen[0], self.rgb[:, 1:5])

    def test_crop_budget_preserves_explicit_omissions(self):
        row = self.source()
        original = row['detections'][0]
        row['detections'] = [{**copy.deepcopy(original), 'detection_index': i,
                             'detection_confidence': .9-i*.01} for i in range(20)]
        result = self.encoded(row)
        self.assertEqual(len(result['samples']), 16)
        self.assertEqual([s['detection_index'] for s in result['skipped_detections']], [16, 17, 18, 19])

    def test_encoder_failure_propagates_and_does_not_create_vectors(self):
        class FailedEncoder:
            def encode(self, *args, **kwargs):
                raise RuntimeError('Controlled encoder failure')
        row = self.source()
        capture = OnlineSemanticCapture(FailedEncoder(), self.writer, self.crops, lambda: self.clock)
        self.addCleanup(capture.close)
        capture.remember(row, self.rgb)
        capture.request({'node_id': 1, 'stamp_ns': STAMP})
        capture.pump(self.rows)
        with self.assertRaisesRegex(RuntimeError, 'Controlled encoder failure'):
            capture.close()
        self.writer.close()
        self.assertTrue(capture.closed)
        self.assertEqual(self.query()['semantic']['semantic_event_count'], 0)


if __name__ == '__main__':
    unittest.main()
