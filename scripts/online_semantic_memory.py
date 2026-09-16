"""Encode delivered keyframes and rank text against one causal memory snapshot."""

import argparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import time

import numpy as np

from extract_mapped_rgbd import file_hash
from rgbd_geometry import match_source_stamp
from scene_memory import require_hash
from semantic_memory import (MobileClipEncoder, SELECTION_POLICY, crop_rgb, rank_objects,
                             select_candidates, unit_vector, write_query_review)


POLICY = {'rgb_cache_frames': 32, 'pending_keyframes': 8, 'workers': 1,
          'source_wait_s': 5., 'max_crops_per_keyframe': 16,
          'selection': 'Received mapped keyframes with originally accepted poses; depth-accepted proposals in confidence order',
          'fusion': 'Only currently associated geometric representatives with committed vectors; report missing supports'}


def encode_keyframe(encoder, row, rgb, node, crops, elapsed):
    from PIL import Image
    started = elapsed()
    if hashlib.sha256(rgb.tobytes()).hexdigest() != row['rgb_pixels_sha256']:
        raise ValueError('Cached RGB pixels differ from the original observation')
    detections = sorted((d for d in row['detections'] if d['depth']['status'] == 'ACCEPTED'),
                        key=lambda d: (-d['detection_confidence'], d['detection_index']))
    samples = []
    for detection in detections[:POLICY['max_crops_per_keyframe']]:
        index = detection['detection_index']
        crop, bounds = crop_rgb(rgb, detection['box_xyxy'])
        path = crops/f'{node}_{index}.png'
        with path.open('xb') as stream:
            Image.fromarray(crop).save(stream, format='PNG')
        vector, duration = encoder.encode(crop, image=True)
        samples.append({'node_id': node, 'detection_index': index,
            'source_stamp_ns': row['source_stamp_ns'], 'box_xyxy_exclusive': bounds,
            'crop': str(Path(crops.name)/path.name), 'crop_sha256': file_hash(path),
            'rgb_pixels_sha256': hashlib.sha256(crop.tobytes()).hexdigest(),
            'encode_ms': duration, 'vector': unit_vector(vector).tolist()})
    return {'status': 'ENCODED', 'node_id': node, 'source_stamp_ns': row['source_stamp_ns'],
            'source_rgb_pixels_sha256': row['rgb_pixels_sha256'], 'samples': samples,
            'skipped_detections': [{'detection_index': d['detection_index'], 'reason': 'crop_budget'}
                                   for d in detections[POLICY['max_crops_per_keyframe']:]],
            'started_elapsed_s': started, 'completed_elapsed_s': elapsed()}


class OnlineSemanticCapture:
    """A bounded RGB cache and one encoder worker; caller owns all journal writes."""
    def __init__(self, encoder, memory, crops, elapsed):
        self.encoder, self.memory, self.crops, self.elapsed = encoder, memory, Path(crops), elapsed
        self.crops.mkdir(exist_ok=False)
        self.images, self.pending = OrderedDict(), OrderedDict()
        self.active = None
        self.closed = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mobileclip_keyframe')
        self.stats = {'cache_peak': 0, 'cache_evictions': 0, 'pending_peak': 0,
                      'encoded_keyframes': 0, 'encoded_crops': 0, 'rejections': {}, 'encode_ms': []}

    def remember(self, row, rgb):
        self.images[row['source_stamp_ns']] = rgb
        while len(self.images) > POLICY['rgb_cache_frames']:
            self.images.popitem(last=False)
            self.stats['cache_evictions'] += 1
        self.stats['cache_peak'] = max(self.stats['cache_peak'], len(self.images))

    def reject(self, request, reason, stamp=None):
        self.memory.submit('semantic', {'status': 'REJECTED', 'node_id': request['node_id'],
            'source_stamp_ns': stamp, 'requested_elapsed_s': request['requested_elapsed_s'],
            'reason': reason}, self.elapsed())
        self.stats['rejections'][reason] = self.stats['rejections'].get(reason, 0)+1

    def request(self, mapping):
        request = {**mapping, 'requested_elapsed_s': self.elapsed()}
        if len(self.pending) >= POLICY['pending_keyframes']:
            self.reject(request, 'semantic_queue_full')
            return
        self.pending[mapping['node_id']] = request
        self.stats['pending_peak'] = max(self.stats['pending_peak'], len(self.pending))

    def collect(self):
        request, future = self.active
        result = future.result(timeout=5)
        result['requested_elapsed_s'] = request['requested_elapsed_s']
        self.memory.submit('semantic', result, self.elapsed())
        self.stats['encoded_keyframes'] += 1
        self.stats['encoded_crops'] += len(result['samples'])
        self.stats['encode_ms'].extend(s['encode_ms'] for s in result['samples'])
        self.active = None

    def pump(self, rows):
        if self.active is not None and self.active[1].done():
            self.collect()
        sources = {r['source_stamp_ns']: r for r in rows}
        stamps = sorted(sources)
        for node, request in list(self.pending.items()):
            row = None
            reason = None
            try:
                stamp = match_source_stamp(request['stamp_ns'], stamps)
                row = sources[stamp]
            except ValueError:
                reason = 'source_not_received'
            if row is not None:
                if row['status'] == 'DROPPED':
                    reason = 'source_observation_dropped'
                elif row['status'] != 'PROCESSED':
                    reason = 'source_not_finalized'
                elif row['pose']['status'] != 'ACCEPTED':
                    reason = 'source_pose_rejected'
                elif stamp not in self.images:
                    reason = 'source_rgb_evicted'
            if reason in ('source_not_received', 'source_not_finalized'):
                if self.elapsed()-request['requested_elapsed_s'] < POLICY['source_wait_s']:
                    continue
            if reason:
                self.reject(request, reason, row['source_stamp_ns'] if row else None)
                del self.pending[node]
            elif self.active is None:
                self.active = (request, self.executor.submit(encode_keyframe, self.encoder,
                    copy.deepcopy(row), self.images[stamp], node, self.crops, self.elapsed))
                del self.pending[node]

    def close(self):
        if self.closed:
            return
        try:
            if self.active is not None:
                self.collect()
            for request in self.pending.values():
                self.reject(request, 'shutdown_before_encoding')
        finally:
            self.closed = True
            self.pending.clear()
            self.images.clear()
            # A running CUDA failure remains an error; the outer process supervisor
            # enforces the exit deadline if a worker cannot finish.
            self.executor.shutdown(wait=self.active is None, cancel_futures=True)


def validate_semantic(connection, context, payload, elapsed):
    if context.get('semantic_policy') != POLICY or 'semantic_encoder' not in context:
        raise ValueError('Semantic events require the declared encoder and capture policy')
    mapping = connection.execute('SELECT available_elapsed_s,payload_json FROM events WHERE kind="mapping" AND '
        'json_extract(payload_json,"$.node_id")=?', (payload['node_id'],)).fetchone()
    if mapping is None or not mapping[0] <= payload['requested_elapsed_s'] <= elapsed:
        raise ValueError('Semantic result lacks an already committed mapping request')
    if payload['status'] == 'REJECTED':
        if not payload['reason']:
            raise ValueError('Semantic rejection needs a reason')
        return
    if payload['status'] != 'ENCODED':
        raise ValueError('Unknown semantic outcome')
    stamp = payload['source_stamp_ns']
    match_source_stamp(json.loads(mapping[1])['stamp_ns'], [stamp])
    original = connection.execute('SELECT available_elapsed_s,payload_json FROM events WHERE kind="observation" AND '
        'json_extract(payload_json,"$.source_stamp_ns")=?', (stamp,)).fetchone()
    if original is None:
        raise ValueError('Semantic result precedes its source observation')
    row = json.loads(original[1])
    if row['status'] != 'PROCESSED' or row['pose']['status'] != 'ACCEPTED':
        raise ValueError('Semantic source pose was not accepted')
    if (not max(row['completed_elapsed_s'], original[0]) <= payload['started_elapsed_s'] <= payload['completed_elapsed_s'] <= elapsed
            or payload['requested_elapsed_s'] > payload['started_elapsed_s']
            or payload['source_rgb_pixels_sha256'] != row['rgb_pixels_sha256']):
        raise ValueError('Semantic availability or source pixels disagree')
    detections = {d['detection_index']: d for d in row['detections'] if d['depth']['status'] == 'ACCEPTED'}
    seen = set()
    if len(payload['samples']) > POLICY['max_crops_per_keyframe']:
        raise ValueError('Semantic crop budget exceeded')
    for sample in payload['samples']:
        index = sample['detection_index']
        if (index not in detections or index in seen or sample['source_stamp_ns'] != stamp
                or sample['node_id'] != payload['node_id']):
            raise ValueError('Semantic crop has conflicting source identity')
        seen.add(index)
        vector = np.asarray(sample['vector'], dtype=np.float32)
        unit_vector(vector)
        if not np.isclose(np.linalg.norm(vector), 1., atol=1e-5, rtol=0):
            raise ValueError('Stored semantic vector must be unit length')
        for key in ('crop_sha256', 'rgb_pixels_sha256'):
            require_hash(sample[key])
        if not np.isfinite(sample['encode_ms']) or sample['encode_ms'] < 0:
            raise ValueError('Invalid semantic encoding time')
        info = row['camera_info']
        clipped = np.clip(detections[index]['box_xyxy'], [0]*4,
                          [info['width'], info['height']]*2)
        bounds = np.r_[np.floor(clipped[:2]), np.ceil(clipped[2:])].astype(int).tolist()
        if sample['box_xyxy_exclusive'] != bounds or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise ValueError('Semantic crop bounds differ from original detection')
        path = Path(sample['crop'])
        if path.is_absolute() or '..' in path.parts or len(path.parts) != 2:
            raise ValueError('Semantic crop must be local to the journal directory')
    for skipped in payload['skipped_detections']:
        index = skipped['detection_index']
        if index not in detections or index in seen or skipped['reason'] != 'crop_budget':
            raise ValueError('Invalid semantic crop omission')
        seen.add(index)
    if seen != set(detections):
        raise ValueError('Semantic result silently omits a source detection')


def rank_snapshot(connection, context, events, remembered, text_vector, encoder_identity):
    if context.get('semantic_encoder') != encoder_identity or context.get('semantic_policy') != POLICY:
        raise ValueError('Online image/text encoder or policy mismatch')
    outcomes = {p['node_id']: (seq, p) for seq, p in events}
    samples, groups, missing = [], {}, []
    for node, index, oid in connection.execute('SELECT node_id,detection_index,object_id FROM associations '
            'WHERE decision IN ("new_object","nearest_match") ORDER BY node_id,detection_index'):
        seq, event = outcomes.get(node, (None, None))
        sample = next((s for s in event['samples'] if s['detection_index'] == index), None) if event and event['status'] == 'ENCODED' else None
        if sample is None:
            reason = 'embedding_not_committed' if event is None else event.get('reason', 'crop_budget')
            missing.append({'node_id': node, 'detection_index': index, 'object_id': oid, 'reason': reason})
            continue
        vector = unit_vector(sample['vector'])
        evidence = {**{k: v for k, v in sample.items() if k != 'vector'}, 'semantic_event_seq': seq}
        samples.append((oid, evidence, vector))
        groups.setdefault(oid, []).append(vector)
    objects = []
    for obj in remembered['objects']:
        if obj['object_id'] not in groups:
            continue
        vectors = groups[obj['object_id']]
        mean = np.mean(vectors, axis=0)
        objects.append(({**obj, 'semantic_support_count': len(vectors)}, unit_vector(mean), float(np.linalg.norm(mean))))
    ranking = rank_objects(text_vector, objects, samples)
    ids = select_candidates(ranking)
    return {'status': 'CANDIDATES_SELECTED' if ids else 'NO_CANDIDATE_ABOVE_THRESHOLD' if ranking else 'NO_SEMANTIC_SUPPORT',
            'ranking': ranking, 'selected_object_ids': ids, 'selection_policy': SELECTION_POLICY,
            'missing_supports': missing, 'available_supports': len(samples),
            'semantic_event_count': len(events)}


def query_text(database, model, phrase, output, *, planning=False):
    from online_scene_memory import query_online
    if not phrase.strip():
        raise ValueError('Provide a nonempty text phrase')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'text': phrase}
    encoder = None
    try:
        encoder = MobileClipEncoder(model)
        vector, elapsed_ms = encoder.encode(phrase)
        result = query_online(database, text_vector=vector, encoder_identity=encoder.identity, planning=planning)
        report.update(result, text=phrase, text_vector=vector.tolist(), text_encode_ms=elapsed_ms,
                      encoder=encoder.identity, load_ms=encoder.load_ms)
        report['status'] = result['semantic']['status']
        report['limitation'] = 'Ranks only committed crops of current geometric supports. Partial coverage and uncalibrated cosine scores do not prove identity or presence/absence. No navigation decision.'
        write_query_review([{'text': phrase, 'ranking': result['semantic']['ranking']}],
                           database.parent, output/'queries.html', report['limitation'])
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as error:
        report.update(status='INCOMPLETE', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        report['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if encoder is not None:
            report['peak_cuda_allocated_bytes'] = encoder.torch.cuda.max_memory_allocated()
        (output/'query.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('db', 'model', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--text', required=True)
    args = parser.parse_args()
    result = query_text(args.db.resolve(), args.model.resolve(), args.text, args.output.resolve())
    print(json.dumps({'status': result['status'], 'snapshot': result.get('snapshot'), 'output': str(args.output)}))
