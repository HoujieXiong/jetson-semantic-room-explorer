"""Persist measured M5 observations and query provisional objects in one frozen map."""

import argparse
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
import time

import numpy as np

from observe_rgbd_objects import source_association


SCHEMA_VERSION = 1
POLICY = {'distance_gate_m': 0.35, 'same_frame_overlap_min_area': 0.5,
          'position_update': 'Equal mean of one representative per source frame',
          'representative_order': 'Descending detector confidence, then detection index'}
SCHEMA = (
    'CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), context_json TEXT NOT NULL)',
    'CREATE TABLE frames (node_id INTEGER PRIMARY KEY, source_stamp_ns INTEGER UNIQUE NOT NULL, evidence_json TEXT NOT NULL)',
    '''CREATE TABLE objects (
        object_id INTEGER PRIMARY KEY, label TEXT NOT NULL, position_json TEXT NOT NULL,
        support_count INTEGER NOT NULL, first_seen_ns INTEGER NOT NULL, last_seen_ns INTEGER NOT NULL,
        confidence_sum REAL NOT NULL, last_node_id INTEGER NOT NULL REFERENCES frames(node_id),
        last_detection_index INTEGER NOT NULL)''',
    '''CREATE TABLE associations (
        node_id INTEGER NOT NULL REFERENCES frames(node_id), detection_index INTEGER NOT NULL,
        object_id INTEGER REFERENCES objects(object_id), decision TEXT NOT NULL,
        distance_m REAL, representative_index INTEGER, PRIMARY KEY(node_id, detection_index))''',
)
RUN_FIELDS = {'first_predict_call', 'predict_wall_ms', 'model_stage_ms', 'processing_wall_ms', 'annotation'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def require_hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Expected lowercase SHA256 provenance')


def validate_report(report):
    """Check the saved observation boundary; do not rerun the camera or detector."""
    canonical(report)  # Refuse non-finite numbers even in retained evidence.
    if (report['status'] != 'MEASURED' or report['map_frame'] != 'map'
            or report['camera_frame'] != 'camera_color_optical_frame' or report['point_unit'] != 'meter'
            or not report['frames']):
        raise ValueError('Expected a complete measured M5 report in metric camera/map frames')
    context = {key: report[key] for key in ('model_sha256', 'inference', 'depth_policy', 'runtime',
               'camera_frame', 'map_frame', 'point_unit', 'representative_method', 'limitation')}
    require_hash(context['model_sha256'])
    context.update(schema_version=SCHEMA_VERSION, association_policy=POLICY)
    frames, nodes, stamps = [], set(), set()
    accepted = rejected = 0
    for frame in report['frames']:
        node, stamp = frame['node_id'], frame['source_stamp_ns']
        if (type(node) is not int or type(stamp) is not int or not 0 < node < 2**63
                or not 0 < stamp < 2**63 or node in nodes or stamp in stamps):
            raise ValueError('Duplicate or invalid node/source timestamp')
        nodes.add(node)
        stamps.add(stamp)
        for key in ('database_sha256', 'camera_poses_sha256'):
            require_hash(frame[key])
            if key in context and context[key] != frame[key]:
                raise ValueError('Mixed frozen map/pose identities in one report')
            context[key] = frame[key]
        for key in ('frame_sha256', 'frames_manifest_sha256'):
            require_hash(frame[key])
        association = source_association({'messages': frame['source_messages'], 'source_stamp_ns': stamp})
        if any(frame[key] != value for key, value in association.items()):
            raise ValueError('Observation source timestamps disagree')
        for message in frame['source_messages'].values():
            require_hash(message['serialized_sha256'])
        if not frame['pose_provenance'] or not frame['camera_info']:
            raise ValueError('Missing pose/calibration evidence')
        transform = np.asarray(frame['map_from_camera'], dtype=float)
        if (transform.shape != (4, 4) or not np.array_equal(transform[3], [0, 0, 0, 1])
                or not np.allclose(transform[:3, :3].T@transform[:3, :3], np.eye(3), atol=1e-6, rtol=0)
                or not np.isclose(np.linalg.det(transform[:3, :3]), 1, atol=1e-6, rtol=0)):
            raise ValueError('Invalid map-from-camera rigid transform')
        indices, frame_accepted = set(), 0
        for detection in frame['detections']:
            index = detection['detection_index']
            if type(index) is not int or index < 0 or index in indices:
                raise ValueError('Duplicate or invalid detection index')
            indices.add(index)
            confidence = detection['detection_confidence']
            box = np.asarray(detection['box_xyxy'], dtype=float)
            if (not isinstance(detection['label'], str) or not detection['label'].strip()
                    or not 0 <= confidence <= 1 or box.shape != (4,) or np.any(box[2:] <= box[:2])):
                raise ValueError('Invalid detection label, confidence or box')
            depth = detection['depth']
            if depth['status'] == 'REJECTED':
                if not depth['reason'] or 'camera_point_m' in depth or 'map_point_m' in detection:
                    raise ValueError('Rejected depth must have a reason and no position')
                rejected += 1
            elif depth['status'] == 'ACCEPTED':
                camera, mapped = np.asarray(depth['camera_point_m']), np.asarray(detection['map_point_m'])
                if (camera.shape != (3,) or mapped.shape != (3,) or depth['depth_m'] <= 0
                        or camera[2] != depth['depth_m']
                        or not np.allclose((transform@[*camera, 1])[:3], mapped, atol=1e-6, rtol=0)
                        or not 0 < depth['inlier_pixels'] <= depth['valid_pixels'] <= depth['roi_pixels']
                        or not 0 < depth['valid_fraction'] <= 1):
                    raise ValueError('Invalid accepted depth/camera/map evidence')
                frame_accepted += 1
            else:
                raise ValueError('Unknown depth observation status')
        if frame_accepted != frame['accepted_observations']:
            raise ValueError('Frame observation count disagrees')
        accepted += frame_accepted
        normalized = {key: value for key, value in frame.items() if key not in RUN_FIELDS}
        normalized['detections'] = sorted(frame['detections'], key=lambda d: d['detection_index'])
        frames.append(normalized)
    if accepted != report['accepted_observations'] or rejected != report['rejected_detections'] or not accepted:
        raise ValueError('Report observation counts disagree')
    return context, sorted(frames, key=lambda f: (f['source_stamp_ns'], f['node_id']))


def overlap_min_area(a, b):
    width = max(0, min(a[2], b[2])-max(a[0], b[0]))
    height = max(0, min(a[3], b[3])-max(a[1], b[1]))
    return width*height/min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))


def rebuild_objects(connection):
    """Replay retained evidence in source order so import batch order cannot change the result."""
    connection.execute('DELETE FROM associations')
    connection.execute('DELETE FROM objects')
    objects, decisions = [], []
    for row in connection.execute('SELECT evidence_json FROM frames ORDER BY source_stamp_ns, node_id'):
        frame = json.loads(row[0])
        representatives, used = [], set()
        for detection in sorted(frame['detections'], key=lambda d: (-d['detection_confidence'], d['detection_index'])):
            node, index = frame['node_id'], detection['detection_index']
            if detection['depth']['status'] == 'REJECTED':
                decisions.append((node, index, None, 'depth_rejected', None, None))
                continue
            label, point = detection['label'].strip().casefold(), detection['map_point_m']
            duplicate = next(((previous, obj) for previous, obj in representatives
                if obj['label'] == label and math.dist(point, previous['map_point_m']) <= POLICY['distance_gate_m']
                and overlap_min_area(detection['box_xyxy'], previous['box_xyxy']) >= POLICY['same_frame_overlap_min_area']), None)
            if duplicate is not None:
                previous, obj = duplicate
                decisions.append((node, index, obj['id'], 'same_frame_overlap',
                                  math.dist(point, previous['map_point_m']), previous['detection_index']))
                continue
            candidates = [(math.dist(point, obj['point']), obj['id']) for obj in objects
                          if obj['label'] == label and obj['id'] not in used
                          and math.dist(point, obj['point']) <= POLICY['distance_gate_m']]
            if candidates:
                distance, object_id = min(candidates)
                obj = objects[object_id-1]
                n = obj['count']
                obj['point'] = [(a*n+b)/(n+1) for a, b in zip(obj['point'], point)]
                obj['count'] += 1
                decision = 'nearest_match'
            else:
                obj = {'id': len(objects)+1, 'label': label, 'point': list(point), 'count': 1,
                       'first': frame['source_stamp_ns'], 'confidence_sum': 0.0}
                objects.append(obj)
                distance, decision = None, 'new_object'
            obj.update(last=frame['source_stamp_ns'], last_node=node, last_index=index)
            obj['confidence_sum'] += detection['detection_confidence']
            used.add(obj['id'])
            representatives.append((detection, obj))
            decisions.append((node, index, obj['id'], decision, distance, None))
    connection.executemany('INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [(o['id'], o['label'], canonical(o['point']), o['count'], o['first'], o['last'],
          o['confidence_sum'], o['last_node'], o['last_index']) for o in objects])
    connection.executemany('INSERT INTO associations VALUES (?, ?, ?, ?, ?, ?)', decisions)


def check_schema(connection):
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if (tables != {'metadata', 'frames', 'objects', 'associations'}
            or connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION):
        raise ValueError('Unsupported scene-memory database schema; use a new database')


def summary(connection):
    decisions = dict(connection.execute('SELECT decision, count(*) FROM associations GROUP BY decision'))
    return {'frames': connection.execute('SELECT count(*) FROM frames').fetchone()[0],
            'observations': sum(decisions.values()), 'decisions': decisions,
            'objects': connection.execute('SELECT count(*) FROM objects').fetchone()[0],
            'supporting_observations': connection.execute('SELECT coalesce(sum(support_count), 0) FROM objects').fetchone()[0]}


def import_report(database, report):
    context, frames = validate_report(report)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=5)) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        with connection:
            connection.execute('BEGIN IMMEDIATE')
            if not connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                connection.execute('INSERT INTO metadata VALUES (1, ?)', (canonical(context),))
            check_schema(connection)
            stored_context = connection.execute('SELECT context_json FROM metadata WHERE id=1').fetchone()[0]
            if stored_context != canonical(context):
                raise ValueError('Incompatible map, pose, producer or association policy; use a separate database')
            added = 0
            for frame in frames:
                existing = connection.execute('SELECT evidence_json FROM frames WHERE node_id=? OR source_stamp_ns=?',
                    (frame['node_id'], frame['source_stamp_ns'])).fetchall()
                payload = canonical(frame)
                if existing:
                    if len(existing) != 1 or existing[0][0] != payload:
                        raise ValueError(f'Conflicting source evidence for node {frame["node_id"]}; import rolled back')
                    continue
                connection.execute('INSERT INTO frames VALUES (?, ?, ?)', (frame['node_id'], frame['source_stamp_ns'], payload))
                added += 1
            if added:
                rebuild_objects(connection)
            result = {'status': 'IMPORTED', 'added_frames': added, 'existing_frames': len(frames)-added,
                      'counts': summary(connection)}
        return result


def query(database, command='list', label=None):
    """Read-only queries must not create a missing database or hide same-label candidates."""
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('BEGIN')  # Keep counts, objects and evidence in one read snapshot.
        check_schema(connection)
        context = json.loads(connection.execute('SELECT context_json FROM metadata WHERE id=1').fetchone()[0])
        sql, parameters = 'SELECT * FROM objects', ()
        if command in ('find', 'last_seen'):
            sql += ' WHERE label=?'
            parameters = (label.strip().casefold(),)
        elif command != 'list':
            raise ValueError('Unknown query')
        rows = connection.execute(sql+' ORDER BY last_seen_ns DESC, object_id', parameters).fetchall()
        if command == 'last_seen' and rows:
            rows = [row for row in rows if row['last_seen_ns'] == rows[0]['last_seen_ns']]
        objects = []
        for row in rows:
            frame = json.loads(connection.execute('SELECT evidence_json FROM frames WHERE node_id=?', (row['last_node_id'],)).fetchone()[0])
            detection = next(d for d in frame['detections'] if d['detection_index'] == row['last_detection_index'])
            objects.append({'object_id': row['object_id'], 'label': row['label'], 'status': 'PROVISIONAL',
                'map_point_m': json.loads(row['position_json']), 'support_count': row['support_count'],
                'first_seen_ns': row['first_seen_ns'], 'last_seen_ns': row['last_seen_ns'],
                'mean_detection_confidence': row['confidence_sum']/row['support_count'],
                'last_observation': {'node_id': row['last_node_id'], 'source_stamp_ns': frame['source_stamp_ns'],
                                     'detection': detection}})
        return {'status': 'FOUND' if objects else 'NOT_FOUND', 'query': command, 'label': label,
                'context': context, 'counts': summary(connection), 'objects': objects,
                'limitation': 'Provisional label/distance association of surface samples; identity and physical accuracy unverified. IDs may change if older evidence is added.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('import').add_argument('observations', type=Path)
    commands.add_parser('list')
    for name in ('find', 'last_seen'):
        commands.add_parser(name).add_argument('label')
    args = parser.parse_args()
    begin = time.monotonic()
    if args.command == 'import':
        result = import_report(args.db, json.loads(args.observations.read_text()))
    else:
        result = query(args.db, args.command, getattr(args, 'label', None))
    result.update(operation_ms=(time.monotonic()-begin)*1000, sqlite_version=sqlite3.sqlite_version)
    print(json.dumps(result, indent=2, allow_nan=False))
