"""Real SQLite event prefixes, graph revisions and bounded writer failures."""

from contextlib import closing
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import online_scene_memory as online
from observe_rgbd_objects import DEPTH_POLICY, INFERENCE
from scene_memory import query as frozen_query


STAMP = 1789512489378743000


def context():
    return {'reference_sha256': 'a'*64, 'model_sha256': 'b'*64,
            'inference': INFERENCE, 'depth_policy': DEPTH_POLICY, 'runtime': {'test': True},
            'session_id': 'controlled-test', 'origin_monotonic_ns': time.monotonic_ns(),
            'camera_frame': 'camera_color_optical_frame', 'map_frame': 'map', 'point_unit': 'meter'}


def observation(stamp=STAMP, status='ACCEPTED'):
    detection = {'detection_index': 0, 'label': 'bottle', 'class_id': 39, 'detection_confidence': .9,
                 'box_xyxy': [0., 0., 20., 20.],
                 'depth': {'status': 'ACCEPTED', 'camera_point_m': [0., 0., 2.], 'depth_m': 2.}}
    pose = {'status': status, 'checked_elapsed_s': .3}
    if status == 'ACCEPTED':
        pose.update(source_stamp_ns=stamp, map_from_camera=np.eye(4).tolist(),
                    odom_evidence={'stamp_ns': stamp, 'lost': False, 'received_elapsed_s': .25})
        detection['map_point_m'] = [0., 0., 2.]
    else:
        pose['reason'] = 'missing_source_map_tf'
    return {'source_stamp_ns': stamp, 'rgb_stamp_ns': stamp, 'depth_stamp_ns': stamp-2_000_000,
            'rgb_depth_skew_ns': 2_000_000, 'rgb_pixels_sha256': 'c'*64, 'depth_pixels_sha256': 'd'*64,
            'status': 'PROCESSED', 'arrived_elapsed_s': .1, 'dispatched_elapsed_s': .15,
            'prediction_completed_elapsed_s': .2, 'completed_elapsed_s': .4,
            'pose': pose, 'detections': [detection]}


def graph(positions, stamp=STAMP):
    return {'stamp_ns': stamp, 'poses': [{'node_id': node, 'position_m': position,
             'quaternion_xyzw': [0., 0., 0., 1.]} for node, position in positions.items()],
            'extrinsic': {'status': 'ACCEPTED', 'camera_link_from_optical': np.eye(4).tolist()}}


class OnlineMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'online.db'
        self.writer = online.OnlineMemoryWriter(self.db, context())
        self.addCleanup(self.close)
        self.elapsed = 1.
        self.submitted = 0

    def close(self):
        try:
            self.writer.close()
        except RuntimeError:
            if self.writer.thread.is_alive():
                raise

    def flush(self):
        deadline = time.monotonic()+3
        while self.writer.stats['events_committed'] < self.submitted:
            self.writer.check()
            if time.monotonic() > deadline:
                self.fail('Writer did not commit within three seconds')
            time.sleep(.005)

    def send(self, kind, payload):
        self.elapsed += 1
        self.writer.submit(kind, payload, self.elapsed)
        self.submitted += 1
        self.flush()

    def source(self, node, status='ACCEPTED'):
        stamp = STAMP+(node-1)*1_000_000_000
        self.send('mapping', {'node_id': node, 'stamp_ns': stamp+191})
        self.send('observation', observation(stamp, status))

    def test_live_provenance_is_distinct_and_persists_without_bag_reference(self):
        provenance = context()
        del provenance['reference_sha256']
        provenance['live_config_sha256'] = 'e'*64
        path = self.db.with_name('live.db')
        writer = online.OnlineMemoryWriter(path, provenance)
        writer.close()
        with closing(sqlite3.connect(path)) as connection:
            saved = json.loads(connection.execute('SELECT context_json FROM metadata').fetchone()[0])
        self.assertEqual(saved['live_config_sha256'], 'e'*64)
        self.assertEqual(saved['policy'], online.LIVE_POLICY)
        self.assertNotIn('reference_sha256', saved)
        self.assertEqual(online.query_online(path)['status'], 'NO_GRAPH')

    def test_explicit_large_detector_journal_preserves_gates_and_refuses_policy_changes(self):
        provenance = {**context(), 'inference': {**INFERENCE, 'imgsz': 1280}}
        path = self.db.with_name('large.db')
        writer = online.OnlineMemoryWriter(path, provenance)
        writer.close()
        with closing(sqlite3.connect(path)) as connection:
            saved = json.loads(connection.execute('SELECT context_json FROM metadata').fetchone()[0])
        self.assertEqual(saved['inference'], provenance['inference'])
        self.assertEqual(saved['depth_policy'], DEPTH_POLICY)
        self.assertEqual(online.query_online(path)['status'], 'NO_GRAPH')
        for key, value in [('imgsz', 641), ('confidence_threshold', .1), ('device', 'cpu')]:
            invalid = {**provenance, 'inference': {**provenance['inference'], key: value}}
            refused = self.db.with_name('refused.db')
            with self.assertRaises(ValueError):
                online.OnlineMemoryWriter(refused, invalid)
            self.assertFalse(refused.exists())

    def test_live_burst_is_bounded_and_original_live_failure_stays_readable(self):
        provenance = context()
        del provenance['reference_sha256']
        provenance['live_config_sha256'] = 'e'*64
        path = self.db.with_name('live.db')
        writer = online.OnlineMemoryWriter(path, provenance)
        try:
            with closing(sqlite3.connect(path)) as blocker:
                blocker.execute('BEGIN IMMEDIATE')
                writer.submit('mapping', {'node_id': 1, 'stamp_ns': STAMP}, 1.)
                deadline = time.monotonic()+.2
                while not writer.queue.empty() and time.monotonic() < deadline:
                    time.sleep(.001)
                for node in range(2, online.LIVE_POLICY['queue_capacity']+2):
                    writer.submit('mapping', {'node_id': node, 'stamp_ns': STAMP+node}, float(node))
                with self.assertRaisesRegex(RuntimeError, 'queue full'):
                    writer.submit('mapping', {'node_id': 1000, 'stamp_ns': STAMP+1000}, 1000.)
                blocker.rollback()
        finally:
            writer.close()
        self.assertEqual(writer.stats['events_committed'], 513)
        self.assertEqual(sum(writer.stats['committed_batch_sizes']), 513)
        self.assertEqual(max(writer.stats['committed_batch_sizes']), 16)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute('SELECT seq FROM events ORDER BY seq').fetchall(),
                             [(i,) for i in range(1, 514)])
        with closing(sqlite3.connect(path)) as connection:
            old = {**writer.context, 'policy': online.POLICY}
            connection.execute('UPDATE metadata SET context_json=?', (json.dumps(old),))
            connection.commit()
        self.assertEqual(online.query_online(path)['status'], 'NO_GRAPH')

    def test_failed_live_batch_rolls_back_without_exposing_partial_prefix(self):
        provenance = context()
        del provenance['reference_sha256']
        provenance['live_config_sha256'] = 'e'*64
        path = self.db.with_name('live.db')
        # Hold the first real validation so the following pair is queued together.
        import threading
        entered, release = threading.Event(), threading.Event()
        original = online.validate_event
        def validate(kind, payload, elapsed):
            if payload.get('node_id') == 1:
                entered.set()
                if not release.wait(2):
                    raise TimeoutError('Test did not release the writer')
            return original(kind, payload, elapsed)
        with patch.object(online, 'validate_event', side_effect=validate):
            writer = online.OnlineMemoryWriter(path, provenance)
            try:
                writer.submit('mapping', {'node_id': 1, 'stamp_ns': STAMP}, 1.)
                self.assertTrue(entered.wait(2))
                writer.submit('mapping', {'node_id': 2, 'stamp_ns': STAMP+1}, 2.)
                writer.submit('mapping', {'node_id': 2, 'stamp_ns': STAMP+2}, 3.)
            finally:
                release.set()
                with self.assertRaises(RuntimeError):
                    writer.close()
        self.assertEqual(writer.stats['events_committed'], 1)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute('SELECT seq FROM events').fetchall(), [(1,)])
        self.assertEqual(online.query_online(path)['snapshot']['event_seq'], 1)

    def test_ambiguous_missing_or_malformed_source_provenance_is_rejected(self):
        for source in ({'live_config_sha256': 'e'*64}, {}, {'live_config_sha256': 'invalid'}):
            provenance = context()
            if source != {'live_config_sha256': 'e'*64}:
                del provenance['reference_sha256']
            provenance.update(source)
            with self.assertRaises(ValueError):
                online.OnlineMemoryWriter(self.db.with_name('invalid.db'), provenance)
            self.assertFalse(self.db.with_name('invalid.db').exists())

    def test_query_before_graph_and_delayed_observation_has_no_future_data(self):
        self.assertEqual(online.query_online(self.db)['status'], 'NO_GRAPH')
        self.send('mapping', {'node_id': 1, 'stamp_ns': STAMP})
        self.send('graph', graph({1: [1, 0, 0]}))
        first = online.query_online(self.db)
        self.assertEqual(first['status'], 'NOT_FOUND')
        self.assertEqual(first['excluded_nodes'][0]['reason'], 'source_observation_not_finalized')
        self.send('observation', observation())
        second = online.query_online(self.db, 'find', 'BOTTLE')
        self.assertEqual(first['snapshot']['event_seq'], 2)
        self.assertEqual(first['objects'], [])
        self.assertEqual(second['snapshot']['event_seq'], 3)
        self.assertEqual(second['snapshot']['graph_seq'], 2)
        np.testing.assert_allclose(second['objects'][0]['map_point_m'], [1, 0, 2])

    def test_graph_revision_reprojects_all_supports_and_reopen_keeps_results(self):
        self.source(1)
        self.source(2)
        self.send('graph', graph({1: [1, 0, 0], 2: [1.1, 0, 0]}))
        before = online.query_online(self.db)
        self.assertEqual(before['objects'][0]['support_count'], 2)
        np.testing.assert_allclose(before['objects'][0]['map_point_m'], [1.05, 0, 2])
        with closing(sqlite3.connect(self.db)) as connection:
            original = connection.execute('SELECT payload_json FROM events WHERE kind="observation"').fetchall()
        self.send('graph', graph({1: [4, 0, 0], 2: [4.1, 0, 0]}))
        after = online.query_online(self.db)
        np.testing.assert_allclose(after['objects'][0]['map_point_m'], [4.05, 0, 2])
        self.assertNotEqual(before['snapshot']['graph_sha256'], after['snapshot']['graph_sha256'])
        self.writer.close()
        reopened = online.query_online(self.db)
        self.assertEqual(after['objects'], reopened['objects'])
        self.assertEqual(after['snapshot'], reopened['snapshot'])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(original, connection.execute('SELECT payload_json FROM events WHERE kind="observation"').fetchall())
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone(), ('ok',))
        self.assertFalse(self.writer.thread.is_alive())

    def test_removed_graph_nodes_are_excluded_and_returning_nodes_restore_support(self):
        self.source(1)
        self.source(2)
        self.send('graph', graph({1: [1, 0, 0], 2: [1.1, 0, 0]}))
        self.send('graph', graph({2: [1.1, 0, 0]}))
        current = online.query_online(self.db)
        self.assertEqual(current['objects'][0]['support_count'], 1)
        self.assertEqual(current['excluded_nodes'][0]['reason'], 'not_in_current_graph')
        self.assertEqual(current['observation_events'], 2)
        self.send('graph', graph({1: [1, 0, 0], 2: [1.1, 0, 0]}))
        self.assertEqual(online.query_online(self.db)['objects'][0]['support_count'], 2)

    def test_source_pose_refusal_is_not_repaired_by_later_graph(self):
        self.source(1, 'REJECTED')
        self.send('graph', graph({1: [1, 0, 0]}))
        result = online.query_online(self.db)
        self.assertEqual(result['objects'], [])
        self.assertIn('source_pose_rejected', result['excluded_nodes'][0]['reason'])

    def test_drop_and_missing_extrinsic_are_explicit(self):
        dropped = observation()
        dropped.update(status='DROPPED', reason='pending_queue_full')
        self.send('observation', dropped)
        self.send('mapping', {'node_id': 1, 'stamp_ns': STAMP})
        self.source(2)
        revised = graph({1: [0, 0, 0], 2: [0, 0, 0]})
        revised['extrinsic'] = {'status': 'REJECTED', 'reason': 'unavailable'}
        self.send('graph', revised)
        result = online.query_online(self.db)
        self.assertEqual(result['objects'], [])
        self.assertEqual([r['reason'] for r in result['excluded_nodes']],
                         ['observation_dropped: pending_queue_full', 'graph_extrinsic_unavailable'])

    def test_graph_rotation_composes_with_camera_extrinsic(self):
        self.source(1)
        revised = graph({1: [1, 2, 3]})
        revised['poses'][0]['quaternion_xyzw'] = [0, 0, 2**-.5, 2**-.5]
        revised['extrinsic']['camera_link_from_optical'][0][3] = .2
        self.send('graph', revised)
        np.testing.assert_allclose(online.query_online(self.db)['objects'][0]['map_point_m'], [1, 2.2, 5], atol=1e-12)

    def test_query_uses_one_prefix_even_when_writer_commits_during_derivation(self):
        self.source(1)
        self.send('graph', graph({1: [1, 0, 0]}))
        original = online.rebuild_objects
        def concurrent_update(connection):
            self.send('graph', graph({1: [9, 0, 0]}))
            original(connection)
        with patch('online_scene_memory.rebuild_objects', side_effect=concurrent_update):
            result = online.query_online(self.db)
        self.assertEqual(result['snapshot']['event_seq'], 3)
        np.testing.assert_allclose(result['objects'][0]['map_point_m'], [1, 0, 2])
        np.testing.assert_allclose(online.query_online(self.db)['objects'][0]['map_point_m'], [9, 0, 2])

    def test_frozen_reader_and_existing_output_are_refused(self):
        with self.assertRaises(ValueError):
            frozen_query(self.db)
        with self.assertRaises(FileExistsError):
            online.OnlineMemoryWriter(self.db, context())
        missing = Path(self.temp.name)/'absent.db'
        with self.assertRaises(sqlite3.OperationalError):
            online.query_online(missing)
        self.assertFalse(missing.exists())

    def test_changed_extrinsic_fails_writer_without_altering_old_prefix(self):
        self.send('graph', graph({1: [1, 0, 0]}))
        changed = graph({1: [1, 0, 0]})
        changed['extrinsic']['camera_link_from_optical'][0][3] = 1
        self.writer.submit('graph', changed, 4.)
        with self.assertRaisesRegex(RuntimeError, 'writer failed'):
            self.writer.close()
        self.assertFalse(self.writer.thread.is_alive())
        self.assertEqual(online.query_online(self.db)['snapshot']['event_seq'], 1)

    def test_invalid_point_or_future_pose_evidence_is_rejected(self):
        bad = observation(); bad['detections'][0]['map_point_m'][0] = 100
        future = observation(); future['pose']['odom_evidence']['received_elapsed_s'] = 20
        malformed = observation(); malformed['depth_stamp_ns'] -= 10_000_000
        for payload in (bad, future, malformed):
            with self.assertRaises(ValueError):
                online.validate_event('observation', payload, 1.)
        with self.assertRaises(ValueError):
            online.validate_event('graph', graph({1: [float('nan'), 0, 0]}), 1.)

    def test_duplicate_source_is_fatal_and_prefix_remains_queryable(self):
        self.send('observation', observation())
        self.writer.submit('observation', observation(), 5.)
        with self.assertRaises(RuntimeError):
            self.writer.close()
        self.assertEqual(online.query_online(self.db)['observation_events'], 1)

    def test_full_queue_is_explicit_and_drain_closes(self):
        with closing(sqlite3.connect(self.db)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            self.writer.submit('mapping', {'node_id': 1, 'stamp_ns': STAMP}, 2.)
            deadline = time.monotonic()+.2
            while not self.writer.queue.empty() and time.monotonic() < deadline:
                time.sleep(.001)
            for node in range(2, online.POLICY['queue_capacity']+2):
                self.writer.submit('mapping', {'node_id': node, 'stamp_ns': STAMP+node}, float(node+1))
            with self.assertRaisesRegex(RuntimeError, 'queue full'):
                self.writer.submit('mapping', {'node_id': 100, 'stamp_ns': STAMP+100}, 101.)
            blocker.rollback()
        self.writer.close()
        self.assertEqual(self.writer.stats['events_committed'], online.POLICY['queue_capacity']+1)
        self.assertFalse(self.writer.thread.is_alive())


if __name__ == '__main__':
    unittest.main()
