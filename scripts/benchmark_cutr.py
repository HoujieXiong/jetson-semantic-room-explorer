"""Measure official CuTR RGB-D inference on a small sample or verified Femto frames."""

import argparse
import hashlib
from importlib.metadata import version
import itertools
import json
from pathlib import Path
import resource
import time

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from extract_mapped_rgbd import file_hash
from observe_rgbd_objects import load_frame
from scene_memory import canonical


EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
         (0, 4), (1, 5), (2, 6), (3, 7))
POLICY = {'dtype': 'float32', 'device': 'cuda:0', 'score_threshold': .25,
          'cuda_allocator_fraction': .4, 'max_samples': 10,
          'femto_rgb_size_wh': [1024, 576], 'femto_depth_size_wh': [256, 144],
          'depth_resize': 'Nearest-exact uint16 pixels, then millimeters / 1000; no hole filling',
          'intrinsics_resize': 'Official ImageMeasurementInfo.resize; uniform pixel-coordinate scale'}


def assumed_gravity(map_from_camera):
    """Match upstream capture_stream's yaw removal, assuming map +Z is physical up."""
    transform = np.asarray(map_from_camera, dtype=float)
    if (transform.shape != (4, 4) or not np.isfinite(transform).all()
            or not np.allclose(transform[3], [0, 0, 0, 1], atol=1e-6, rtol=0)
            or not np.allclose(transform[:3, :3].T@transform[:3, :3], np.eye(3), atol=1e-6, rtol=0)
            or not np.isclose(np.linalg.det(transform[:3, :3]), 1, atol=1e-6, rtol=0)):
        raise ValueError('Expected a rigid map-from-optical-camera transform')
    # Upstream's reordered depth-box basis has columns: map +X, -Z, +Y.
    basis = transform[:3, :3].T@np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    if basis[1, 1] <= .5:
        raise ValueError('Femto adapter requires an approximately upright camera; assumed gravity is too tilted')
    angles = Rotation.from_matrix(basis).as_euler('yxz')
    return Rotation.from_euler('xz', angles[1:]).as_matrix()


def femto_sample(frames, node_id):
    import torch
    from cubifyanything.measurement import DepthMeasurementInfo, ImageMeasurementInfo
    from cubifyanything.sensor import PosedSensorInfo, SensorArrayInfo

    rgb, depth, k, transform, provenance = load_frame(frames, node_id)
    if rgb.shape != (720, 1280, 3):
        raise ValueError('This measured Femto adapter requires verified 1280x720 aligned RGB-D')
    sensor = PosedSensorInfo()
    sensor.RT = torch.eye(4)[None]
    sensor.T_gravity = torch.tensor(assumed_gravity(transform), dtype=torch.float32)[None]
    original_size = (rgb.shape[1], rgb.shape[0])
    sensor.image = ImageMeasurementInfo(original_size, torch.tensor(k, dtype=torch.float32)[None]).resize(POLICY['femto_rgb_size_wh'])
    sensor.depth = DepthMeasurementInfo(original_size, torch.tensor(k, dtype=torch.float32)[None]).resize(POLICY['femto_depth_size_wh'])
    image = cv2.resize(rgb, tuple(sensor.image.size), interpolation=cv2.INTER_AREA)
    reduced = cv2.resize(depth, tuple(sensor.depth.size), interpolation=cv2.INTER_NEAREST_EXACT)
    info = SensorArrayInfo()
    info.wide = sensor
    sample = {'sensor_info': info,
              'wide': {'image': torch.tensor(image.transpose(2, 0, 1))[None],
                       'depth': torch.tensor(reduced.astype(np.float32)/1000)[None]},
              'meta': {'node_id': node_id, 'source_stamp_ns': provenance['source_stamp_ns']}}
    return sample, {'source': provenance,
                    'gravity_provenance': 'Assumed map +Z up; source camera pose with upstream yaw removal. No measured IMU gravity.',
                    'map_from_camera': transform.tolist(),
                    'resized_depth_pixels_sha256': hashlib.sha256(reduced.tobytes()).hexdigest()}


def predictions(instances, transform=None):
    boxes = instances.pred_boxes_3d
    centers, dimensions = boxes.gravity_center.cpu(), boxes.dims.cpu()
    rotations, corners = boxes.R.cpu(), boxes.corners.cpu()
    scores, classes = instances.scores.cpu(), instances.pred_classes.cpu()
    rectangles = instances.pred_boxes.cpu()
    rows = []
    for i in range(len(instances)):
        row = {'score': float(scores[i]), 'upstream_class_index': int(classes[i]),
               'box_xyxy': rectangles[i].tolist(),
               'center_camera_m': centers[i].tolist(),
               'dimensions_local_xyz_m': dimensions[i].tolist(),
               'camera_from_box_rotation': rotations[i].tolist(),
               'corners_camera_m': corners[i].tolist()}
        if transform is not None:
            center = np.asarray(row['center_camera_m'])
            camera_corners = np.asarray(row['corners_camera_m'])
            row['center_map_m'] = (transform[:3, :3]@center+transform[:3, 3]).tolist()
            row['corners_map_m'] = (camera_corners@transform[:3, :3].T+transform[:3, 3]).tolist()
        if any(v <= 0 for v in row['dimensions_local_xyz_m']) or row['center_camera_m'][2] <= 0:
            raise ValueError('CuTR produced nonpositive dimensions or center depth')
        rows.append(row)
    canonical(rows)  # Refuse non-finite predictions instead of saving plausible JSON.
    return rows


def render(rgb, k, rows, path):
    canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    skipped = 0
    for index, row in enumerate(rows):
        corners = np.asarray(row['corners_camera_m'])
        if np.any(corners[:, 2] <= .01):
            skipped += 1
            continue  # Retained in JSON; do not draw lines across the camera plane.
        projected = corners@k.T
        projected = np.clip(projected[:, :2]/projected[:, 2:], -100000, 100000).round().astype(int)
        color = (int(40+(index*67)%200), int(40+(index*97)%200), int(40+(index*137)%200))
        for a, b in EDGES:
            cv2.line(canvas, tuple(projected[a]), tuple(projected[b]), color, 1, cv2.LINE_AA)
        x, y = np.asarray(row['box_xyxy'][:2]).round().astype(int)
        cv2.putText(canvas, f'{index}: {row["score"]:.2f}', (max(0, x), max(15, y)),
                    cv2.FONT_HERSHEY_SIMPLEX, .4, color, 1, cv2.LINE_AA)
    if not cv2.imwrite(str(path), canvas):
        raise OSError('Failed to save CuTR projected cuboids')
    return skipped


def benchmark(model_path, output, sample_tar=None, frames=None, nodes=None, repeats=3):
    if (sample_tar is None) == (frames is None) or not 1 <= repeats <= 10:
        raise ValueError('Provide one official sample archive or Femto manifest, with 1..10 repeats')
    if frames is not None and (not nodes or len(nodes) > POLICY['max_samples'] or len(set(nodes)) != len(nodes)):
        raise ValueError('Provide 1..10 unique Femto node IDs')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'policy': POLICY, 'runs': [], 'camera_frame': 'optical x-right y-down z-forward',
              'point_unit': 'meter', 'limitation': 'Class-agnostic experimental cuboids; descriptors are not text-aligned. Domain transfer, object identity and geometric accuracy unverified.'}
    started = time.monotonic()
    try:
        import torch
        import cubifyanything
        from cubifyanything.cubify_transformer import make_cubify_transformer
        from cubifyanything.dataset import CubifyAnythingDataset
        from cubifyanything.preprocessor import Augmentor, Preprocessor

        if not torch.cuda.is_available():
            raise RuntimeError('Jetson CUDA is required; no CPU fallback')
        torch.cuda.set_per_process_memory_fraction(POLICY['cuda_allocator_fraction'])
        inputs = [model_path, frames if frames is not None else sample_tar]
        report['inputs_before'] = {str(p): file_hash(p) for p in inputs}
        package = Path(cubifyanything.__file__).parent
        report['implementation_sha256'] = hashlib.sha256(canonical({str(p.relative_to(package)): file_hash(p)
            for p in sorted(package.rglob('*.py'))}).encode()).hexdigest()
        report['runtime'] = {'torch': torch.__version__, 'device': torch.cuda.get_device_name(0),
                             'cuda_total_memory_bytes': torch.cuda.get_device_properties(0).total_memory,
                             'packages': {name: version(name) for name in
                                          ('torchvision', 'timm', 'numpy', 'scipy', 'webdataset', 'tifffile')},
                             'benchmark_sha256': file_hash(Path(__file__))}
        load_begin = time.monotonic()
        state = torch.load(model_path, map_location='cpu', weights_only=True)['model']
        dimension = state['backbone.0.patch_embed.proj.weight'].shape[0]
        if not any(key.startswith('backbone.0.patch_embed_depth.') for key in state):
            raise ValueError('Expected the official RGB-D model')
        model = make_cubify_transformer(dimension=dimension, depth_model=True).eval()
        model.load_state_dict(state)
        del state
        model = model.to(POLICY['device'])
        torch.cuda.synchronize()
        report.update(load_ms=(time.monotonic()-load_begin)*1000, backbone_dimension=dimension)
        if frames is None:
            samples = [(s, {'gravity_provenance': 'Official sample T_gravity'}) for s in itertools.islice(
                CubifyAnythingDataset([sample_tar.as_uri()]), POLICY['max_samples'])]
        else:
            samples = [femto_sample(frames, node) for node in nodes]
        if not samples:
            raise ValueError('No input samples')
        augmentor, preprocessor = Augmentor(('wide/image', 'wide/depth')), Preprocessor()
        for repeat in range(repeats):
            for index, (sample, provenance) in enumerate(samples):
                sensor = sample['sensor_info'].wide
                begin = time.monotonic()
                packaged = augmentor.package(sample)
                # Passing the float model buffer preserves official RGB mean/std,
                # which would otherwise be cast to uint8 by the upstream normalizer.
                packaged = {key: {name: measurement.to(model.pixel_mean) for name, measurement in value.items()}
                            for key, value in packaged.items()}
                packaged = preprocessor.preprocess([packaged])
                torch.cuda.synchronize()
                preprocessed = time.monotonic()
                with torch.inference_mode():
                    raw = model(packaged)[0]
                torch.cuda.synchronize()
                completed = time.monotonic()
                selected = raw[raw.scores >= POLICY['score_threshold']]
                transform = np.asarray(provenance['map_from_camera']) if 'map_from_camera' in provenance else None
                rows = predictions(selected, transform)
                result = {'sample': index, 'repeat': repeat, 'meta': sample['meta'], 'provenance': provenance,
                          'rgb_size_wh': list(sensor.image.size), 'depth_size_wh': list(sensor.depth.size),
                          'image_k': sensor.image.K[0].tolist(), 'depth_k': sensor.depth.K[0].tolist(),
                          'T_gravity': sensor.T_gravity[0].tolist(),
                          'valid_depth_fraction': float((sample['wide']['depth'] > 0).float().mean()),
                          'preprocess_ms': (preprocessed-begin)*1000, 'model_ms': (completed-preprocessed)*1000,
                          'inference_ms': (completed-begin)*1000, 'raw_count': len(raw), 'selected_count': len(rows),
                          'predictions': rows}
                if repeat == 0:
                    result['overlay'] = f'sample_{index}.png'
                    rgb = sample['wide']['image'][0].numpy().transpose(1, 2, 0)
                    result['overlay_skipped_camera_plane'] = render(
                        rgb, sensor.image.K[0].numpy(), rows, output/result['overlay'])
                report['runs'].append(result)
                print(f'CuTR sample={index} repeat={repeat} selected={len(rows)} inference_ms={result["inference_ms"]:.1f}', flush=True)
        warm = [row['inference_ms'] for row in report['runs'][1:]]
        report.update(status='MEASURED', first_inference_ms=report['runs'][0]['inference_ms'],
                      warm_inference_ms={'count': len(warm), 'median': float(np.median(warm)) if warm else None,
                                         'p95': float(np.percentile(warm, 95)) if warm else None},
                      peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
                      peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved(),
                      inputs_after={str(p): file_hash(p) for p in inputs})
        if report['inputs_before'] != report['inputs_after']:
            report['status'] = 'INCOMPLETE'
            raise ValueError('CuTR inputs changed during trial')
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'benchmark.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--sample-tar', type=Path)
    source.add_argument('--frames', type=Path)
    parser.add_argument('--nodes', type=int, nargs='+')
    parser.add_argument('--assume-map-z-up', action='store_true', help='Required acknowledgement of unmeasured gravity for Femto')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.frames and not args.assume_map_z_up:
        parser.error('Femto samples require --assume-map-z-up; current bags have no IMU gravity')
    benchmark(args.model.resolve(), args.output.resolve(), args.sample_tar.resolve() if args.sample_tar else None,
              args.frames.resolve() if args.frames else None, args.nodes, args.repeats)
