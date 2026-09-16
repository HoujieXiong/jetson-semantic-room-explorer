"""Measure YOLO detections as source-associated optical-camera/map surface points."""

import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from extract_mapped_rgbd import file_hash
from rgbd_geometry import map_from_camera, pinhole_matrix


INFERENCE = {'imgsz': 640, 'confidence_threshold': 0.25, 'device': 'cuda:0'}


DEPTH_POLICY = {'inner_box_fraction': 0.5, 'max_depth_m': 5.0,
                'min_valid_pixels': 20, 'min_valid_fraction': 0.25,
                'mad_multiplier': 3.0, 'mad_sigma_factor': 1.4826,
                'min_outlier_gate_m': 0.02, 'max_inlier_p90_p10_m': 0.5}


def inference_config(imgsz=INFERENCE['imgsz']):
    """Explicit measured detector sizes; confidence and device stay fixed."""
    if type(imgsz) is not int or imgsz not in (640, 1280):
        raise ValueError('Detector imgsz must be 640 or 1280')
    return {**INFERENCE, 'imgsz': imgsz}


def depth_observation(depth_mm, k, box):
    """Choose an actual inner-ROI pixel near median depth, keeping rejection evidence."""
    k = pinhole_matrix(k)
    if depth_mm.ndim != 2 or depth_mm.dtype != np.uint16:
        raise ValueError('Expected raw uint16 millimeter depth')
    box = np.asarray(box, dtype=float)
    if box.shape != (4,) or not np.isfinite(box).all() or np.any(box[2:] <= box[:2]):
        raise ValueError('Invalid detection box')
    height, width = depth_mm.shape
    box = np.clip(box, [0, 0, 0, 0], [width, height, width, height])
    center = (box[:2]+box[2:])/2
    half = (box[2:]-box[:2])*DEPTH_POLICY['inner_box_fraction']/2
    x0, y0 = np.ceil(center-half).astype(int)
    x1, y1 = np.ceil(center+half).astype(int)
    result = {'status': 'REJECTED', 'roi_xyxy_exclusive': [int(v) for v in (x0, y0, x1, y1)]}
    roi = depth_mm[y0:y1, x0:x1]
    result['roi_pixels'] = int(roi.size)
    if not roi.size:
        return {**result, 'reason': 'empty_inner_roi'}
    valid = (roi > 0) & (roi < DEPTH_POLICY['max_depth_m']*1000)
    ys, xs = np.nonzero(valid)
    depths = roi[valid].astype(float)/1000
    result.update(valid_pixels=len(depths), valid_fraction=len(depths)/roi.size,
                  invalid_zero_pixels=int(np.count_nonzero(roi == 0)),
                  out_of_range_pixels=int(np.count_nonzero(roi >= DEPTH_POLICY['max_depth_m']*1000)))
    if len(depths) < DEPTH_POLICY['min_valid_pixels'] or result['valid_fraction'] < DEPTH_POLICY['min_valid_fraction']:
        return {**result, 'reason': 'insufficient_valid_depth'}
    median = float(np.median(depths))
    mad = float(np.median(np.abs(depths-median)))
    gate = max(DEPTH_POLICY['min_outlier_gate_m'], DEPTH_POLICY['mad_multiplier']*DEPTH_POLICY['mad_sigma_factor']*mad)
    inliers = np.abs(depths-median) <= gate
    depths, xs, ys = depths[inliers], xs[inliers], ys[inliers]
    result.update(initial_median_m=median, mad_m=mad, outlier_gate_m=gate,
                  inlier_pixels=len(depths), rejected_outlier_pixels=int(np.count_nonzero(~inliers)))
    if len(depths) < DEPTH_POLICY['min_valid_pixels']:
        return {**result, 'reason': 'insufficient_depth_inliers'}
    p10, median, p90 = np.percentile(depths, [10, 50, 90])
    result.update(inlier_depth_p10_m=float(p10), inlier_median_m=float(median), inlier_depth_p90_m=float(p90))
    if p90-p10 > DEPTH_POLICY['max_inlier_p90_p10_m']:
        return {**result, 'reason': 'depth_spread_too_large'}
    u, v = xs+x0, ys+y0
    order = np.lexsort(((u-center[0])**2+(v-center[1])**2, np.abs(depths-median)))
    index = order[0]
    u, v, z = int(u[index]), int(v[index]), float(depths[index])
    point = [(u-k[0, 2])*z/k[0, 0], (v-k[1, 2])*z/k[1, 1], z]
    return {**result, 'status': 'ACCEPTED', 'pixel_uv': [u, v], 'depth_m': z,
            'camera_point_m': [float(value) for value in point]}


def source_association(row):
    """Recover both sensor stamps and require their measured aggregate timestamp."""
    stamps = {}
    for stream in ('color', 'depth'):
        image = row['messages'][f'/camera/{stream}/image_raw']['stamp_ns']
        info = row['messages'][f'/camera/{stream}/camera_info']['stamp_ns']
        if not isinstance(image, int) or image <= 0 or image != info:
            raise ValueError('Image and CameraInfo source timestamps differ or are invalid')
        stamps[stream] = image
    if max(stamps.values()) != row['source_stamp_ns'] or abs(stamps['color']-stamps['depth']) > 5_000_000:
        raise ValueError('RGB-D pair does not match the mapped source timestamp')
    return {'source_stamp_ns': row['source_stamp_ns'], 'rgb_stamp_ns': stamps['color'],
            'depth_stamp_ns': stamps['depth'], 'rgb_depth_skew_ns': stamps['color']-stamps['depth']}


def load_frame(manifest_path, node_id):
    manifest = json.loads(manifest_path.read_text())
    if (manifest['status'] != 'VERIFIED' or manifest['depth_unit'] != 'millimeter'
            or manifest['invalid_depth'] != 0 or manifest['pose_frame'] != 'map -> camera_color_optical_frame'):
        raise ValueError('Use verified metric RGB-D with map-from-optical-camera poses')
    matching = [row for row in manifest['frames'] if row['node_id'] == node_id]
    if len(matching) != 1:
        raise ValueError(f'Expected one mapped frame for node {node_id}')
    row = matching[0]
    association = source_association(row)
    mapping = Path(manifest['mapping_run'])
    if file_hash(mapping/'map.db') != manifest['database_sha256']:
        raise ValueError('Frozen map database changed')
    pose_path = mapping/'export/room_camera_poses.txt'
    if file_hash(pose_path) != manifest['camera_poses_sha256']:
        raise ValueError('Frozen camera-pose export changed')
    poses = np.loadtxt(pose_path, ndmin=2)
    selected = poses[poses[:, 8] == node_id]
    if len(selected) != 1 or not np.array_equal(selected[0, 1:8], row['position_m']+row['quaternion_xyzw']):
        raise ValueError('Node camera pose differs from its frozen export')
    measurement = json.loads((mapping/'measurement.json').read_text())
    valid = measurement['mapping']['validated_map_observations']
    if measurement['status'] != 'MEASURED' or not any(r['node_id'] == node_id and r['stamp_ns'] == row['source_stamp_ns'] for r in valid):
        raise ValueError('Node lacks validated source-time map association')
    calibration = manifest['camera_info']
    k = pinhole_matrix(calibration['k'])
    p = np.asarray(calibration['p']).reshape(3, 4)
    if (any(calibration['d']) or not np.array_equal(np.reshape(calibration['r'], (3, 3)), np.eye(3))
            or not np.array_equal(p[:, :3], k) or np.any(p[:, 3])):
        raise ValueError('Expected rectified pinhole calibration')
    frame_path = manifest_path.parent/row['file']
    if file_hash(frame_path) != row['file_sha256']:
        raise ValueError('Extracted RGB-D frame changed')
    with np.load(frame_path, allow_pickle=False) as data:
        rgb, depth = data['rgb'], data['depth_mm']
    if (rgb.shape != (calibration['height'], calibration['width'], 3) or rgb.dtype != np.uint8
            or depth.shape != rgb.shape[:2] or depth.dtype != np.uint16):
        raise ValueError('Expected same-grid RGB8 and uint16 depth')
    transform = map_from_camera(row['position_m'], row['quaternion_xyzw'])
    provenance = {**association, 'node_id': node_id, 'frame_sha256': row['file_sha256'],
                  'frames_manifest_sha256': file_hash(manifest_path), 'database_sha256': manifest['database_sha256'],
                  'camera_poses_sha256': manifest['camera_poses_sha256'], 'pose_provenance': manifest['pose_provenance'],
                  'map_from_camera': transform.tolist(), 'camera_info': calibration,
                  'source_messages': row['messages']}
    return rgb, depth, k, transform, provenance


def infer_rgbd(model, rgb, depth, k, transform=None, *, imgsz=INFERENCE['imgsz']):
    """GPU inference and depth localization; an absent online pose leaves map points absent."""
    import cv2
    import torch

    begin = time.monotonic()
    inference = inference_config(imgsz)
    # Ultralytics numpy inputs use OpenCV BGR; source NPZ arrays preserve RGB.
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    result = model.predict(source=bgr, imgsz=inference['imgsz'], conf=inference['confidence_threshold'],
                           device=inference['device'], save=False, verbose=False)[0]
    torch.cuda.synchronize()
    prediction_ms = (time.monotonic()-begin)*1000
    frame = {'predict_wall_ms': prediction_ms, 'model_stage_ms': result.speed, 'detections': []}
    boxes = result.boxes
    if boxes is not None:
        for detection_id, box in enumerate(boxes):
            xyxy = box.xyxy[0].cpu().tolist()
            cls, confidence = int(box.cls.item()), float(box.conf.item())
            if not np.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError('Invalid detector confidence')
            estimate = depth_observation(depth, k, xyxy)
            detection = {'detection_index': detection_id, 'class_id': cls, 'label': result.names[cls],
                         'detection_confidence': confidence, 'box_xyxy': xyxy, 'depth': estimate}
            if estimate['status'] == 'ACCEPTED' and transform is not None:
                camera = np.array(estimate['camera_point_m'])
                detection['map_point_m'] = (transform[:3, :3]@camera+transform[:3, 3]).tolist()
            frame['detections'].append(detection)
    frame['inference_depth_wall_ms'] = (time.monotonic()-begin)*1000
    return frame


def observe(args):
    # Resolve local artifacts before loading a library that accepts model URLs/names.
    model_path = args.model.resolve(strict=True)
    if not model_path.is_file():
        raise ValueError('Expected local YOLO weights')
    samples = [load_frame(args.frames.resolve(), node) for node in args.nodes]
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'model_path': str(model_path), 'model_sha256': file_hash(model_path),
              'inference': INFERENCE,
              'depth_policy': DEPTH_POLICY, 'camera_frame': 'camera_color_optical_frame', 'map_frame': 'map',
              'point_unit': 'meter', 'frames': [],
              'representative_method': 'Actual inner-ROI pixel closest to inlier median depth; ties nearest box center.',
              'limitation': 'Detection-associated visible surface point, not object center or segmentation. Confidence is detector confidence only. Fixed map accuracy and live performance are unverified.'}
    started = time.monotonic()
    try:
        os.environ['YOLO_OFFLINE'] = 'true'
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        import cv2
        import torch
        import ultralytics
        from ultralytics import YOLO
        if not torch.cuda.is_available():
            raise RuntimeError('Jetson CUDA is unavailable; CPU inference is not this measurement')
        report['runtime'] = {'torch': torch.__version__, 'ultralytics': ultralytics.__version__,
                             'opencv': cv2.__version__, 'device': torch.cuda.get_device_name(0)}
        model = YOLO(str(model_path))
        for index, (rgb, depth, k, transform, provenance) in enumerate(samples):
            begin = time.monotonic()
            frame = {**provenance, 'first_predict_call': index == 0,
                     **infer_rgbd(model, rgb, depth, k, transform)}
            frame.pop('inference_depth_wall_ms')
            canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            for detection in frame['detections']:
                detection_id, xyxy = detection['detection_index'], detection['box_xyxy']
                estimate, confidence = detection['depth'], detection['detection_confidence']
                color = (80, 220, 80) if estimate['status'] == 'ACCEPTED' else (70, 70, 230)
                x0, y0, x1, y1 = [int(v) for v in xyxy]
                cv2.rectangle(canvas, (x0, y0), (x1, y1), color, 2)
                label = f'{detection_id}: {detection["label"]} {confidence:.2f}'
                label += f' z={estimate["depth_m"]:.2f}m' if estimate['status'] == 'ACCEPTED' else ' depth rejected'
                cv2.putText(canvas, label, (max(0, x0), max(18, y0-6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
                a, b, c, d = estimate['roi_xyxy_exclusive']
                cv2.rectangle(canvas, (a, b), (max(a, c-1), max(b, d-1)), color, 1)
                if 'pixel_uv' in estimate:
                    cv2.drawMarker(canvas, tuple(estimate['pixel_uv']), (0, 255, 255), cv2.MARKER_CROSS, 14, 2)
            frame['processing_wall_ms'] = (time.monotonic()-begin)*1000
            frame['accepted_observations'] = sum(d['depth']['status'] == 'ACCEPTED' for d in frame['detections'])
            frame['annotation'] = f'node_{provenance["node_id"]}.png'
            if not cv2.imwrite(str(args.output/frame['annotation']), canvas):
                raise RuntimeError('Annotated image write failed')
            report['frames'].append(frame)
            print(f'Node {provenance["node_id"]}: {len(frame["detections"])} detections, {frame["accepted_observations"]} valid 3D observations', flush=True)
        report['accepted_observations'] = sum(f['accepted_observations'] for f in report['frames'])
        report['rejected_detections'] = sum(len(f['detections'])-f['accepted_observations'] for f in report['frames'])
        report['status'] = 'MEASURED' if report['accepted_observations'] else 'NO_VALID_OBSERVATIONS'
    finally:
        report['duration_s'] = time.monotonic()-started
        (args.output/'observations.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return 0 if report['status'] == 'MEASURED' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=Path('yolov8n.pt'))
    parser.add_argument('--nodes', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(set(args.nodes)) != len(args.nodes):
        parser.error('Select each node once')
    raise SystemExit(observe(args))
