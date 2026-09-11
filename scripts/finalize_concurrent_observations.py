"""Reproject verified concurrent camera observations into one final frozen map."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from extract_mapped_rgbd import file_hash
from observe_rgbd_objects import DEPTH_POLICY, INFERENCE, depth_observation, load_frame
from scene_memory import validate_report


def finalize(run, frames, output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'frames': [], 'excluded_nodes': [],
              'concurrent_run': str(run), 'frames_path': str(frames),
              'camera_frame': 'camera_color_optical_frame', 'map_frame': 'map', 'point_unit': 'meter',
              'inference_rerun': False, 'motion_executed': False,
              'representative_method': 'Original concurrent depth-filtered source pixels; no detection or depth-policy changes.',
              'limitation': 'Post-run reprojection with final optimized poses into a frozen map. Online poses and source evidence remain separate. No causal online memory, identity, physical accuracy or navigation acceptance.'}
    try:
        paths = [run/'run.json', run/'measurement.json', run/'verification.json', frames,
                 run/'map.db', run/'export/room_camera_poses.txt']
        before = {str(path): file_hash(path) for path in paths}
        measured = json.loads(paths[1].read_text())
        verified = json.loads(paths[2].read_text())
        manifest = json.loads(frames.read_text())
        if (measured['status'] != 'MEASURED' or verified['status'] != 'VERIFIED'
                or verified['measurement_sha256'] != before[str(paths[1])]
                or verified['run_sha256'] != before[str(paths[0])]):
            raise ValueError('Concurrent run does not match its verified measurement')
        if (manifest['status'] != 'VERIFIED' or Path(manifest['mapping_run']).resolve() != run.resolve()
                or manifest['reference_sha256'] != measured['reference_sha256']
                or manifest['database_sha256'] != before[str(paths[4])]
                or manifest['camera_poses_sha256'] != before[str(paths[5])]):
            raise ValueError('Extracted frames belong to a different or unverified mapping/source run')
        if measured['inference'] != INFERENCE or measured['depth_policy'] != DEPTH_POLICY:
            raise ValueError('Concurrent producer policy differs from the shared depth/inference baseline')
        perception = measured['perception']
        if (perception['depth_unit'], perception['invalid_depth'], perception['point_unit'],
                perception['map_frame'], perception['camera_frame']) != (
                'millimeter', 0, 'meter', 'map', 'camera_color_optical_frame'):
            raise ValueError('Concurrent observations have incompatible units or coordinate frames')
        model = Path(measured['model_path'])
        if file_hash(model) != measured['model_sha256']:
            raise ValueError('Original local model identity changed')
        before[str(model)] = measured['model_sha256']
        report.update({key: measured[key] for key in ('model_sha256', 'inference', 'depth_policy', 'runtime')})
        report['input_sha256'] = before
        rows = perception['frames']
        observations = {row['source_stamp_ns']: row for row in rows}
        if len(observations) != len(rows) or len({row['node_id'] for row in manifest['frames']}) != len(manifest['frames']):
            raise ValueError('Duplicate source timestamps or exported node IDs')
        validated = {(row['node_id'], row['stamp_ns']) for row in measured['mapping']['validated_map_observations']}
        for node in sorted(manifest['frames'], key=lambda row: row['source_stamp_ns']):
            source = observations.get(node['source_stamp_ns'])
            reason = None
            if source is None or source['status'] != 'PROCESSED':
                reason = 'no_processed_concurrent_observation'
            elif source['pose']['status'] != 'ACCEPTED':
                reason = 'online_pose_rejected: '+source['pose']['reason']
            elif (node['node_id'], node['source_stamp_ns']) not in validated:
                reason = 'no_validated_mapping_association'
            if reason:
                report['excluded_nodes'].append({'node_id': node['node_id'], 'source_stamp_ns': node['source_stamp_ns'], 'reason': reason})
                continue
            rgb, depth, k, transform, provenance = load_frame(frames, node['node_id'])
            if (source['rgb_pixels_sha256'] != hashlib.sha256(rgb.tobytes()).hexdigest()
                    or source['depth_pixels_sha256'] != hashlib.sha256(depth.tobytes()).hexdigest()
                    or any(source[key] != provenance[key] for key in
                           ('source_stamp_ns', 'rgb_stamp_ns', 'depth_stamp_ns', 'rgb_depth_skew_ns'))
                    or provenance['camera_info'] != perception['camera_info']['/camera/color/camera_info']):
                raise ValueError('Concurrent observation pixels, timestamps or calibration differ from the mapped source')
            frame = {**provenance, 'online_pose': copy.deepcopy(source['pose']),
                     'concurrent_measurement_sha256': before[str(paths[1])],
                     'online_result_completed_elapsed_s': source['completed_elapsed_s'],
                     'detections': copy.deepcopy(source['detections'])}
            for detection in frame['detections']:
                estimate = depth_observation(depth, k, detection['box_xyxy'])
                if estimate != detection['depth']:
                    raise ValueError('Concurrent depth evidence differs from the original source pixels/policy')
                if estimate['status'] == 'ACCEPTED':
                    camera = np.array(estimate['camera_point_m'])
                    detection['online_map_point_m'] = detection['map_point_m']
                    detection['map_point_m'] = (transform[:3, :3]@camera+transform[:3, 3]).tolist()
            frame['accepted_observations'] = sum(d['depth']['status'] == 'ACCEPTED' for d in frame['detections'])
            report['frames'].append(frame)
        report['accepted_observations'] = sum(frame['accepted_observations'] for frame in report['frames'])
        report['rejected_detections'] = sum(len(frame['detections'])-frame['accepted_observations'] for frame in report['frames'])
        if report['accepted_observations']:
            validate_report({**report, 'status': 'MEASURED'})
        if any(file_hash(Path(path)) != value for path, value in before.items()):
            raise ValueError('Source evidence changed during finalization')
        report['status'] = 'MEASURED' if report['accepted_observations'] else 'NO_VALID_OBSERVATIONS'
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'observations.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'frames', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    result = finalize(args.run.resolve(), args.frames.resolve(), args.output.resolve())
    print(json.dumps({'status': result['status'], 'selected_nodes': len(result['frames']),
                      'excluded_nodes': result['excluded_nodes'], 'accepted': result['accepted_observations'],
                      'rejected': result['rejected_detections'], 'duration_ms': result['duration_ms']}, indent=2))
    raise SystemExit(0 if result['status'] == 'MEASURED' else 2)
