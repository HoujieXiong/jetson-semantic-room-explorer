"""Measure replay odometry; a completed measurement does not imply accurate tracking."""

import argparse
from bisect import bisect_left
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import rclpy
from rclpy.duration import Duration
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rclpy.serialization import deserialize_message
from rclpy.time import Time
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from rtabmap_msgs.msg import OdomInfo
from sensor_msgs.msg import CameraInfo
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer

from check_femto_rosbag import comparison_key, distribution, message_content_bytes


def stamp_ns(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def lost_intervals(rows, end_ns):
    """Source-time spans from first lost result until recovery (or recording end)."""
    intervals, start = [], None
    for row in rows:
        if row['lost'] and start is None:
            start = row['stamp_ns']
        elif not row['lost'] and start is not None:
            intervals.append({'start_ns': start, 'end_ns': row['stamp_ns'],
                              'duration_s': (row['stamp_ns'] - start) / 1e9})
            start = None
    if start is not None:
        intervals.append({'start_ns': start, 'end_ns': end_ns, 'duration_s': (end_ns - start) / 1e9})
    return intervals


def check_pose(row, lost):
    values = row['position_m'] + row['quaternion_xyzw'] + row['covariance_diagonal']
    if not np.all(np.isfinite(values)):
        raise ValueError('Non-finite odometry pose or covariance')
    norm = float(np.linalg.norm(row['quaternion_xyzw']))
    if lost:
        if norm != 0:
            raise ValueError('Lost odometry must publish the configured null quaternion')
    elif not np.isclose(norm, 1, atol=1e-5, rtol=0):
        raise ValueError('Tracked odometry quaternion is not normalized')


class OdomCheck:
    def __init__(self):
        self.info, self.poses = [], []
        self.camera_stamps = {'color': [], 'depth': []}
        self.camera_hashes = {stream: hashlib.sha256() for stream in self.camera_stamps}
        self.camera_content_hashes = {stream: hashlib.sha256() for stream in self.camera_stamps}
        self.tf = Buffer(cache_time=Duration(seconds=120))
        self.dynamic_tf = {}
        self.clock_stamps = []

    def subscribe(self, node):
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE)
        for stream in self.camera_stamps:
            node.create_subscription(CameraInfo, f'/camera/{stream}/camera_info', lambda msg, stream=stream: self.camera_info(stream, msg), qos, raw=True)
        node.create_subscription(OdomInfo, '/odom_info_lite', self.odom_info, qos)
        node.create_subscription(Odometry, '/odom', self.odometry, qos)
        node.create_subscription(TFMessage, '/tf', lambda msg: self.transforms(msg, False), qos)
        node.create_subscription(TFMessage, '/tf_static', lambda msg: self.transforms(msg, True),
                                 QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        node.create_subscription(Clock, '/clock', lambda msg: self.clock_stamps.append(stamp_ns(msg.clock)),
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))

    def incomplete_evidence(self):
        return {'odom_info': self.info, 'odometry': self.poses,
                'received_camera_info': {stream: len(stamps) for stream, stamps in self.camera_stamps.items()}}

    def camera_info(self, stream, payload):
        message = deserialize_message(payload, CameraInfo)
        self.camera_stamps[stream].append(stamp_ns(message.header.stamp))
        self.camera_hashes[stream].update(payload)
        self.camera_content_hashes[stream].update(message_content_bytes(message))

    def odom_info(self, message):
        if message.header.frame_id != 'odom':
            raise ValueError('OdomInfo frame must be odom')
        self.info.append({'stamp_ns': stamp_ns(message.header.stamp), 'lost': message.lost,
                          'inliers': message.inliers, 'matches': message.matches,
                          'features': message.features, 'local_map_size': message.local_map_size,
                          'processing_s': message.time_estimation, 'interval_s': message.interval})

    def odometry(self, message):
        if message.header.frame_id != 'odom' or message.child_frame_id != 'camera_link':
            raise ValueError('Odometry must describe odom -> camera_link')
        p, q = message.pose.pose.position, message.pose.pose.orientation
        self.poses.append({'stamp_ns': stamp_ns(message.header.stamp),
                           'position_m': [p.x, p.y, p.z], 'quaternion_xyzw': [q.x, q.y, q.z, q.w],
                           'covariance_diagonal': list(message.pose.covariance[::7])})

    def transforms(self, message, static):
        for transform in message.transforms:
            if static:
                self.tf.set_transform_static(transform, 'recorded_camera')
            else:
                if transform.header.frame_id != 'odom' or transform.child_frame_id != 'camera_link':
                    raise ValueError('Unexpected dynamic TF publisher or frame')
                self.tf.set_transform(transform, 'rgbd_odometry')
                self.dynamic_tf[stamp_ns(transform.header.stamp)] = transform

    def finish(self, reference):
        for stream, stamps in self.camera_stamps.items():
            expected = reference['topics'][f'/camera/{stream}/camera_info']
            key = comparison_key(reference)
            hashes = self.camera_hashes if key == 'serialized_sha256' else self.camera_content_hashes
            if len(stamps) != expected['count'] or hashes[stream].hexdigest() != expected[key]:
                raise ValueError(f'{stream} CameraInfo replay differs from the verified bag')
        if not self.info or len(self.info) != len(self.poses):
            raise ValueError('Missing odometry or unmatched OdomInfo/Odometry results')
        for rows in (self.info, self.poses):
            stamps = [row['stamp_ns'] for row in rows]
            if min(stamps) <= 0 or np.any(np.diff(stamps) <= 0):
                raise ValueError('Odometry timestamps must increase')
        if len(self.clock_stamps) < 2 or self.clock_stamps[-1] <= self.clock_stamps[0]:
            raise ValueError('No advancing simulated clock')
        color, depth = self.camera_stamps['color'], self.camera_stamps['depth']
        expected_stamps = set()
        for stamp in color:
            index = bisect_left(depth, stamp)
            nearest = min((depth[i] for i in (index-1, index) if 0 <= i < len(depth)), key=lambda s: abs(s-stamp))
            if abs(nearest-stamp) > 5_000_000:
                raise ValueError('Input RGB-D skew exceeds the verified 5 ms contract')
            expected_stamps.add(max(stamp, nearest))
        valid = []
        for info, pose in zip(self.info, self.poses):
            stamp = info['stamp_ns']
            if pose['stamp_ns'] != stamp or stamp not in expected_stamps:
                raise ValueError('Output does not preserve the synchronized source image stamp')
            if not np.isfinite(info['processing_s']) or info['processing_s'] < 0:
                raise ValueError('Invalid processing time')
            check_pose(pose, info['lost'])
            if info['lost']:
                continue
            transform = self.dynamic_tf.get(stamp)
            if transform is None:
                raise ValueError('Missing TF at a tracked image timestamp')
            p, q = transform.transform.translation, transform.transform.rotation
            if not np.allclose([p.x, p.y, p.z], pose['position_m'], atol=1e-6, rtol=0):
                raise ValueError('TF and Odometry translation disagree')
            if not any(np.allclose(sign*np.array([q.x, q.y, q.z, q.w]), pose['quaternion_xyzw'], atol=1e-6, rtol=0) for sign in (1, -1)):
                raise ValueError('TF and Odometry rotation disagree')
            self.tf.lookup_transform('odom', 'camera_color_optical_frame', Time(nanoseconds=stamp))
            valid.append(pose)
        start, end = min(color[0], depth[0]), max(color[-1], depth[-1])
        lost = sum(row['lost'] for row in self.info)
        return {'status': 'MEASURED', 'contract_checks_passed': True,
                'reference_pairs': len(expected_stamps), 'processed_frames': len(self.info),
                'input_frames_without_result': len(expected_stamps)-len(self.info),
                'tracked_frames': len(valid), 'lost_frames': lost,
                'lost_fraction_of_processed': lost/len(self.info),
                'lost_intervals': lost_intervals(self.info, end),
                'source_start_ns': start, 'source_end_ns': end,
                'first_result_offset_s': (self.info[0]['stamp_ns']-start)/1e9,
                'last_result_offset_s': (self.info[-1]['stamp_ns']-start)/1e9,
                'last_tracked_offset_s': (valid[-1]['stamp_ns']-start)/1e9 if valid else None,
                'processing_ms': distribution([row['processing_s']*1000 for row in self.info]),
                'tracked_inliers': distribution([row['inliers'] for row in self.info if not row['lost']]),
                'clock_messages': len(self.clock_stamps), 'validated_pose_tf_count': len(valid),
                'trajectory': [{**pose, 'lost': info['lost']} for info, pose in zip(self.info, self.poses)],
                'odom_info': self.info,
                'limitation': 'No ground-truth pose, accuracy or loop-closure claim; dropped input frames and lost outputs are reported separately.'}


def main(check_type=OdomCheck):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if (not np.isfinite(args.duration) or args.duration <= 0
            or args.output.exists() or args.output.with_suffix('.csv').exists()):
        parser.error('Use a finite positive duration and a new output path')
    reference = json.loads(args.reference.read_text())
    if reference.get('status') != 'PASSED':
        parser.error('Use a verified sensor bag report')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    check = check_type()
    result = {'status': 'INCOMPLETE'}
    rclpy.init()
    node = rclpy.create_node('rtabmap_trial_check', parameter_overrides=[Parameter('use_sim_time', value=True)])
    try:
        check.subscribe(node)
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.get_clock().ros_time_is_active or node.get_clock().now().nanoseconds <= 0:
            raise ValueError('ROS simulated time is not active')
        measured = check.finish(reference)
        with args.output.with_suffix('.csv').open('w', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(['stamp_ns', 'lost', 'x_m', 'y_m', 'z_m', 'qx', 'qy', 'qz', 'qw'])
            for row in measured['trajectory']:
                writer.writerow([row['stamp_ns'], row['lost'], *([None]*7 if row['lost'] else row['position_m']+row['quaternion_xyzw'])])
        result = measured
    finally:
        if result['status'] == 'INCOMPLETE':
            result.update(check.incomplete_evidence())
        try:
            args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
        finally:
            node.destroy_node()
            rclpy.shutdown()
    print(f"Odometry measured: {result['tracked_frames']} tracked, {result['lost_frames']} lost, {result['input_frames_without_result']} inputs without result", flush=True)


if __name__ == '__main__':
    main()
