"""Extract original color RGB-D for frozen RTAB-Map nodes using system ROS Python."""

import argparse
from bisect import bisect_left, bisect_right
import hashlib
import json
from pathlib import Path
import time

import numpy as np


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def selected_stamp(stamp, source_stamps):
    """Select only a nearby mapped source; distant frames remain unselected."""
    candidates = source_stamps[bisect_left(source_stamps, stamp-5_000_000):
                               bisect_right(source_stamps, stamp+5_000_000)]
    if len(candidates) > 1:
        raise ValueError('Ambiguous mapped frame association')
    return candidates[0] if candidates else None


def extract(bag, reference_path, mapping, output):
    import cv2
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import CameraInfo, Image

    reference = json.loads(reference_path.read_text())
    database = json.loads((mapping/'database_check.json').read_text())
    exported = json.loads((mapping/'export_run.json').read_text())
    measurement = json.loads((mapping/'measurement.json').read_text())
    if (reference['status'] != 'PASSED' or database['status'] != 'VERIFIED'
            or exported['status'] != 'EXPORTED' or measurement['status'] != 'MEASURED'):
        raise ValueError('Use verified bag, mapping and export evidence')
    if file_hash(mapping/'map.db') != database['database_sha256']:
        raise ValueError('Database no longer matches the verified export')
    pose_path = mapping/'export/room_camera_poses.txt'
    expected_hash = next(row['sha256'] for row in exported['files'] if row['name'] == pose_path.name)
    if file_hash(pose_path) != expected_hash:
        raise ValueError('Exported camera poses changed')
    poses = np.loadtxt(pose_path, ndmin=2)
    if poses.shape[1] != 9 or not np.isfinite(poses).all():
        raise ValueError('Expected finite timestamp/translation/quaternion/node-ID poses')
    nodes = {row['node_id']: row for row in database['nodes']}
    graph_ids = {row['node_id'] for row in measurement['mapping']['graphs'][-1]['poses']}
    if set(poses[:, 8]) != graph_ids or len(poses) != len(graph_ids):
        raise ValueError('Camera poses do not match the final graph node IDs')
    tracked = {row['stamp_ns'] for row in measurement['odom_info'] if not row['lost']}
    rows = {}
    for pose in poses:
        node_id = int(pose[8])
        stamp = nodes[node_id]['source_stamp_ns']
        if stamp not in tracked or nodes[node_id]['map_id'] != 0 or stamp in rows:
            raise ValueError('Invalid tracked node or map association')
        rows[stamp] = {'node_id': node_id, 'source_stamp_ns': stamp,
                       'position_m': pose[1:4].tolist(), 'quaternion_xyzw': pose[4:8].tolist(),
                       'file': f'{node_id}.npz', 'messages': {}}
    source_stamps = sorted(rows)
    topics = {f'/camera/{stream}/{kind}': (stream, kind)
              for stream in ('color', 'depth') for kind in ('image_raw', 'camera_info')}
    hashes = {topic: hashlib.sha256() for topic in topics}
    counts = dict.fromkeys(topics, 0)
    pending = {}
    result = {'status': 'INCOMPLETE', 'frames': list(rows.values()), 'bag': str(bag),
              'mapping_run': str(mapping), 'database_sha256': database['database_sha256'],
              'camera_poses_sha256': expected_hash, 'reference_sha256': file_hash(reference_path),
              'pose_frame': 'map -> camera_color_optical_frame',
              'pose_provenance': 'Frozen final optimized camera poses, joined by node ID; not historical online TF.',
              'depth_unit': 'millimeter', 'invalid_depth': 0}
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    reader = rosbag2_py.SequentialCompressionReader()
    try:
        reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id='sqlite3'),
                    rosbag2_py.ConverterOptions('', ''))
        reader.set_filter(rosbag2_py.StorageFilter(topics=list(topics)))
        while reader.has_next():
            topic, payload, _ = reader.read_next()
            hashes[topic].update(payload)
            counts[topic] += 1
            stream, kind = topics[topic]
            message = deserialize_message(payload, Image if kind == 'image_raw' else CameraInfo)
            stamp = message.header.stamp.sec*1_000_000_000 + message.header.stamp.nanosec
            source = selected_stamp(stamp, source_stamps)
            if source is None:
                continue
            row = rows[source]
            if topic in row['messages']:
                raise ValueError(f'Duplicate selected input for node {row["node_id"]}: {topic}')
            if (message.header.frame_id, message.width, message.height) != ('camera_color_optical_frame', 1280, 720):
                raise ValueError('Expected the verified registered optical-frame pixel grid')
            row['messages'][topic] = {'stamp_ns': stamp, 'serialized_sha256': hashlib.sha256(payload).hexdigest()}
            if kind == 'camera_info':
                calibration = {'width': message.width, 'height': message.height,
                               'distortion_model': message.distortion_model,
                               **{name: list(getattr(message, name)) for name in ('d', 'k', 'r', 'p')}}
                if calibration != reference['camera_info'][topic]:
                    raise ValueError('Selected calibration differs from verified source')
                continue
            is_depth = stream == 'depth'
            encoding, step = ('16UC1', 2560) if is_depth else ('rgb8', 3840)
            if (message.encoding, message.step, message.is_bigendian, len(message.data)) != (encoding, step, 0, step*720):
                raise ValueError('Unexpected selected image encoding, stride or payload')
            pixels = np.frombuffer(message.data, dtype='<u2' if is_depth else np.uint8)
            pixels = pixels.reshape((720, 1280) if is_depth else (720, 1280, 3)).copy()
            if is_depth:
                stored = cv2.imread(str(mapping/f'export/room_depth/{row["node_id"]}.png'), cv2.IMREAD_UNCHANGED)
                if stored is None or not np.array_equal(stored, pixels):
                    raise ValueError('Original depth differs from the mapped node depth')
            pending.setdefault(source, {})[stream] = pixels
            if len(pending[source]) == 2:
                pair = pending.pop(source)
                np.savez(output/row['file'], rgb=pair['color'], depth_mm=pair['depth'])
                row['file_sha256'] = file_hash(output/row['file'])
                print(f'Extracted node {row["node_id"]}', flush=True)
        for topic in topics:
            expected = reference['topics'][topic]
            if counts[topic] != expected['count'] or hashes[topic].hexdigest() != expected['serialized_sha256']:
                raise ValueError(f'Full source topic differs from verified bag: {topic}')
        color = reference['camera_info']['/camera/color/camera_info']
        depth = reference['camera_info']['/camera/depth/camera_info']
        if color != depth or any(color['d']) or not np.array_equal(np.reshape(color['r'], (3, 3)), np.eye(3)):
            raise ValueError('Require matching rectified RGB/depth calibration')
        projection = np.reshape(color['p'], (3, 4))
        if not np.array_equal(projection[:, :3], np.reshape(color['k'], (3, 3))) or np.any(projection[:, 3]):
            raise ValueError('Projection matrix must match the rectified pinhole intrinsics')
        for row in rows.values():
            if set(row['messages']) != set(topics) or 'file_sha256' not in row:
                raise ValueError('Missing selected RGB-D image or calibration')
            stamps = []
            for stream in ('color', 'depth'):
                image_stamp = row['messages'][f'/camera/{stream}/image_raw']['stamp_ns']
                if image_stamp != row['messages'][f'/camera/{stream}/camera_info']['stamp_ns']:
                    raise ValueError('Image and CameraInfo timestamps differ')
                stamps.append(image_stamp)
            if max(stamps) != row['source_stamp_ns'] or abs(stamps[0]-stamps[1]) > 5_000_000:
                raise ValueError('Pair does not reproduce the mapped aggregate source stamp')
            row['rgb_depth_skew_ns'] = stamps[0]-stamps[1]
        result.update(status='VERIFIED', camera_info=color, frame_count=len(rows),
                      source_topic_hashes={topic: digest.hexdigest() for topic, digest in hashes.items()},
                      source_topic_counts=counts, depth_pixels_equal_to_database=len(rows)*720*1280)
    finally:
        del reader
        result['duration_s'] = time.monotonic()-started
        (output/'frames.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bag', 'reference', 'mapping-run', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    extract(args.bag.resolve(), args.reference.resolve(), args.mapping_run.resolve(), args.output.resolve())
