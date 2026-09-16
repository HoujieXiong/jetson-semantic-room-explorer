"""Real journal snapshots, known map geometry, and explicit causal refusals."""

import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from online_scene_memory import OnlineMemoryWriter, query_online
from online_search_preview import GRID_POLICY, grid_from_event, plan_snapshot
from online_semantic_memory import POLICY as SEMANTIC_POLICY, encode_keyframe
from test_online_scene_memory import STAMP, context, graph, observation
from test_online_semantic_memory import IDENTITY, KnownEncoder, axis


def occupancy(stamp=STAMP):
    cells = np.zeros((60, 60), dtype=np.int8)
    return {'stamp_ns': stamp, 'frame_id': 'map', 'width': 60, 'height': 60,
            'resolution_m': .1, 'origin_position_m': [-3., -3., 0.],
            'origin_quaternion_xyzw': [0., 0., 0., 1.], 'cells': cells.ravel().tolist(),
            'cells_sha256': hashlib.sha256(cells.tobytes()).hexdigest()}


class OnlineSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root/'online.db'
        self.origin = time.monotonic_ns()-2_000_000_000
        self.writer = OnlineMemoryWriter(self.db, {**context(), 'origin_monotonic_ns': self.origin,
            'semantic_encoder': IDENTITY, 'semantic_policy': SEMANTIC_POLICY, 'grid_policy': GRID_POLICY})
        self.addCleanup(self.writer.close)
        self.seq = 0
        rgb = np.zeros((20, 20, 3), dtype=np.uint8)
        row = observation()
        row.update(camera_info={'width': 20, 'height': 20}, rgb_pixels_sha256=hashlib.sha256(rgb.tobytes()).hexdigest())
        self.send('mapping', {'node_id': 1, 'stamp_ns': STAMP})
        self.send('observation', row)
        crops = self.root/'online.crops'; crops.mkdir()
        encoded = encode_keyframe(KnownEncoder(), row, rgb, 1, crops, lambda: 1.)
        encoded['requested_elapsed_s'] = 1.
        self.send('semantic', encoded)
        self.send('graph', graph({1: [0., 0., 0.]}))

    def send(self, kind, payload):
        self.writer.submit(kind, payload, 1.)
        self.seq += 1
        deadline = time.monotonic()+3
        while self.writer.stats['events_committed'] < self.seq:
            self.writer.check()
            if time.monotonic() > deadline:
                self.fail('Writer did not commit')
            time.sleep(.005)

    def query(self, vector=None):
        return query_online(self.db, text_vector=axis(0) if vector is None else vector,
                            encoder_identity=IDENTITY, planning=True)

    def test_matching_received_grid_reuses_metric_route_and_preserves_source_identity(self):
        self.send('occupancy', occupancy())
        query = self.query()
        result = plan_snapshot(query, 'a bottle')
        self.assertEqual(result['search_status'], 'ROUTE_READY')
        self.assertEqual(result['snapshot'], query['snapshot'])
        self.assertEqual(result['start']['kind'], 'recorded_camera_link_projection')
        path = result['selection']['route']['path_map_xy_m']
        self.assertEqual(path[0], [0., 0.])
        self.assertEqual(path[-1], result['selection']['goal']['map_xy_m'])
        self.assertTrue(all(a[0] == b[0] or a[1] == b[1] for a, b in zip(path, path[1:])))
        self.assertGreaterEqual(np.linalg.norm(path[-1]), .75)
        self.assertLessEqual(np.linalg.norm(path[-1]), 1.25)
        self.assertEqual(result['occupancy']['event_seq'], 5)

    def test_missing_grid_and_later_commit_do_not_change_earlier_query(self):
        query = self.query()
        self.send('occupancy', occupancy())
        self.assertEqual(plan_snapshot(query, 'bottle')['reason'], 'missing_occupancy')
        self.assertEqual(plan_snapshot(self.query(), 'bottle')['search_status'], 'ROUTE_READY')

    def test_grid_commit_during_query_is_outside_snapshot(self):
        import online_scene_memory as online
        rebuild = online.rebuild_objects
        def commit(connection):
            self.send('occupancy', occupancy())
            rebuild(connection)
        with patch('online_scene_memory.rebuild_objects', side_effect=commit):
            query = self.query()
        self.assertEqual(plan_snapshot(query, 'bottle')['reason'], 'missing_occupancy')

    def test_new_graph_cannot_reuse_previous_grid(self):
        self.send('occupancy', occupancy())
        before = self.query()
        self.send('mapping', {'node_id': 2, 'stamp_ns': STAMP+10**9})
        self.send('graph', graph({1: [1., 0., 0.], 2: [0., 0., 0.]}, STAMP+10**9))
        result = plan_snapshot(self.query(), 'bottle')
        self.assertEqual(result['reason'], 'grid_graph_stamp_mismatch')
        self.assertIsNone(result['selection'])
        self.assertEqual(plan_snapshot(before, 'bottle')['search_status'], 'ROUTE_READY')

    def test_mismatched_session_graph_prefix_and_missing_start_are_refused(self):
        self.send('occupancy', occupancy())
        query = self.query()
        cases = [('session_id', 'other', 'incompatible_snapshot_or_grid_policy'),
                 ('mapping', None, 'missing_current_mapping')]
        for key, value, reason in cases:
            altered = copy.deepcopy(query); altered['planning_evidence'][key] = value
            self.assertEqual(plan_snapshot(altered, 'bottle')['reason'], reason)
        altered = copy.deepcopy(query); altered['snapshot']['graph_sha256'] = '0'*64
        self.assertEqual(plan_snapshot(altered, 'bottle')['reason'], 'graph_identity_mismatch')
        altered = copy.deepcopy(query); altered['planning_evidence']['occupancy']['event_seq'] += 10
        self.assertEqual(plan_snapshot(altered, 'bottle')['reason'], 'evidence_outside_query_prefix')

    def test_paused_old_journal_future_time_and_source_lag_are_refused(self):
        self.send('occupancy', occupancy())
        query = self.query()
        for now in (query['read_started_monotonic_ns']+11*10**9, self.origin):
            self.assertEqual(plan_snapshot(query, 'bottle', now_ns=now)['reason'], 'stale_or_future_map_evidence')
        query['planning_evidence']['latest_source_stamp_ns'] = STAMP+11*10**9
        self.assertEqual(plan_snapshot(query, 'bottle')['reason'], 'stale_or_future_map_evidence')

    def test_explicit_simulated_start_and_invalid_start_do_not_snap(self):
        self.send('occupancy', occupancy())
        good = plan_snapshot(self.query(), 'bottle', [.01, .02])
        self.assertEqual(good['start']['kind'], 'simulated_grid_fixture')
        self.assertEqual(good['selection']['route']['path_map_xy_m'][0], [.01, .02])
        bad = plan_snapshot(self.query(), 'bottle', [100., 100.])
        self.assertEqual(bad['search_status'], 'NO_ROUTE')
        self.assertIsNone(bad['selection'])
        self.assertEqual(bad['outcomes'][0]['route']['status'], 'INVALID_START')

    def test_unknown_query_uses_frontier_and_never_creates_an_object(self):
        grid = occupancy()
        cells = np.array(grid['cells'], dtype=np.int8).reshape(60, 60)
        cells[:, 50:] = -1
        grid.update(cells=cells.ravel().tolist(), cells_sha256=hashlib.sha256(cells.tobytes()).hexdigest())
        self.send('occupancy', grid)
        result = plan_snapshot(self.query(axis(1)), 'an elephant')
        self.assertEqual(result['branch'], 'frontier')
        self.assertEqual(result['search_status'], 'EXPLORATION_READY')
        self.assertIsNone(result['selection']['object_id'])
        self.assertEqual(result['semantic_selection']['selected_object_ids'], [])

    def test_grid_integrity_orientation_dimensions_and_values(self):
        original = occupancy()
        for key, value in [('cells_sha256', '0'*64), ('width', 59), ('width', 100000),
                           ('origin_quaternion_xyzw', [0, 0, 1, 0]), ('frame_id', 'odom'),
                           ('resolution_m', float('nan')), ('cells', [50]*3600)]:
            altered = {**original, key: value}
            with self.assertRaises(ValueError):
                grid_from_event(altered)
        cells = original['cells']; cells[1] = 100; cells[60] = -1
        original['cells_sha256'] = hashlib.sha256(np.array(cells, dtype=np.int8).tobytes()).hexdigest()
        decoded = grid_from_event(original)
        self.assertEqual(decoded.cells[0, 1], 100)
        self.assertEqual(decoded.cells[1, 0], -1)

    def test_old_query_api_unchanged_and_reopen_keeps_planning_snapshot(self):
        self.send('occupancy', occupancy())
        original = self.query()
        self.writer.close()
        reopened = self.query()
        for key in ('snapshot', 'semantic', 'objects', 'planning_evidence'):
            self.assertEqual(original[key], reopened[key])
        self.assertEqual(query_online(self.db)['objects'], original['objects'])


if __name__ == '__main__':
    unittest.main()
