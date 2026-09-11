"""Use real depth validation and SQLite with a controlled mapped-frame loading boundary."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from extract_mapped_rgbd import file_hash
from finalize_concurrent_observations import finalize
from observe_rgbd_objects import DEPTH_POLICY, INFERENCE, depth_observation
from scene_memory import import_report, query
from test_scene_memory import detection, frame


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root/'run'
        (self.run/'export').mkdir(parents=True)
        self.output = self.root/'output'
        self.frames = self.root/'frames.json'
        self.model = self.root/'local.pt'
        self.model.write_bytes(b'Synthetic local model identity; no inference')
        (self.run/'run.json').write_text('{"status":"MEASURED"}')
        (self.run/'map.db').write_bytes(b'Synthetic frozen map identity')
        (self.run/'export/room_camera_poses.txt').write_text('Synthetic final pose identity')
        self.rgb = np.ones((20, 20, 3), dtype=np.uint8)
        self.depth = np.full((20, 20), 2000, dtype=np.uint16)
        self.provenance = [frame(node) for node in (1, 2)]
        self.k = np.array(self.provenance[0]['camera_info']['k']).reshape(3, 3)
        self.manifest = {'status': 'VERIFIED', 'mapping_run': str(self.run), 'reference_sha256': 'e'*64,
                         'database_sha256': file_hash(self.run/'map.db'),
                         'camera_poses_sha256': file_hash(self.run/'export/room_camera_poses.txt'), 'frames': []}
        sources = []
        for index, original in enumerate(self.provenance):
            for key in ('database_sha256', 'camera_poses_sha256'):
                original[key] = self.manifest[key]
            original['map_from_camera'][0][3] = 10+index*.1
            sample = detection(point=(1, 0, 2))
            sample['depth'] = depth_observation(self.depth, self.k, sample['box_xyxy'])
            online = np.eye(4); online[0, 3] = 1
            sources.append({**{key: original[key] for key in ('source_stamp_ns', 'rgb_stamp_ns', 'depth_stamp_ns', 'rgb_depth_skew_ns')},
                            'status': 'PROCESSED', 'completed_elapsed_s': index+1.,
                            'pose': {'status': 'ACCEPTED', 'map_from_camera': online.tolist()},
                            'rgb_pixels_sha256': hashlib.sha256(self.rgb.tobytes()).hexdigest(),
                            'depth_pixels_sha256': hashlib.sha256(self.depth.tobytes()).hexdigest(),
                            'detections': [sample]})
            self.manifest['frames'].append({key: original[key] for key in ('node_id', 'source_stamp_ns')})
        rejected = detection(1, label='bottle', box=(21, 21, 25, 25))
        rejected.pop('map_point_m')
        rejected['depth'] = depth_observation(self.depth, self.k, rejected['box_xyxy'])
        sources[1]['detections'].append(rejected)
        self.measured = {'status': 'MEASURED', 'reference_sha256': 'e'*64, 'model_path': str(self.model),
                         'model_sha256': file_hash(self.model), 'inference': copy.deepcopy(INFERENCE),
                         'depth_policy': copy.deepcopy(DEPTH_POLICY), 'runtime': {'synthetic_fixture': True},
                         'mapping': {'validated_map_observations': [{'node_id': n, 'stamp_ns': self.provenance[n-1]['source_stamp_ns']} for n in (1, 2)]},
                         'perception': {'depth_unit': 'millimeter', 'invalid_depth': 0, 'point_unit': 'meter',
                            'camera_frame': 'camera_color_optical_frame', 'map_frame': 'map', 'frames': sources,
                            'camera_info': {'/camera/color/camera_info': self.provenance[0]['camera_info']}}}
        stub = patch('finalize_concurrent_observations.load_frame', side_effect=self.load)
        self.loader = stub.start(); self.addCleanup(stub.stop)
        self.save()

    def save(self):
        self.frames.write_text(json.dumps(self.manifest))
        (self.run/'measurement.json').write_text(json.dumps(self.measured))
        (self.run/'verification.json').write_text(json.dumps({'status': 'VERIFIED',
            'run_sha256': file_hash(self.run/'run.json'), 'measurement_sha256': file_hash(self.run/'measurement.json')}))

    def load(self, path, node):
        self.assertEqual(path, self.frames)
        provenance = copy.deepcopy(self.provenance[node-1])
        provenance['frames_manifest_sha256'] = file_hash(self.frames)
        provenance.pop('detections'); provenance.pop('accepted_observations')
        return self.rgb, self.depth, self.k, np.array(provenance['map_from_camera']), provenance

    def result(self):
        result = finalize(self.run, self.frames, self.output)
        self.assertEqual(json.loads((self.output/'observations.json').read_text()), result)
        self.assertFalse(result['inference_rerun'])
        return result

    def test_final_pose_reprojection_imports_and_reopens_without_losing_online_evidence(self):
        result = self.result()
        self.assertEqual((result['status'], result['accepted_observations'], result['rejected_detections']), ('MEASURED', 2, 1))
        first = result['frames'][0]['detections'][0]
        self.assertEqual(first['depth']['camera_point_m'], [0., 0., 2.])
        self.assertEqual(first['online_map_point_m'], [1, 0, 2])
        self.assertEqual(first['map_point_m'], [10., 0., 2.])
        self.assertEqual(result['frames'][1]['detections'][1], self.measured['perception']['frames'][1]['detections'][1])
        database = self.root/'memory.db'
        self.assertEqual(import_report(database, result)['added_frames'], 2)
        obj, = query(database, 'find', 'chair')['objects']
        self.assertAlmostEqual(obj['map_point_m'][0], 10.05)
        self.assertEqual(obj['support_count'], 2)
        before = file_hash(database)
        self.assertEqual(import_report(database, result)['added_frames'], 0)
        self.assertEqual(file_hash(database), before)

    def test_missing_dropped_and_pose_rejected_nodes_are_listed(self):
        for node in (3, 4, 5):
            row = {'node_id': node, 'source_stamp_ns': frame(node)['source_stamp_ns']}
            self.manifest['frames'].append(row)
            if node != 3:
                self.measured['perception']['frames'].append({'source_stamp_ns': row['source_stamp_ns'],
                    'status': 'DROPPED' if node == 4 else 'PROCESSED', 'pose': {'status': 'REJECTED', 'reason': 'tracking_lost'}})
        self.save(); result = self.result()
        self.assertEqual([r['node_id'] for r in result['frames']], [1, 2])
        self.assertEqual([r['node_id'] for r in result['excluded_nodes']], [3, 4, 5])
        self.assertEqual(result['excluded_nodes'][-1]['reason'], 'online_pose_rejected: tracking_lost')
        self.assertEqual(self.loader.call_count, 2)

    def test_all_pose_rejected_returns_explicit_no_valid_result(self):
        for row in self.measured['perception']['frames']:
            row['pose'] = {'status': 'REJECTED', 'reason': 'missing_source_map_tf'}
        self.save(); result = self.result()
        self.assertEqual(result['status'], 'NO_VALID_OBSERVATIONS')
        self.assertEqual(result['frames'], [])
        self.loader.assert_not_called()

    def test_modified_measurement_fails_its_verification_hash(self):
        (self.run/'measurement.json').write_text(json.dumps({**self.measured, 'changed': True}))
        with self.assertRaisesRegex(ValueError, 'verified measurement'): self.result()
        self.assertEqual(json.loads((self.output/'observations.json').read_text())['status'], 'INCOMPLETE')

    def test_pixels_and_timestamps_must_match_mapped_sources(self):
        for key, value in [('rgb_pixels_sha256', '0'*64), ('depth_stamp_ns', 123)]:
            with self.subTest(key=key):
                self.output = self.root/key
                saved = self.measured['perception']['frames'][0][key]
                self.measured['perception']['frames'][0][key] = value; self.save()
                with self.assertRaisesRegex(ValueError, 'pixels, timestamps or calibration'): self.result()
                self.measured['perception']['frames'][0][key] = saved

    def test_changed_depth_result_is_not_silently_corrected(self):
        self.measured['perception']['frames'][0]['detections'][0]['depth']['depth_m'] += 1
        self.save()
        with self.assertRaisesRegex(ValueError, 'depth evidence differs'): self.result()

    def test_wrong_mapping_or_reference_fails_before_loading_frames(self):
        self.manifest['reference_sha256'] = 'f'*64; self.save()
        with self.assertRaisesRegex(ValueError, 'different or unverified'): self.result()
        self.loader.assert_not_called()

    def test_changed_local_weights_fail_without_inference(self):
        self.model.write_bytes(b'Changed weights')
        with self.assertRaisesRegex(ValueError, 'model identity changed'): self.result()
        self.loader.assert_not_called()

    def test_changed_policy_and_units_fail(self):
        self.measured['depth_policy']['max_depth_m'] = 6; self.save()
        with self.assertRaisesRegex(ValueError, 'producer policy differs'): self.result()
        self.output = self.root/'bad_units'
        self.measured['depth_policy'] = copy.deepcopy(DEPTH_POLICY)
        self.measured['perception']['depth_unit'] = 'meter'; self.save()
        with self.assertRaisesRegex(ValueError, 'incompatible units'): self.result()

    def test_input_mutation_prevents_completed_report(self):
        def changed(path, node):
            result = self.load(path, node)
            if node == 2: self.model.write_bytes(b'Mutated during finalization')
            return result
        self.loader.side_effect = changed
        with self.assertRaisesRegex(ValueError, 'changed during finalization'): self.result()
        self.assertEqual(json.loads((self.output/'observations.json').read_text())['status'], 'INCOMPLETE')

    def test_duplicate_source_stamps_fail(self):
        self.measured['perception']['frames'].append(copy.deepcopy(self.measured['perception']['frames'][0]))
        self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate source timestamps'): self.result()

    def test_output_reuse_preserves_existing_evidence(self):
        self.result(); path = self.output/'observations.json'; before = file_hash(path)
        with self.assertRaises(FileExistsError): self.result()
        self.assertEqual(file_hash(path), before)


if __name__ == '__main__':
    unittest.main()
