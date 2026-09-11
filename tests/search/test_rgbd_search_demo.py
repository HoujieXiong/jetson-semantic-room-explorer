"""Stub the GPU producer boundary; run real map validation, memory imports and search replay."""

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'tests/memory'))
from extract_mapped_rgbd import file_hash
from run_rgbd_search_demo import run_demo
from test_run_offline_search import SearchFixture
from test_scene_memory import detection, frame, report as observation_report


class RGBDSearchDemoTests(SearchFixture):
    def setUp(self):
        super().setUp()
        self.manifest = self.root/'frames.json'
        first = copy.deepcopy(self.observations['frames'][0])
        self.manifest.write_text(json.dumps({key: first[key] for key in ('database_sha256', 'camera_poses_sha256')}))
        self.model = self.root/'model.pt'
        self.model.write_bytes(b'Synthetic weights identity; no inference in unit tests')
        second = frame(2, [detection(point=(4.05, 1.55, 2), label='bottle')])
        for key in ('database_sha256', 'camera_poses_sha256'):
            second[key] = first[key]
        for item in (first, second):
            item['frames_manifest_sha256'] = file_hash(self.manifest)
        self.generated = observation_report(first, second)
        self.generated['model_sha256'] = file_hash(self.model)
        self.code = 0
        stub = patch('run_rgbd_search_demo.observe', side_effect=self.produce)
        self.producer = stub.start()
        self.addCleanup(stub.stop)

    def produce(self, args):
        self.assertEqual(args.frames, self.manifest)
        self.assertEqual(args.model, self.model)
        self.assertEqual(args.nodes, [1, 2])
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output/'observations.json').write_text(json.dumps(self.generated))
        return self.code

    def demo(self, nodes=None, start=None):
        result = run_demo(self.manifest, self.model, [1, 2] if nodes is None else nodes,
                          self.mapping, 'bottle', self.output, [1.05, 1.55] if start is None else start)
        self.assertEqual(json.loads((self.output/'demo.json').read_text()), result)
        self.assertIsNone(result['active_stage'])
        self.assertFalse(result['live_capture_executed'])
        self.assertFalse(result['motion_executed'])
        self.assertFalse(result['new_coverage_measured'])
        for stage in result['stages']:
            self.assertEqual(stage['sha256'], file_hash(self.output/stage['report']))
        return result

    def test_generated_observations_feed_real_memory_and_search(self):
        before = file_hash(self.memory)
        result = self.demo()
        self.assertEqual(result['status'], 'DEMO_COMPLETE')
        self.assertEqual(result['perception'], {'accepted_observations': 4, 'rejected_detections': 0})
        self.assertEqual([s['name'] for s in result['stages']], ['perception', 'replay'])
        self.assertEqual([s['query']['status'] for s in result['timeline']], ['NOT_FOUND', 'FOUND'])
        self.assertEqual([s['search_status'] for s in result['timeline']], ['EXPLORATION_READY', 'ROUTE_READY'])
        replay = json.loads((self.output/'replay/replay.json').read_text())
        self.assertEqual(replay['observations_sha256'], result['stages'][0]['sha256'])
        self.assertEqual(replay['observations_path'], str(self.output/'perception/observations.json'))
        self.assertEqual(result['timeline'][1]['source_stamp_ns'], 1020000000)
        self.assertEqual(file_hash(self.memory), before)
        self.producer.assert_called_once()

    def test_no_valid_observations_preserves_exit_outcome_without_replay(self):
        for item in self.generated['frames']:
            item['accepted_observations'] = 0
            for d in item['detections']:
                d.pop('map_point_m')
                d['depth'] = {'status': 'REJECTED', 'reason': 'insufficient_valid_depth'}
        self.generated.update(status='NO_VALID_OBSERVATIONS', accepted_observations=0, rejected_detections=4)
        self.code = 2
        result = self.demo()
        self.assertEqual(result['status'], 'NO_VALID_OBSERVATIONS')
        self.assertEqual(result['reason'], 'no_depth_accepted_observations')
        self.assertEqual(result['timeline'], [])
        self.assertEqual(result['stages'][0]['exit_code'], 2)
        self.assertFalse((self.output/'replay').exists())

    def test_gpu_error_is_recorded_and_reraised(self):
        self.producer.side_effect = RuntimeError('Injected CUDA failure')
        with self.assertRaisesRegex(RuntimeError, 'Injected CUDA failure'):
            self.demo()
        result = json.loads((self.output/'demo.json').read_text())
        self.assertEqual((result['status'], result['active_stage']), ('INCOMPLETE', 'perception'))
        self.assertEqual(result['error']['type'], 'RuntimeError')
        self.assertFalse((self.output/'replay').exists())

    def test_wrong_map_identity_fails_before_perception(self):
        (self.mapping/'map.db').write_bytes(b'Incompatible map')
        with self.assertRaisesRegex(ValueError, 'map identity'):
            self.demo()
        self.producer.assert_not_called()
        result = json.loads((self.output/'demo.json').read_text())
        self.assertEqual(result['active_stage'], 'input_validation')
        self.assertEqual(result['stages'], [])

    def test_missing_local_weights_fail_before_perception(self):
        self.model.unlink()
        with self.assertRaises(FileNotFoundError):
            self.demo()
        self.producer.assert_not_called()
        self.assertEqual(json.loads((self.output/'demo.json').read_text())['status'], 'INCOMPLETE')

    def test_wrong_node_selection_or_manifest_in_producer_output_fails(self):
        original = copy.deepcopy(self.generated)
        for index, key, value in [(0, 'node_id', 99), (1, 'frames_manifest_sha256', 'f'*64)]:
            self.output = self.root/f'bad_{key}'
            self.generated = copy.deepcopy(original)
            self.generated['frames'][index][key] = value
            with self.assertRaisesRegex(ValueError, 'requested source/model identity or node selection'):
                self.demo()
            self.assertFalse((self.output/'replay').exists())

    def test_wrong_producer_model_identity_fails(self):
        self.generated['model_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'requested source/model identity'):
            self.demo()
        self.assertFalse((self.output/'replay').exists())

    def test_inconsistent_producer_exit_and_status_cannot_complete(self):
        self.code = 2
        with self.assertRaisesRegex(RuntimeError, 'supported completed outcome'):
            self.demo()
        self.assertEqual(json.loads((self.output/'demo.json').read_text())['status'], 'INCOMPLETE')

    def test_invalid_generated_timestamp_propagates_replay_failure(self):
        self.generated['frames'][1]['rgb_stamp_ns'] += 1
        with self.assertRaisesRegex(ValueError, 'source timestamps disagree'):
            self.demo()
        result = json.loads((self.output/'demo.json').read_text())
        self.assertEqual((result['status'], result['active_stage']), ('INCOMPLETE', 'replay'))
        child = json.loads((self.output/'replay/replay.json').read_text())
        self.assertEqual(child['status'], 'INCOMPLETE')
        self.assertEqual(child['steps'], [])

    def test_first_prefix_without_accepted_observations_is_not_skipped(self):
        first = self.generated['frames'][0]
        for d in first['detections']:
            d.pop('map_point_m')
            d['depth'] = {'status': 'REJECTED', 'reason': 'insufficient_valid_depth'}
        first['accepted_observations'] = 0
        self.generated.update(accepted_observations=1, rejected_detections=3)
        with self.assertRaisesRegex(ValueError, 'Report observation counts disagree'):
            self.demo()
        child = json.loads((self.output/'replay/replay.json').read_text())
        self.assertEqual(child['active_node'], 1)
        self.assertEqual(child['steps'][0]['status'], 'INCOMPLETE')

    def test_invalid_start_remains_completed_refusals(self):
        result = self.demo(start=[.15, 3.55])
        self.assertEqual(result['status'], 'DEMO_COMPLETE')
        self.assertEqual([s['search_status'] for s in result['timeline']], ['INVALID_START', 'NO_ROUTE'])

    def test_model_changed_during_work_prevents_final_success(self):
        from replay_observation_search import replay_search

        def changed(*args):
            result = replay_search(*args)
            self.model.write_bytes(b'Changed during demo')
            return result

        with patch('run_rgbd_search_demo.replay_search', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'manifest or model changed'):
                self.demo()
        result = json.loads((self.output/'demo.json').read_text())
        self.assertEqual((result['status'], result['active_stage']), ('INCOMPLETE', 'final_validation'))

    def test_output_reuse_preserves_all_evidence(self):
        self.demo()
        before = {p: file_hash(p) for p in self.output.rglob('*') if p.is_file()}
        self.producer.reset_mock()
        with self.assertRaises(FileExistsError):
            self.demo()
        self.producer.assert_not_called()
        self.assertEqual(before, {p: file_hash(p) for p in before})

    def test_nodes_and_finite_start_are_explicit(self):
        for nodes in ([], [1, 1]):
            with self.assertRaisesRegex(ValueError, 'each exactly once'):
                self.demo(nodes=nodes)
            self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            self.demo(start=[float('nan'), 1])
        self.assertFalse(self.output.exists())
        self.producer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
