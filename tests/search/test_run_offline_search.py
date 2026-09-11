"""Exercise real search stages with temporary memory/maps; only PNG rendering is stubbed."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'tests/memory'))
from extract_mapped_rgbd import file_hash
from run_offline_search import run_search
from scene_memory import import_report
from test_scene_memory import detection, frame, report as observation_report


class OfflineSearchTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.memory = self.root/'memory.db'
        self.mapping = self.root/'mapping'
        self.export = self.mapping/'export'
        self.export.mkdir(parents=True)
        (self.mapping/'map.db').write_bytes(b'Synthetic frozen map identity')
        (self.export/'room_camera_poses.txt').write_text('1.01 0.15 3.55 2 0 0 0 1 1\n')
        (self.export/'room.yaml').write_text(yaml.safe_dump({
            'image': 'room.pgm', 'resolution': .1, 'origin': [0, 0, 0],
            'negate': 0, 'occupied_thresh': .5, 'free_thresh': .196}))
        self.pixels = np.full((40, 60), 254, dtype=np.uint8)  # Bottom row first in this fixture.
        self.pixels[30:] = 205
        self.save_grid()
        mapped = frame(detections=[detection(point=(4.05, 1.55, 2)),
            detection(1, point=(4.10, 1.55, 2), box=(30, 0, 50, 20)),
            detection(2, point=(20, 20, 2), label='refrigerator', box=(60, 0, 80, 20))])
        mapped.update(database_sha256=file_hash(self.mapping/'map.db'),
                      camera_poses_sha256=file_hash(self.export/'room_camera_poses.txt'))
        import_report(self.memory, observation_report(mapped))
        (self.mapping/'database_check.json').write_text(json.dumps({
            'status': 'VERIFIED', 'database_sha256': mapped['database_sha256'],
            'nodes': [{'node_id': 1, 'map_id': 0, 'source_stamp_ns': mapped['source_stamp_ns']}]}))
        self.output = self.root/'run'
        for name in ('preview_search_goal.render_overlay', 'preview_search_route.render_overlay',
                     'preview_frontier_search.render_frontiers'):
            stub = patch(name)
            stub.start()
            self.addCleanup(stub.stop)

    def save_grid(self):
        self.assertTrue(cv2.imwrite(str(self.export/'room.pgm'), np.flipud(self.pixels)))
        (self.mapping/'export_run.json').write_text(json.dumps({
            'status': 'EXPORTED', 'exit_code': 0, 'database_unchanged': True,
            'files': [{'name': p.name, 'sha256': file_hash(p)} for p in sorted(self.export.iterdir())]}))

    def search(self, label='chair', **start):
        if not start:
            start = {'simulated_xy': [1.05, 1.55]}
        result = run_search(self.memory, self.mapping, label, self.output, **start)
        self.assertEqual(result, json.loads((self.output/'search.json').read_text()))
        for stage in result['stages']:
            path = self.output/stage['report']
            self.assertEqual(stage['sha256'], file_hash(path))
            self.assertEqual(stage['status'], json.loads(path.read_text())['status'])
        self.assertFalse(result['observation_executed'])
        self.assertFalse(result['motion_executed'])
        self.assertFalse(result['new_coverage_measured'])
        self.assertIsNone(result['active_stage'])
        return result

    def test_object_routes_keep_both_candidates_and_original_evidence(self):
        before = file_hash(self.memory)
        result = self.search(' CHAIR ')
        self.assertEqual(result['status'], 'ROUTE_READY')
        self.assertEqual(result['branch'], 'object_route')
        self.assertEqual(result['branch_reason'], 'object_goal_available')
        self.assertEqual(result['query']['candidate_ids'], [1, 2])
        self.assertEqual([row['object_id'] for row in result['outcomes']], [1, 2])
        self.assertTrue(all(row['status'] == 'ROUTE_READY' for row in result['outcomes']))
        source = json.loads((self.output/'goal/preview.json').read_text())
        self.assertEqual(source['object_candidates'][0]['last_observation']['source_stamp_ns'], 1010000000)
        self.assertEqual(result['start']['map_xy_m'], [1.05, 1.55])
        self.assertFalse((self.output/'frontier').exists())
        self.assertEqual(file_hash(self.memory), before)

    def test_missing_target_selects_frontier_without_inventing_object(self):
        result = self.search('backpack')
        self.assertEqual((result['branch'], result['status']), ('frontier', 'EXPLORATION_READY'))
        self.assertEqual(result['branch_reason'], 'target_not_in_memory')
        self.assertEqual(result['query']['candidate_ids'], [])
        self.assertIsNotNone(result['outcomes'][0]['goal'])
        self.assertFalse((self.output/'route').exists())

    def test_known_no_goal_preserves_object_and_rejection(self):
        result = self.search('refrigerator')
        self.assertEqual(result['status'], 'EXPLORATION_READY')
        self.assertEqual(result['branch_reason'], 'no_object_goal')
        self.assertEqual(result['query']['candidate_ids'], [3])
        self.assertEqual(result['query']['goal_rejections'], [{'object_id': 3, 'reason': 'target_outside_grid'}])

    def test_disconnected_object_route_does_not_switch_to_frontier(self):
        self.pixels[:, 30] = 0
        self.save_grid()
        result = self.search()
        self.assertEqual((result['branch'], result['status']), ('object_route', 'NO_ROUTE'))
        self.assertTrue(all(row['reason'] == 'disconnected_under_route_policy' for row in result['outcomes']))
        self.assertFalse((self.output/'frontier').exists())

    def test_camera_start_refusal_preserved_in_each_object_route(self):
        result = self.search(node_id=1)
        self.assertEqual((result['branch'], result['status']), ('object_route', 'NO_ROUTE'))
        self.assertTrue(all(row['status'] == 'INVALID_START' and row['reason'] == 'unknown_cell'
                            for row in result['outcomes']))
        self.assertEqual(result['start']['map_xy_m'], [.15, 3.55])
        self.assertEqual(result['start']['source_stamp_ns'], 1010000000)
        self.assertFalse((self.output/'frontier').exists())

    def test_camera_start_refusal_preserved_in_frontier_branch(self):
        result = self.search('backpack', node_id=1)
        self.assertEqual(result['status'], 'INVALID_START')
        self.assertEqual(result['outcomes'][0]['reason'], 'unknown_cell')
        self.assertIsNone(result['outcomes'][0]['goal'])

    def test_no_frontier_is_a_completed_refusal(self):
        self.pixels[:] = 254
        self.save_grid()
        result = self.search('backpack')
        self.assertEqual(result['status'], 'NO_FRONTIER')
        self.assertEqual(result['outcomes'][0]['reason'], 'no_free_unknown_boundary')

    def test_unreachable_frontiers_remain_no_route(self):
        self.pixels[30:, :30] = 254
        self.pixels[:, 30] = 0
        self.save_grid()
        result = self.search('backpack')
        self.assertEqual((result['branch'], result['status']), ('frontier', 'NO_ROUTE'))
        self.assertEqual(result['outcomes'][0]['reason'], 'no_reachable_frontier_viewpoint')

    def test_changed_map_identity_stops_before_branch_selection(self):
        (self.mapping/'map.db').write_bytes(b'Incompatible map')
        with self.assertRaisesRegex(ValueError, 'map identity'):
            self.search()
        result = json.loads((self.output/'search.json').read_text())
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertIsNone(result['branch'])
        self.assertEqual(result['active_stage'], 'goal')
        self.assertEqual(result['error']['type'], 'ValueError')
        self.assertEqual(result['outcomes'], [])
        self.assertFalse((self.output/'route').exists())

    def test_changed_pose_export_is_not_replaced_by_exploration(self):
        (self.export/'room_camera_poses.txt').write_text('Changed pose evidence')
        with self.assertRaisesRegex(ValueError, 'Frozen export changed'):
            self.search('backpack')
        self.assertFalse((self.output/'frontier').exists())
        self.assertEqual(json.loads((self.output/'search.json').read_text())['status'], 'INCOMPLETE')

    def test_rendering_error_keeps_failed_stage_and_reraises(self):
        with patch('preview_frontier_search.render_frontiers', side_effect=OSError('Injected image write failure')):
            with self.assertRaisesRegex(OSError, 'Injected image write failure'):
                self.search('backpack')
        result = json.loads((self.output/'search.json').read_text())
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['active_stage'], 'frontier')
        self.assertEqual(result['error']['message'], 'Injected image write failure')
        self.assertEqual(result['outcomes'], [])
        child = json.loads((self.output/'frontier/frontier.json').read_text())
        self.assertEqual(child['status'], 'INCOMPLETE')

    def test_changed_generated_goal_fails_at_handoff(self):
        from preview_search_goal import preview

        def changed_preview(*args):
            result = preview(*args)
            path = args[3]/'preview.json'
            saved = json.loads(path.read_text())
            saved['results'][0]['goal']['map_xy_m'][0] += .1
            path.write_text(json.dumps(saved))
            return result

        with patch('run_offline_search.preview', side_effect=changed_preview):
            with self.assertRaisesRegex(ValueError, 'Saved goal decision'):
                self.search()
        result = json.loads((self.output/'search.json').read_text())
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['active_stage'], 'route')
        self.assertFalse((self.output/'frontier').exists())

    def test_missing_memory_keeps_error_and_does_not_create_database(self):
        missing = self.root/'missing.db'
        with self.assertRaises(FileNotFoundError):
            run_search(missing, self.mapping, 'chair', self.output, simulated_xy=[1, 1])
        self.assertFalse(missing.exists())
        self.assertEqual(json.loads((self.output/'search.json').read_text())['error']['type'], 'FileNotFoundError')

    def test_output_reuse_preserves_original_evidence(self):
        self.search('backpack')
        before = {p: file_hash(p) for p in self.output.rglob('*') if p.is_file()}
        with self.assertRaises(FileExistsError):
            self.search()
        self.assertEqual(before, {p: file_hash(p) for p in before})

    def test_explicit_finite_start_is_required(self):
        for start in ({}, {'node_id': 1, 'simulated_xy': [1, 1]}, {'simulated_xy': [float('nan'), 1]}):
            with self.subTest(start=start), self.assertRaises(ValueError):
                run_search(self.memory, self.mapping, 'chair', self.output, **start)
            self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
