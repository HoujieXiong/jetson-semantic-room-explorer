"""Check the Femto ROS contract from a bag or live/replayed messages, using system ROS Python."""

import argparse
from bisect import bisect_left
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import rclpy
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rclpy.serialization import deserialize_message
from rclpy.time import Time
import rosbag2_py
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer
import yaml


TOPICS = {
    '/camera/color/image_raw': Image,
    '/camera/depth/image_raw': Image,
    '/camera/color/camera_info': CameraInfo,
    '/camera/depth/camera_info': CameraInfo,
    '/tf_static': TFMessage,
}
OPTICAL_FRAME = 'camera_color_optical_frame'
# A subscriber may enter or leave between a pair's two messages.
MAX_BOUNDARY_FRAMES = 2


def distribution(values):
    if not len(values):
        return None
    return {'min': float(np.min(values)), 'median': float(np.median(values)),
            'p95': float(np.percentile(values, 95)), 'max': float(np.max(values))}


def paired_timestamps(color, depth, tolerance_ns=5_000_000):
    """One-to-one nearest matching; report unmatched frames inside the shared time window."""
    start, end = max(color[0], depth[0]), min(color[-1], depth[-1])
    if start >= end:
        raise ValueError('Color and depth do not share a time interval')
    used, deltas, unmatched = set(), [], []
    for stamp in color:
        index = bisect_left(depth, stamp)
        choices = [i for i in (index - 1, index) if 0 <= i < len(depth) and i not in used]
        nearest = min(choices, key=lambda i: abs(depth[i] - stamp)) if choices else None
        if nearest is not None and abs(depth[nearest] - stamp) <= tolerance_ns:
            used.add(nearest)
            deltas.append((stamp - depth[nearest]) / 1000)
        elif start <= stamp <= end:
            unmatched.append(stamp)
    unmatched_depth = sum(start <= s <= end and i not in used for i, s in enumerate(depth))
    return {
        'pairs': len(deltas), 'absolute_skew_us': distribution(np.abs(deltas)),
        'unmatched_color_interior': len(unmatched),
        'unmatched_depth_interior': unmatched_depth,
        'unmatched_color_boundaries': len(color) - len(deltas) - len(unmatched),
        'unmatched_depth_boundaries': len(depth) - len(used) - unmatched_depth,
    }


class ContractCheck:
    def __init__(self, scene='fixed-wall'):
        if scene not in ('fixed-wall', 'room-walk'):
            raise ValueError(f'Unknown scene: {scene}')
        self.scene = scene
        self.counts = defaultdict(int)
        self.hashes = {topic: hashlib.sha256() for topic in TOPICS}
        self.stamps = defaultdict(list)
        self.arrivals = defaultdict(list)
        self.calibration = {}
        self.depth_centers, self.depth_coverage = [], []
        self.depth_empty_centers = 0
        self.first_images = {}
        self.transforms = {}
        self.tf_quaternion_norms = {}
        self.tf = Buffer()

    def add(self, topic, payload, arrival_ns):
        message = deserialize_message(payload, TOPICS[topic])
        self.counts[topic] += 1
        self.hashes[topic].update(payload)
        self.arrivals[topic].append(arrival_ns)
        if topic == '/tf_static':
            for transform in message.transforms:
                q = transform.transform.rotation
                norm = float(np.sqrt(q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w))
                if not np.isclose(norm, 1, atol=1e-6, rtol=0):
                    raise ValueError(f'Static TF quaternion is not normalized: {transform}')
                self.tf_quaternion_norms[transform.child_frame_id] = norm
                self.tf.set_transform_static(transform, 'recorded_camera')
                self.transforms[transform.child_frame_id] = transform.header.frame_id
            return
        stamp = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
        if stamp <= 0 or (self.stamps[topic] and stamp <= self.stamps[topic][-1]):
            raise ValueError(f'Non-increasing or zero timestamp on {topic}')
        self.stamps[topic].append(stamp)
        if message.header.frame_id != OPTICAL_FRAME:
            raise ValueError(f'Unexpected optical frame on {topic}: {message.header.frame_id}')
        if (message.width, message.height) != (1280, 720):
            raise ValueError(f'Unexpected pixel grid on {topic}: {message.width}x{message.height}')
        if isinstance(message, CameraInfo):
            info = {'width': message.width, 'height': message.height,
                    'distortion_model': message.distortion_model,
                    **{name: list(getattr(message, name)) for name in ('d', 'k', 'r', 'p')}}
            if not np.all(np.isfinite(info['k'] + info['d'] + info['r'] + info['p'])) or info['k'][0] <= 0 or info['k'][4] <= 0:
                raise ValueError(f'Invalid calibration on {topic}')
            if topic in self.calibration and self.calibration[topic] != info:
                raise ValueError(f'Calibration changed on {topic}')
            self.calibration[topic] = info
            return
        is_depth = topic == '/camera/depth/image_raw'
        encoding, stride = ('16UC1', 2560) if is_depth else ('rgb8', 3840)
        if message.encoding != encoding or message.step != stride or message.is_bigendian:
            raise ValueError(f'Unexpected encoding/stride/endianness on {topic}')
        if len(message.data) != stride * message.height:
            raise ValueError(f'Truncated image on {topic}')
        pixels = np.frombuffer(message.data, dtype='<u2' if is_depth else np.uint8)
        pixels = pixels.reshape((720, 1280) if is_depth else (720, 1280, 3))
        if topic not in self.first_images:
            self.first_images[topic] = pixels.copy()
        if is_depth:
            self.depth_coverage.append(float(np.count_nonzero(pixels)) / pixels.size)
            roi = pixels[350:370, 630:650]
            valid = roi[roi != 0]
            if not valid.size:
                self.depth_empty_centers += 1
                if self.scene == 'fixed-wall':
                    raise ValueError('Aligned center has no valid depth for the fixed-wall unit check')
            else:
                self.depth_centers.append(float(np.median(valid)) / 1000)

    def finish(self):
        for topic in TOPICS:
            if self.counts[topic] < (1 if topic == '/tf_static' else 10):
                raise ValueError(f'Insufficient messages on {topic}: {self.counts[topic]}')
        if self.calibration['/camera/color/camera_info'] != self.calibration['/camera/depth/camera_info']:
            raise ValueError('Registered depth and color CameraInfo disagree')
        info_matching = {}
        for stream in ('color', 'depth'):
            images = self.stamps[f'/camera/{stream}/image_raw']
            infos = self.stamps[f'/camera/{stream}/camera_info']
            start, end = max(images[0], infos[0]), min(images[-1], infos[-1])
            if start >= end:
                raise ValueError(f'Image/CameraInfo have no shared {stream} time interval')
            missing = set(images) ^ set(infos)
            interior = sum(start <= stamp <= end for stamp in missing)
            info_matching[stream] = {'unmatched_interior': interior, 'unmatched_at_recording_boundaries': len(missing) - interior}
            if interior:
                raise ValueError(f'Image/CameraInfo timestamp mismatch inside {stream} recording')
            if len(missing) - interior > MAX_BOUNDARY_FRAMES:
                raise ValueError(f'Too many missing {stream} Image/CameraInfo messages at recording boundaries')
        pairs = paired_timestamps(self.stamps['/camera/color/image_raw'], self.stamps['/camera/depth/image_raw'])
        if not pairs['pairs'] or pairs['unmatched_color_interior'] or pairs['unmatched_depth_interior']:
            raise ValueError(f'Unmatched RGB-D frames inside the recording: {pairs}')
        if max(pairs['unmatched_color_boundaries'], pairs['unmatched_depth_boundaries']) > MAX_BOUNDARY_FRAMES:
            raise ValueError(f'Too many unmatched RGB-D frames at recording boundaries: {pairs}')
        if not any(self.depth_coverage):
            raise ValueError('Recording contains no valid depth')
        if self.scene == 'fixed-wall' and not (2 <= min(self.depth_centers) <= max(self.depth_centers) <= 3):
            raise ValueError('Millimeter depth interpretation disagrees with the user-provided 2-3 m wall range')
        for topic in self.stamps:
            for stamp in (self.stamps[topic][0], self.stamps[topic][-1]):
                self.tf.lookup_transform('camera_link', OPTICAL_FRAME, Time(nanoseconds=stamp))
        topics = {}
        for topic in TOPICS:
            stamps = self.stamps.get(topic, [])
            arrivals = self.arrivals[topic]
            topics[topic] = {
                'count': self.counts[topic], 'serialized_sha256': self.hashes[topic].hexdigest(),
                'header_rate_hz': (len(stamps)-1)*1e9/(stamps[-1]-stamps[0]) if len(stamps)>1 else None,
                'arrival_rate_hz': (len(arrivals)-1)*1e9/(arrivals[-1]-arrivals[0]) if len(arrivals)>1 and arrivals[-1]>arrivals[0] else None,
                'header_period_ms': distribution(np.diff(stamps)/1e6),
                'first_stamp_ns': stamps[0] if stamps else None, 'last_stamp_ns': stamps[-1] if stamps else None,
            }
        return {'status': 'PASSED', 'scene': self.scene, 'topics': topics, 'camera_info': self.calibration,
                'image_info_matching': info_matching, 'synchronization': pairs,
                'depth_center_m': distribution(self.depth_centers), 'depth_valid_ratio': distribution(self.depth_coverage),
                'depth_empty_center_frames': self.depth_empty_centers,
                'depth_empty_frames': self.depth_coverage.count(0),
                'fixed_wall_unit_check': self.scene == 'fixed-wall',
                'depth_encoding': '16UC1 millimeters; zero invalid', 'static_tf_parents': self.transforms,
                'static_tf_quaternion_norms': self.tf_quaternion_norms,
                'tf_check': 'Static camera_link-to-color-optical chain resolves at first and last image/info timestamps'}


def inspect_bag(path, check):
    metadata = yaml.safe_load((path / 'metadata.yaml').read_text())['rosbag2_bagfile_information']
    compression = metadata.get('compression_mode', '').lower()
    reader_type = rosbag2_py.SequentialCompressionReader if compression in ('message', 'file') else rosbag2_py.SequentialReader
    reader = reader_type()
    reader.open(rosbag2_py.StorageOptions(uri=str(path), storage_id='sqlite3'), rosbag2_py.ConverterOptions('', ''))
    while reader.has_next():
        topic, payload, stamp = reader.read_next()
        if topic in TOPICS:
            check.add(topic, payload, stamp)
    return {'bag_path': str(path), 'compression_mode': compression,
            'bag_duration_s': metadata['duration']['nanoseconds'] / 1e9,
            'receipt_minus_header_ms': {
                topic: distribution((np.array(check.arrivals[topic], dtype=np.int64) -
                                     np.array(stamps, dtype=np.int64)) / 1e6)
                for topic, stamps in check.stamps.items() if stamps},
            'offered_qos': {item['topic_metadata']['name']: item['topic_metadata']['offered_qos_profiles']
                            for item in metadata['topics_with_message_count'] if item['topic_metadata']['name'] in TOPICS}}


def observe(check, duration, reference):
    rclpy.init()
    node = rclpy.create_node('femto_contract_check', parameter_overrides=[Parameter('use_sim_time', value=bool(reference))])
    clocks = []
    qos_report = {}
    try:
        for topic, message_type in TOPICS.items():
            qos = QoSProfile(depth=30, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL if topic == '/tf_static' else DurabilityPolicy.VOLATILE)
            node.create_subscription(message_type, topic, lambda payload, topic=topic: check.add(topic, payload, time.monotonic_ns()), qos, raw=True)
        if reference:
            node.create_subscription(Clock, '/clock', lambda msg: clocks.append(msg.clock.sec*1_000_000_000 + msg.clock.nanosec),
                                     QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if not qos_report and all(check.counts[t] for t in TOPICS):
                qos_report = {topic: [{'node': item.node_name, 'reliability': item.qos_profile.reliability.name,
                                      'durability': item.qos_profile.durability.name, 'depth': item.qos_profile.depth}
                                     for item in node.get_publishers_info_by_topic(topic)] for topic in TOPICS}
            if reference and all(check.counts[t] >= reference['topics'][t]['count'] for t in TOPICS):
                break
        if reference:
            for topic in TOPICS:
                expected = reference['topics'][topic]
                if check.counts[topic] != expected['count'] or check.hashes[topic].hexdigest() != expected['serialized_sha256']:
                    raise ValueError(f'Replay message count/content differs from the bag on {topic}')
            if (len(clocks) < 2 or clocks[-1] <= clocks[0] or not node.get_parameter('use_sim_time').value
                    or not node.get_clock().ros_time_is_active or node.get_clock().now().nanoseconds <= 0):
                raise ValueError('Replay did not supply an advancing simulated clock')
        return {'publisher_qos': qos_report, 'use_sim_time': bool(reference), 'clock_messages': len(clocks),
                'simulated_time_final_ns': node.get_clock().now().nanoseconds if reference else None,
                'replay_matches_bag': True if reference else None}
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bag', type=Path, help='Inspect a saved bag instead of subscribing.')
    parser.add_argument('--duration', type=float, default=15, help='Maximum subscription time in seconds.')
    parser.add_argument('--reference', type=Path, help='Expected bag report for replay count/content verification.')
    parser.add_argument('--scene', choices=('fixed-wall', 'room-walk'),
                        help='Defaults to fixed-wall, or inherits the replay reference scene. Room-walk uses the previously verified mm conversion without a new physical distance check.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not np.isfinite(args.duration) or args.duration <= 0 or (args.bag and args.reference):
        parser.error('Use a finite positive duration and only one of --bag / --reference')
    if args.output.exists():
        parser.error('Output report already exists; choose a new evidence path')
    reference = json.loads(args.reference.read_text()) if args.reference else None
    if reference is not None and reference.get('status') != 'PASSED':
        parser.error('Replay reference must be a PASSED bag report')
    reference_scene = reference.get('scene', 'fixed-wall') if reference is not None else None
    if reference is not None and args.scene and args.scene != reference_scene:
        parser.error('Replay scene must match the reference report')
    scene = args.scene or reference_scene or 'fixed-wall'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    check = ContractCheck(scene)
    result = {'status': 'INCOMPLETE', 'scene': scene}
    try:
        details = inspect_bag(args.bag, check) if args.bag else observe(check, args.duration, reference)
        for topic, pixels in check.first_images.items():
            stream = topic.split('/')[2]
            np.save(args.output.with_name(args.output.stem + '_' + stream + '.npy'), pixels)
        result = {**check.finish(), **details}
    finally:
        if result['status'] != 'PASSED':
            result['received_counts'] = dict(check.counts)
            result['observed_camera_info'] = check.calibration
            result['observed_depth_center_m'] = distribution(check.depth_centers)
            result['observed_depth_valid_ratio'] = distribution(check.depth_coverage)
            result['depth_empty_center_frames'] = check.depth_empty_centers
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(f"ROS contract {result['status']}: {args.output}", flush=True)


if __name__ == '__main__':
    main()
