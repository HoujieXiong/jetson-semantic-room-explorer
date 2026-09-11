"""Verify temporal memory snapshots through real imports/searches on synthetic evidence."""

from contextlib import closing
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'tests/memory'))
from extract_mapped_rgbd import file_hash
from replay_observation_search import replay_search
from run_offline_search import run_search
from scene_memory import import_report, query
from test_run_offline_search import SearchFixture
from test_scene_memory import detection, frame, report as observation_report


class ObservationReplayTests(SearchFixture):
    def setUp(self):
        super().setUp()
        first = copy.deepcopy(self.observations['frames'][0])
        rejected = detection(3, label='bottle')
        rejected.pop('map_point_m')
        rejected['depth'] = {'status': 'REJECTED', 'reason': 'insufficient_valid_depth', 'valid_pixels': 0}
        first['detections'].append(rejected)
        second = frame(2, [detection(point=(4.05, 1.55, 2), label='bottle'),
                           detection(1, point=(4.5, 1.55, 2), label='bottle', box=(30, 0, 50, 20))])
        third = frame(3, [detection(point=(4.15, 1.55, 2), label='bottle')])
        for item in (second, third):
            for key in ('database_sha256', 'camera_poses_sha256'):
                item[key] = first[key]
        self.frames = [first, second, third]
        self.source = self.root/'observations.json'
        self.save_source()

    def save_source(self, frames=None):
        self.source.write_text(json.dumps(observation_report(*(self.frames if frames is None else frames))))

    def replay(self, label='bottle', start=None):
        result = replay_search(self.source, self.mapping, label, self.output,
                               [1.05, 1.55] if start is None else start)
        self.assertEqual(result['status'], 'REPLAY_COMPLETE')
        self.assertEqual(json.loads((self.output/'replay.json').read_text()), result)
        self.assertIsNone(result['active_stage'])
        self.assertIsNone(result['active_node'])
        self.assertFalse(result['observation_executed'])
        self.assertFalse(result['motion_executed'])
        self.assertFalse(result['new_coverage_measured'])
        for step in result['steps']:
            self.assertEqual(step['status'], 'COMPLETE')
            self.assertEqual(file_hash(self.output/step['memory']), step['memory_sha256'])
            self.assertEqual(file_hash(self.output/step['search_report']), step['search_sha256'])
            child = json.loads((self.output/step['search_report']).read_text())
            self.assertEqual(child['memory_sha256'], step['memory_sha256'])
            self.assertEqual(child['query'], step['query'])
            self.assertEqual(child['outcomes'], step['outcomes'])
            self.assertEqual(child['status'], step['search_status'])
        return result

    def dump(self, path):
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as connection:
            return '\n'.join(connection.iterdump())

    def test_reversed_input_runs_in_source_time_order_and_changes_branch(self):
        self.save_source(self.frames[::-1])
        source_hash = file_hash(self.source)
        result = self.replay(' BOTTLE ')
        self.assertEqual([step['node_id'] for step in result['steps']], [1, 2, 3])
        self.assertEqual([step['source_stamp_ns'] for step in result['steps']], [1010000000, 1020000000, 1030000000])
        self.assertEqual([step['query']['status'] for step in result['steps']], ['NOT_FOUND', 'FOUND', 'FOUND'])
        self.assertEqual([step['branch'] for step in result['steps']], ['frontier', 'object_route', 'object_route'])
        self.assertEqual([step['search_status'] for step in result['steps']], ['EXPLORATION_READY', 'ROUTE_READY', 'ROUTE_READY'])
        self.assertEqual(result['steps'][0]['query_observations'], [
            {'detection_index': 3, 'depth_status': 'REJECTED', 'reason': 'insufficient_valid_depth'}])
        self.assertEqual(result['steps'][1]['query']['candidate_ids'], [4, 5])
        self.assertEqual(len(result['steps'][1]['outcomes']), 2)
        self.assertEqual(file_hash(self.source), source_hash)

    def test_each_snapshot_has_only_its_prefix_and_original_rejection_evidence(self):
        result = self.replay()
        for index, step in enumerate(result['steps'], 1):
            path = self.output/step['memory']
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as connection:
                nodes = connection.execute('SELECT node_id FROM frames ORDER BY source_stamp_ns').fetchall()
                self.assertEqual(nodes, [(i,) for i in range(1, index+1)])
                raw = json.loads(connection.execute('SELECT evidence_json FROM frames WHERE node_id=1').fetchone()[0])
                self.assertEqual(raw['detections'][-1], self.frames[0]['detections'][-1])
                self.assertEqual(connection.execute("SELECT object_id FROM associations WHERE node_id=1 AND detection_index=3").fetchall(), [(None,)])
            self.assertEqual(step['import']['added_frames'], 1)
            self.assertEqual(step['import']['existing_frames'], index-1)
        first = query(self.output/result['steps'][0]['memory'], 'find', 'bottle')
        self.assertEqual(first['objects'], [])
        second = query(self.output/result['steps'][1]['memory'], 'find', 'bottle')
        last = query(self.output/result['steps'][2]['memory'], 'find', 'bottle')
        self.assertEqual([obj['support_count'] for obj in second['objects']], [1, 1])
        self.assertEqual([obj['support_count'] for obj in last['objects']], [2, 1])

    def test_final_logical_memory_matches_full_import_and_duplicates_do_not_write(self):
        result = self.replay()
        expected = self.root/'reference.db'
        import_report(expected, json.loads(self.source.read_text()))
        final = self.output/result['steps'][-1]['memory']
        self.assertEqual(self.dump(final), self.dump(expected))
        duplicate = self.root/'duplicate.db'
        shutil.copyfile(final, duplicate)
        before = file_hash(duplicate)
        imported = import_report(duplicate, json.loads(self.source.read_text()))
        self.assertEqual((imported['added_frames'], imported['existing_frames']), (0, 3))
        self.assertEqual(file_hash(duplicate), before)

    def test_later_rejection_only_frame_is_retained_without_an_object(self):
        middle = copy.deepcopy(self.frames[1])
        middle['detections'] = [self.frames[0]['detections'][-1]]
        middle['accepted_observations'] = 0
        self.save_source([self.frames[0], middle, self.frames[2]])
        result = self.replay()
        self.assertEqual([step['query']['status'] for step in result['steps']], ['NOT_FOUND', 'NOT_FOUND', 'FOUND'])
        self.assertEqual(result['steps'][1]['query_observations'][0]['depth_status'], 'REJECTED')
        self.assertEqual(result['steps'][1]['import']['counts']['decisions']['depth_rejected'], 2)

    def test_absent_label_keeps_exploring_at_every_prefix(self):
        result = self.replay('backpack')
        self.assertTrue(all(step['branch_reason'] == 'target_not_in_memory' for step in result['steps']))
        self.assertTrue(all(step['query_observations'] == [] for step in result['steps']))

    def test_remembered_but_unusable_goal_keeps_its_reasons(self):
        result = self.replay('refrigerator')
        for step in result['steps']:
            self.assertEqual(step['branch_reason'], 'no_object_goal')
            self.assertEqual(step['query']['goal_rejections'], [{'object_id': 3, 'reason': 'target_outside_grid'}])

    def test_invalid_simulated_start_is_preserved_across_branch_change(self):
        result = self.replay(start=[.15, 3.55])
        self.assertEqual([step['search_status'] for step in result['steps']], ['INVALID_START', 'NO_ROUTE', 'NO_ROUTE'])
        for step in result['steps']:
            self.assertTrue(all(row['reason'] == 'unknown_cell' for row in step['outcomes']))
            self.assertTrue(all(row['length_m'] is None for row in step['outcomes']))

    def test_incompatible_pose_identity_fails_before_any_import(self):
        for item in self.frames:
            item['camera_poses_sha256'] = 'f'*64
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'incompatible pose identity'):
            self.replay()
        saved = json.loads((self.output/'replay.json').read_text())
        self.assertEqual(saved['status'], 'INCOMPLETE')
        self.assertEqual(saved['active_stage'], 'source_validation')
        self.assertEqual(saved['steps'], [])
        self.assertEqual(list(self.output.rglob('*.db')), [])

    def test_mixed_map_identities_and_conflicting_source_nodes_fail(self):
        original = copy.deepcopy(self.frames)
        self.frames[1]['database_sha256'] = 'f'*64
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'Mixed frozen map'):
            self.replay()
        self.output = self.root/'duplicate_nodes'
        self.save_source([*original, original[0]])
        with self.assertRaisesRegex(ValueError, 'Duplicate or invalid node'):
            self.replay()

    def test_source_timestamp_mismatch_is_not_reordered_away(self):
        self.frames[1]['rgb_stamp_ns'] += 1
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'source timestamps disagree'):
            self.replay()
        self.assertEqual(json.loads((self.output/'replay.json').read_text())['steps'], [])

    def test_first_rejection_only_prefix_is_explicitly_unsupported(self):
        first = self.frames[0]
        first['detections'] = [first['detections'][-1]]
        first['accepted_observations'] = 0
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'Report observation counts disagree'):
            self.replay()
        saved = json.loads((self.output/'replay.json').read_text())
        self.assertEqual(saved['active_stage'], 'import')
        self.assertEqual(saved['active_node'], 1)
        self.assertEqual(saved['steps'][0]['status'], 'INCOMPLETE')
        self.assertEqual(list(self.output.rglob('*.db')), [])

    def test_later_search_failure_retains_completed_prefix_and_propagates(self):
        def fail_second(memory, *args, **kwargs):
            if memory.parent.name == 'node_2':
                raise OSError('Injected second-search failure')
            return run_search(memory, *args, **kwargs)

        with patch('replay_observation_search.run_search', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'Injected second-search failure'):
                self.replay()
        saved = json.loads((self.output/'replay.json').read_text())
        self.assertEqual(saved['status'], 'INCOMPLETE')
        self.assertEqual((saved['active_stage'], saved['active_node']), ('search', 2))
        self.assertEqual([step['status'] for step in saved['steps']], ['COMPLETE', 'INCOMPLETE'])
        first = saved['steps'][0]
        self.assertEqual(file_hash(self.output/first['memory']), first['memory_sha256'])
        self.assertFalse((self.output/'node_3').exists())

    def test_source_changed_during_replay_cannot_finish_successfully(self):
        def change_source(*args, **kwargs):
            result = run_search(*args, **kwargs)
            with self.source.open('a') as stream:
                stream.write('\n')
            return result

        with patch('replay_observation_search.run_search', side_effect=change_source):
            with self.assertRaisesRegex(ValueError, 'Source observations changed'):
                self.replay()
        self.assertEqual(json.loads((self.output/'replay.json').read_text())['status'], 'INCOMPLETE')

    def test_output_reuse_preserves_snapshots_and_reports(self):
        self.replay()
        before = {p: file_hash(p) for p in self.output.rglob('*') if p.is_file()}
        with self.assertRaises(FileExistsError):
            self.replay()
        self.assertEqual(before, {p: file_hash(p) for p in before})

    def test_nonfinite_or_malformed_start_is_refused(self):
        with self.assertRaises(ValueError):
            self.replay(start=[float('nan'), 1])
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(ValueError, 'finite map x/y'):
            self.replay(start=[1])
        self.assertEqual(json.loads((self.output/'replay.json').read_text())['steps'], [])


if __name__ == '__main__':
    unittest.main()
