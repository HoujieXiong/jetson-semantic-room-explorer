"""Exercise persistence, association and rollback using real temporary SQLite files."""

import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from scene_memory import import_report, query


def detection(index=0, point=(0, 0, 2), label='chair', confidence=0.9, box=(0, 0, 20, 20)):
    return {'detection_index': index, 'label': label, 'class_id': 0,
            'detection_confidence': confidence, 'box_xyxy': list(box), 'map_point_m': list(point),
            'depth': {'status': 'ACCEPTED', 'camera_point_m': list(point), 'depth_m': point[2],
                      'roi_pixels': 100, 'valid_pixels': 90, 'inlier_pixels': 80, 'valid_fraction': 0.9,
                      'pixel_uv': [10, 10], 'roi_xyxy_exclusive': [5, 5, 15, 15]}}


def frame(node=1, detections=None):
    stamp = 1_000_000_000+node*10_000_000
    detections = [detection()] if detections is None else detections
    messages = {}
    for stream, time_ns in [('color', stamp), ('depth', stamp-1_000_000)]:
        for kind in ('image_raw', 'camera_info'):
            messages[f'/camera/{stream}/{kind}'] = {'stamp_ns': time_ns, 'serialized_sha256': '9'*64}
    return {'node_id': node, 'source_stamp_ns': stamp, 'rgb_stamp_ns': stamp,
            'depth_stamp_ns': stamp-1_000_000, 'rgb_depth_skew_ns': 1_000_000,
            'database_sha256': 'a'*64, 'camera_poses_sha256': 'b'*64,
            'frame_sha256': f'{node:064x}', 'frames_manifest_sha256': 'c'*64,
            'source_messages': messages, 'pose_provenance': 'Synthetic identity pose',
            'camera_info': {'width': 20, 'height': 20, 'k': [100, 0, 10, 0, 100, 10, 0, 0, 1]},
            'map_from_camera': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            'detections': detections, 'accepted_observations': sum(d['depth']['status'] == 'ACCEPTED' for d in detections)}


def report(*frames):
    frames = list(frames) if frames else [frame()]
    accepted = sum(f['accepted_observations'] for f in frames)
    return {'status': 'MEASURED', 'camera_frame': 'camera_color_optical_frame', 'map_frame': 'map',
            'point_unit': 'meter', 'model_sha256': 'd'*64, 'inference': {'imgsz': 640, 'confidence_threshold': 0.25},
            'depth_policy': {'fixture': 'Already accepted synthetic surface samples'}, 'runtime': {'fixture': True},
            'representative_method': 'Synthetic source pixels', 'limitation': 'Synthetic association fixture',
            'frames': frames, 'accepted_observations': accepted,
            'rejected_detections': sum(len(f['detections']) for f in frames)-accepted}


class SceneMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name)/'memory.db'

    def sql(self, statement):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(statement).fetchall()

    def dump(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return '\n'.join(connection.iterdump())

    def test_reopen_metric_mean_source_times_and_separate_confidence(self):
        first, last = frame(), frame(2, [detection(point=(0.2, 0, 2), confidence=0.3)])
        import_report(self.database, report(first, last))
        result = query(self.database, 'find', ' CHAIR ')
        self.assertEqual(result['status'], 'FOUND')
        obj, = result['objects']
        self.assertEqual(obj['map_point_m'], [0.1, 0, 2])
        self.assertEqual(obj['support_count'], 2)
        self.assertEqual(obj['status'], 'PROVISIONAL')
        self.assertAlmostEqual(obj['mean_detection_confidence'], 0.6)
        self.assertEqual(obj['first_seen_ns'], first['source_stamp_ns'])
        self.assertEqual(obj['last_seen_ns'], last['source_stamp_ns'])
        self.assertEqual(obj['last_observation']['detection'], last['detections'][0])
        self.assertEqual(self.sql('PRAGMA integrity_check'), [('ok',)])
        self.assertEqual(self.sql('PRAGMA foreign_key_check'), [])

    def test_same_frame_overlap_preserved_without_extra_support(self):
        low = detection(1, (0.1, 0, 2), confidence=0.4, box=(2, 2, 18, 18))
        source = report(frame(detections=[low, detection()]))
        imported = import_report(self.database, source)
        self.assertEqual(imported['counts']['observations'], 2)
        self.assertEqual(imported['counts']['supporting_observations'], 1)
        self.assertEqual(query(self.database)['objects'][0]['map_point_m'], [0, 0, 2])
        self.assertEqual(self.sql("SELECT detection_index, object_id, representative_index FROM associations WHERE decision='same_frame_overlap'"), [(1, 1, 0)])
        retained = json.loads(self.sql('SELECT evidence_json FROM frames')[0][0])
        self.assertEqual(retained['detections'][1], low)

    def test_nonoverlapping_same_frame_neighbors_stay_separate(self):
        other = detection(1, (0.1, 0, 2), box=(30, 0, 50, 20))
        import_report(self.database, report(frame(detections=[detection(), other])))
        result = query(self.database, 'last_seen', 'chair')
        self.assertEqual(len(result['objects']), 2)  # Preserve tied latest candidates.
        self.assertEqual([o['support_count'] for o in result['objects']], [1, 1])

    def test_label_and_distance_gates(self):
        source = report(frame(), frame(2, [detection(label='bottle')]),
                        frame(3, [detection(point=(0.36, 0, 2))]))
        self.assertEqual(import_report(self.database, source)['counts']['objects'], 3)

    def test_nearest_match_and_gate_boundary(self):
        a, b = detection(), detection(1, (1, 0, 2), box=(30, 0, 50, 20))
        source = report(frame(detections=[a, b]), frame(2, [detection(point=(0.35, 0, 2))]),
                        frame(3, [detection(point=(0.9, 0, 2))]))
        import_report(self.database, source)
        self.assertEqual(self.sql("SELECT node_id, object_id FROM associations WHERE decision='nearest_match' ORDER BY node_id"), [(2, 1), (3, 2)])

    def test_depth_rejection_is_retained_without_object_position(self):
        rejected = detection(1)
        rejected.pop('map_point_m')
        rejected['depth'] = {'status': 'REJECTED', 'reason': 'insufficient_valid_depth', 'valid_pixels': 0}
        import_report(self.database, report(frame(detections=[detection(), rejected])))
        self.assertEqual(self.sql("SELECT object_id, distance_m FROM associations WHERE decision='depth_rejected'"), [(None, None)])
        self.assertEqual(query(self.database)['counts']['supporting_observations'], 1)

    def test_duplicate_and_timing_variant_imports_do_not_write_database(self):
        source = report(frame(), frame(2))
        import_report(self.database, source)
        before = self.database.read_bytes()
        duplicate = import_report(self.database, source)
        variant = copy.deepcopy(source)
        variant['duration_s'] = 999
        for f in variant['frames']:
            f.update(predict_wall_ms=500, processing_wall_ms=600, annotation='different.png', first_predict_call=False)
        repeated = import_report(self.database, variant)
        self.assertEqual(duplicate['added_frames'], 0)
        self.assertEqual(repeated['added_frames'], 0)
        self.assertEqual(repeated['counts']['observations'], 2)
        self.assertEqual(repeated['counts']['supporting_observations'], 2)
        self.assertEqual(self.database.read_bytes(), before)

    def test_batch_and_input_order_are_deterministic(self):
        a = frame(detections=[detection(1, (0.1, 0, 2)), detection()])
        b = frame(2, [detection(point=(0.2, 0, 2))])
        import_report(self.database, report(a, b))
        other = Path(self.temp.name)/'other.db'
        import_report(other, report(b))
        a['detections'].reverse()
        import_report(other, report(a))
        self.assertEqual(query(self.database), query(other))
        with closing(sqlite3.connect(other)) as connection:
            self.assertEqual(self.dump(), '\n'.join(connection.iterdump()))

    def test_incompatible_map_pose_model_or_policy_leaves_database_unchanged(self):
        import_report(self.database, report())
        before = self.database.read_bytes()
        for key in ('database_sha256', 'camera_poses_sha256', 'model_sha256', 'depth_policy'):
            with self.subTest(key=key):
                changed = report(frame(2))
                if key in changed['frames'][0]:
                    changed['frames'][0][key] = 'e'*64
                else:
                    changed[key] = {'changed': True} if key == 'depth_policy' else 'e'*64
                with self.assertRaisesRegex(ValueError, 'Incompatible'):
                    import_report(self.database, changed)
                self.assertEqual(self.database.read_bytes(), before)

    def test_conflicting_source_rolls_back_an_earlier_insert_in_same_import(self):
        import_report(self.database, report(frame(2)))
        before = self.dump()
        conflict = frame(2, [detection(label='bottle')])
        with self.assertRaisesRegex(ValueError, 'Conflicting source evidence'):
            import_report(self.database, report(frame(), conflict))
        self.assertEqual(self.dump(), before)
        self.assertEqual(query(self.database)['counts']['frames'], 1)

    def test_native_sql_failure_rolls_back_evidence_and_derived_objects(self):
        import_report(self.database, report())
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("CREATE TRIGGER reject_association BEFORE INSERT ON associations BEGIN SELECT RAISE(ABORT, 'injected write failure'); END")
        before = self.dump()
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'injected write failure'):
            import_report(self.database, report(frame(2)))
        self.assertEqual(self.dump(), before)

    def test_invalid_boundary_fails_before_database_creation(self):
        mutations = [
            lambda r: r.update(status='INCOMPLETE'),
            lambda r: r.update(point_unit='millimeter'),
            lambda r: r.update(accepted_observations=99),
            lambda r: r['frames'][0].update(rgb_stamp_ns=1),
            lambda r: r['frames'][0]['map_from_camera'][0].__setitem__(0, 2),
            lambda r: r['frames'][0]['detections'][0]['map_point_m'].__setitem__(0, float('nan')),
            lambda r: r['frames'][0]['detections'][0]['map_point_m'].__setitem__(0, 99),
            lambda r: r['frames'][0]['detections'].append(copy.deepcopy(r['frames'][0]['detections'][0])),
            lambda r: r['frames'][0]['detections'][0]['depth'].update(status='REJECTED', reason='invalid'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                source = report()
                mutate(source)
                with self.assertRaises(ValueError):
                    import_report(self.database, source)
                self.assertFalse(self.database.exists())

    def test_mixed_maps_or_duplicate_frames_in_report_are_rejected(self):
        for source in (report(frame(), frame()), report(frame(), frame(2))):
            if source['frames'][1]['node_id'] == 2:
                source['frames'][1]['database_sha256'] = 'e'*64
            with self.assertRaises(ValueError):
                import_report(self.database, source)
            self.assertFalse(self.database.exists())

    def test_last_seen_selects_latest_time_and_find_keeps_all_candidates(self):
        import_report(self.database, report(frame(), frame(2, [detection(point=(2, 0, 2))])))
        self.assertEqual(len(query(self.database, 'find', 'chair')['objects']), 2)
        last, = query(self.database, 'last_seen', 'chair')['objects']
        self.assertEqual(last['last_observation']['node_id'], 2)
        self.assertEqual(query(self.database, 'find', "chair' OR 1=1 --")['status'], 'NOT_FOUND')

    def test_read_only_query_does_not_create_missing_database(self):
        with self.assertRaises(sqlite3.OperationalError):
            query(self.database)
        self.assertFalse(self.database.exists())

    def test_foreign_schema_is_not_modified(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('CREATE TABLE unrelated (value TEXT)')
        before = self.database.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            import_report(self.database, report())
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            query(self.database)
        self.assertEqual(self.database.read_bytes(), before)

    def test_unknown_schema_version_is_explicitly_rejected(self):
        import_report(self.database, report())
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('PRAGMA user_version=99')
        before = self.database.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            import_report(self.database, report(frame(2)))
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            query(self.database)
        self.assertEqual(self.database.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
