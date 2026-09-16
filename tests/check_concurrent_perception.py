"""Bounded live/replay measurement: GPU RGB-D perception alongside online SLAM."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

import message_filters
import numpy as np
import rclpy
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.serialization import deserialize_message, serialize_message
from rclpy.time import Time
from sensor_msgs.msg import Image
from tf2_ros import TransformException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from check_femto_rosbag import ContractCheck, TOPICS, comparison_key, distribution
from check_rtabmap_mapping import MappingCheck, pose_values
from check_rtabmap_odometry import stamp_ns
from observe_rgbd_objects import DEPTH_POLICY, INFERENCE, infer_rgbd, inference_config
from rgbd_geometry import map_from_camera, pinhole_matrix
from extract_mapped_rgbd import file_hash
from online_scene_memory import OnlineMemoryWriter
from online_semantic_memory import OnlineSemanticCapture, POLICY as SEMANTIC_POLICY, UNLOCALIZED_POLICY
from online_search_preview import GRID_POLICY, occupancy_payload


class ConcurrentCheck(MappingCheck):
    """One pending frame and one inference job; all ROS/TF access stays on the caller thread."""
    def __init__(self, predict, executor):
        super().__init__()
        self.predict, self.executor = predict, executor
        self.begin = time.monotonic()
        self.sensor = ContractCheck('room-walk')
        self.rows, self.tf_events = [], []
        self.pending, self.active = None, None
        self.awaiting_pose = []
        self.odom_by_stamp = {}
        self.callback_ms = []
        self.memory = None
        self.semantic = None
        self.capture_occupancy = False
        self.filters = {topic: message_filters.SimpleFilter() for topic in TOPICS if topic != '/tf_static'}
        self.sync = message_filters.ApproximateTimeSynchronizer(list(self.filters.values()), 10, 0.005)
        self.sync.registerCallback(self.pair)

    def elapsed(self):
        return time.monotonic()-self.begin

    def subscribe(self, node):
        super().subscribe(node)
        if self.capture_occupancy:
            from nav_msgs.msg import OccupancyGrid
            node.create_subscription(OccupancyGrid, '/map', self.occupancy,
                QoSProfile(depth=2, reliability=ReliabilityPolicy.RELIABLE))
        for stream in ('color', 'depth'):
            topic = f'/camera/{stream}/image_raw'
            node.create_subscription(Image, topic, lambda data, topic=topic: self.ingest(topic, data),
                QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE), raw=True)

    def occupancy(self, message):
        self.memory.submit('occupancy', occupancy_payload(message), self.elapsed())

    def camera_info(self, stream, payload):
        super().camera_info(stream, payload)
        self.ingest(f'/camera/{stream}/camera_info', payload)

    def ingest(self, topic, payload):
        begin = time.monotonic()
        self.sensor.add(topic, payload, time.monotonic_ns())
        self.filters[topic].signalMessage(deserialize_message(payload, TOPICS[topic]))
        self.callback_ms.append((time.monotonic()-begin)*1000)

    def transforms(self, message, static):
        super().transforms(message, static)
        if static:
            self.sensor.add('/tf_static', serialize_message(message), time.monotonic_ns())
        for tf in message.transforms:
            self.tf_events.append({'received_elapsed_s': self.elapsed(), 'static': static,
                'stamp_ns': stamp_ns(tf.header.stamp), 'parent': tf.header.frame_id, 'child': tf.child_frame_id,
                **pose_values(tf.transform.translation, tf.transform.rotation)})

    def odom_info(self, message):
        super().odom_info(message)
        stamp = stamp_ns(message.header.stamp)
        if stamp in self.odom_by_stamp:
            raise ValueError('Duplicate odometry source timestamp')
        self.odom_by_stamp[stamp] = {**self.info[-1], 'received_elapsed_s': self.elapsed()}

    def mapping_stats(self, message):
        super().mapping_stats(message)
        if self.memory is not None:
            self.memory.submit('mapping', self.mapping_info[-1], self.elapsed())
        if self.semantic is not None:
            self.semantic.request(self.mapping_info[-1])

    def map_graph(self, message):
        super().map_graph(message)
        if self.memory is not None:
            try:
                tf = self.tf.lookup_transform('camera_link', 'camera_color_optical_frame',
                                              Time(nanoseconds=stamp_ns(message.header.stamp)))
            except TransformException:
                extrinsic = {'status': 'REJECTED', 'reason': 'camera_extrinsic_unavailable'}
            else:
                pose = pose_values(tf.transform.translation, tf.transform.rotation)
                extrinsic = {'status': 'ACCEPTED', 'camera_link_from_optical':
                             map_from_camera(pose['position_m'], pose['quaternion_xyzw']).tolist()}
            self.memory.submit('graph', {**self.graphs[-1], 'extrinsic': extrinsic}, self.elapsed())

    def pair(self, rgb, depth, rgb_info, depth_info):
        stamps = [stamp_ns(m.header.stamp) for m in (rgb, depth, rgb_info, depth_info)]
        if stamps[0] != stamps[2] or stamps[1] != stamps[3] or abs(stamps[0]-stamps[1]) > 5_000_000:
            raise ValueError('Synchronized images must retain their exact CameraInfo timestamps')
        calibration = self.sensor.calibration['/camera/color/camera_info']
        if calibration != self.sensor.calibration['/camera/depth/camera_info']:
            raise ValueError('Registered depth calibration differs from RGB')
        k = pinhole_matrix(calibration['k'])
        p = np.array(calibration['p']).reshape(3, 4)
        if (any(calibration['d']) or not np.array_equal(np.reshape(calibration['r'], (3, 3)), np.eye(3))
                or not np.array_equal(p[:, :3], k) or np.any(p[:, 3])):
            raise ValueError('Expected rectified pinhole calibration')
        stamp = max(stamps[:2])
        if self.rows and stamp <= self.rows[-1]['source_stamp_ns']:
            raise ValueError('Synchronized pair timestamps must increase')
        row = {'source_stamp_ns': stamp, 'rgb_stamp_ns': stamps[0], 'depth_stamp_ns': stamps[1],
               'rgb_depth_skew_ns': stamps[0]-stamps[1], 'arrived_elapsed_s': self.elapsed(),
               'rgb_pixels_sha256': hashlib.sha256(rgb.data).hexdigest(),
               'depth_pixels_sha256': hashlib.sha256(depth.data).hexdigest(), 'status': 'QUEUED'}
        self.rows.append(row)
        if self.pending is not None:
            row.update(status='DROPPED', reason='pending_queue_full')
            if self.memory is not None:
                self.memory.submit('observation', row, self.elapsed())
            return
        # NumPy views retain the ROS message data buffers until the job completes.
        color = np.frombuffer(rgb.data, dtype=np.uint8).reshape(rgb.height, rgb.width, 3)
        if self.semantic is not None:
            self.semantic.remember(row, color)
        depth_mm = np.frombuffer(depth.data, dtype='<u2').reshape(depth.height, depth.width)
        self.pending = (row, color, depth_mm, k)

    def associate(self, row):
        stamp = row['source_stamp_ns']
        info = self.odom_by_stamp.get(stamp)
        reason = 'missing_source_odometry'
        if info is not None:
            if info['lost']:
                return {'status': 'REJECTED', 'reason': 'tracking_lost', 'odom_evidence': info}
            reason = 'missing_source_map_tf'
            if stamp in self.dynamic_tf:
                try:
                    tf = self.tf.lookup_transform('map', 'camera_color_optical_frame', Time(nanoseconds=stamp))
                except TransformException:
                    pass
                else:
                    pose = pose_values(tf.transform.translation, tf.transform.rotation)
                    return {'status': 'ACCEPTED', 'source_stamp_ns': stamp, 'odom_evidence': info,
                            **pose, 'map_from_camera': map_from_camera(pose['position_m'], pose['quaternion_xyzw']).tolist()}
        if self.elapsed()-row['prediction_completed_elapsed_s'] < 2.0:
            return None
        return {'status': 'REJECTED', 'reason': reason, 'odom_evidence': info}

    def pump(self):
        if self.memory is not None:
            self.memory.check()
        if self.active is not None:
            row, future = self.active
            if future.done():
                try:
                    row.update(future.result(), status='AWAITING_POSE', prediction_completed_elapsed_s=self.elapsed())
                except (RuntimeError, ValueError, OSError) as error:
                    row.update(status='FAILED', error={'type': type(error).__name__, 'message': str(error)})
                    raise
                self.awaiting_pose.append(row)
                self.active = None
        for row in list(self.awaiting_pose):
            pose = self.associate(row)
            if pose is None:
                continue
            pose['checked_elapsed_s'] = self.elapsed()
            if pose['status'] == 'ACCEPTED':
                transform = np.array(pose['map_from_camera'])
                for detection in row['detections']:
                    if detection['depth']['status'] == 'ACCEPTED':
                        camera = np.array(detection['depth']['camera_point_m'])
                        detection['map_point_m'] = (transform[:3, :3]@camera+transform[:3, 3]).tolist()
            row.update(pose=pose, status='PROCESSED', completed_elapsed_s=self.elapsed())
            row['pose_wait_ms'] = (pose['checked_elapsed_s']-row['prediction_completed_elapsed_s'])*1000
            row['arrival_to_result_ms'] = (row['completed_elapsed_s']-row['arrived_elapsed_s'])*1000
            if self.memory is not None:
                self.memory.submit('observation', {**row, 'camera_info':
                    self.sensor.calibration['/camera/color/camera_info']}, self.elapsed())
            self.awaiting_pose.remove(row)
        if self.semantic is not None:
            self.semantic.pump(self.rows)
        if self.pending is None or self.active is not None or len(self.awaiting_pose) >= 8:
            return
        row, rgb, depth, k = self.pending
        row.update(dispatched_elapsed_s=self.elapsed(), status='PROCESSING')
        row['queue_wait_ms'] = (row['dispatched_elapsed_s']-row['arrived_elapsed_s'])*1000
        self.active = (row, self.executor.submit(self.predict, rgb, depth, k, None))
        self.pending = None

    def evidence(self):
        return {'frames': self.rows, 'tf_events': self.tf_events,
                'sensor_stamps_ns': dict(self.sensor.stamps),
                'sensor_arrivals_monotonic_ns': dict(self.sensor.arrivals),
                'callback_ms': distribution(self.callback_ms),
                'queue_policy': {'selection': 'every synchronized RGB-D pair', 'pending_capacity': 1,
                    'inference_workers': 1, 'overflow': 'drop_new', 'pose_result_capacity': 8,
                    'pose_wait_after_prediction_wall_s': 2.0,
                    'synchronizer_depth': 10, 'synchronizer_slop_s': 0.005},
                'pose_provenance': 'Online TF at original source stamp, frozen when the result is finalized using only transforms already received; no final optimized pose substitution.',
                'camera_frame': 'camera_color_optical_frame', 'map_frame': 'map',
                'depth_unit': 'millimeter', 'invalid_depth': 0, 'point_unit': 'meter',
                'counts': {status: sum(row['status'] == status for row in self.rows)
                           for status in ('QUEUED', 'PROCESSING', 'AWAITING_POSE', 'PROCESSED', 'DROPPED', 'FAILED')}}

    def finish(self, reference):
        if self.pending is not None or self.active is not None or self.awaiting_pose:
            raise RuntimeError('Pending perception work at the bounded measurement deadline')
        measured = super().finish(reference)
        sensor = self.sensor.finish(measure_message_loss=reference is None)
        measured['contract_checks_passed'] &= sensor['message_completeness_passed']
        if reference is not None:
            for topic in self.filters:
                for key in ('count', comparison_key(reference)):
                    if sensor['topics'][topic][key] != reference['topics'][topic][key]:
                        raise ValueError('Sensor replay changed or messages were lost: '+topic)
        paired = {'color': {row['rgb_stamp_ns'] for row in self.rows},
                  'depth': {row['depth_stamp_ns'] for row in self.rows}}
        unmatched = {topic: sorted(set(self.sensor.stamps[topic])-paired[topic.split('/')[2]]) for topic in self.filters}
        processed = [row for row in self.rows if row['status'] == 'PROCESSED']
        if not processed or not any(row['pose']['status'] == 'ACCEPTED' for row in processed):
            raise ValueError('No processed RGB-D frame has a valid online map pose')
        measured['sensor'] = sensor
        measured['perception'] = {**self.evidence(), 'camera_info': self.sensor.calibration,
            'synchronized_pairs': len(self.rows), 'synchronizer_unmatched_stamps': unmatched,
            'pose_accepted': sum(row['pose']['status'] == 'ACCEPTED' for row in processed),
            'pose_rejected': sum(row['pose']['status'] == 'REJECTED' for row in processed),
            'latency_ms': {key: distribution([row[key] for row in processed]) for key in
                ('queue_wait_ms', 'predict_wall_ms', 'inference_depth_wall_ms', 'pose_wait_ms', 'arrival_to_result_ms')}}
        return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--reference', type=Path, help='Verified sensor bag report; requires simulated time')
    source.add_argument('--live-config', type=Path, help='Actual camera configuration; uses system time. Stop the camera before the deadline to drain work.')
    for name in ('model', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--memory-db', type=Path, help='Optional fresh causal observation/graph journal')
    parser.add_argument('--semantic-model', type=Path, help='Optional MobileCLIP-S0 checkpoint; requires --memory-db')
    parser.add_argument('--semantic-square-pad', action='store_true', help='Keep complete image crops; requires --semantic-model')
    parser.add_argument('--semantic-include-unlocalized', action='store_true', help='Also encode depth-rejected source views without 3D targets; requires --semantic-model')
    parser.add_argument('--imgsz', type=int, default=INFERENCE['imgsz'], help='Detector input size: 640 (default) or 1280')
    parser.add_argument('--capture-occupancy', action='store_true', help='Journal received /map grids; requires --memory-db')
    args = parser.parse_args()
    if args.semantic_model is not None and args.memory_db is None:
        parser.error('--semantic-model requires --memory-db')
    if args.semantic_square_pad and args.semantic_model is None:
        parser.error('--semantic-square-pad requires --semantic-model')
    if args.semantic_include_unlocalized and args.semantic_model is None:
        parser.error('--semantic-include-unlocalized requires --semantic-model')
    try:
        inference = inference_config(args.imgsz)
    except ValueError as error:
        parser.error(str(error))
    if args.capture_occupancy and args.memory_db is None:
        parser.error('--capture-occupancy requires --memory-db')
    ready = args.output.with_suffix('.ready.json')
    if not np.isfinite(args.duration) or not 0 < args.duration <= 600 or args.output.exists() or ready.exists():
        parser.error('Use a new output path and a finite duration at most 600 seconds')
    reference = json.loads(args.reference.read_text()) if args.reference is not None else None
    if reference is not None and reference.get('status') != 'PASSED':
        parser.error('Use the verified sensor bag report')
    source_path = args.reference if reference is not None else args.live_config
    source_key = 'reference_sha256' if reference is not None else 'live_config_sha256'
    model_path = args.model.resolve(strict=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'INCOMPLETE', source_key: file_hash(source_path),
              'input_mode': 'replay' if reference is not None else 'live', 'use_sim_time': reference is not None,
              'model_path': str(model_path), 'model_sha256': file_hash(model_path),
              'inference': inference, 'depth_policy': DEPTH_POLICY,
              'live_capture_executed': False, 'motion_executed': False}
    check = node = executor = memory = semantic = None
    initialized = False
    try:
        os.environ['YOLO_OFFLINE'] = 'true'
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        import cv2
        import torch
        import ultralytics
        from ultralytics import YOLO
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; no CPU fallback')
        model = YOLO(str(model_path))
        started = time.monotonic()
        model.predict(np.zeros((720, 1280, 3), dtype=np.uint8), imgsz=inference['imgsz'],
                      conf=inference['confidence_threshold'], device=inference['device'], save=False, verbose=False)
        torch.cuda.synchronize()
        report['warmup'] = {'synthetic_zero_rgb': True, 'observations_retained': False,
                            'wall_ms': (time.monotonic()-started)*1000}
        report['runtime'] = {'torch': torch.__version__, 'ultralytics': ultralytics.__version__,
                            'opencv': cv2.__version__, 'gpu': torch.cuda.get_device_name(0)}
        encoder = None
        if args.semantic_model is not None:
            from semantic_memory import MobileClipEncoder
            encoder = MobileClipEncoder(args.semantic_model, square_pad=args.semantic_square_pad)
            report['semantic_encoder'] = encoder.identity
            report['semantic_load_ms'] = encoder.load_ms
        rclpy.init()
        initialized = True
        node = rclpy.create_node('concurrent_rgbd_check', parameter_overrides=[Parameter('use_sim_time', value=reference is not None)])
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='rgbd_inference')
        check = ConcurrentCheck(lambda *values: infer_rgbd(model, *values, imgsz=inference['imgsz']), executor)
        if args.memory_db is not None:
            context = {
                **{key: report[key] for key in (source_key, 'input_mode', 'use_sim_time', 'model_sha256', 'inference', 'depth_policy', 'runtime')},
                'session_id': str(uuid.uuid4()), 'origin_monotonic_ns': int(check.begin*1e9),
                'camera_frame': 'camera_color_optical_frame', 'map_frame': 'map', 'point_unit': 'meter'}
            if encoder is not None:
                context.update(semantic_encoder=encoder.identity,
                               semantic_policy=UNLOCALIZED_POLICY if args.semantic_include_unlocalized else SEMANTIC_POLICY)
            if args.capture_occupancy:
                context['grid_policy'] = GRID_POLICY
                check.capture_occupancy = True
            memory = OnlineMemoryWriter(args.memory_db, context)
            check.memory = memory
            if encoder is not None:
                semantic = OnlineSemanticCapture(encoder, memory, args.memory_db.with_suffix('.crops'), check.elapsed)
                check.semantic = semantic
        check.subscribe(node)
        ready.write_text(json.dumps(report, indent=2)+'\n')
        print('READY: GPU warmup and subscriptions complete', flush=True)
        deadline = time.monotonic()+args.duration
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
            check.pump()
        if reference is not None and (not node.get_clock().ros_time_is_active or node.get_clock().now().nanoseconds <= 0):
            raise ValueError('No active ROS simulated clock')
        if reference is None and node.get_clock().ros_time_is_active:
            raise ValueError('Live capture must use system time')
        if semantic is not None:
            if semantic.active is not None or semantic.pending:
                raise RuntimeError('Pending semantic work at the bounded deadline')
            semantic.close()
            if file_hash(args.semantic_model) != encoder.identity['checkpoint_sha256']:
                raise ValueError('Semantic checkpoint changed during the trial')
        if memory is not None:
            memory.close()
        report.update(check.finish(reference))
        if file_hash(model_path) != report['model_sha256'] or file_hash(source_path) != report[source_key]:
            report['status'] = 'INCOMPLETE'
            raise ValueError('Input provenance or model changed during the trial')
    except (RuntimeError, ValueError, OSError) as error:
        report['status'] = 'INCOMPLETE'
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        close_error = None
        try:
            if semantic is not None:
                try:
                    semantic.close()
                except (RuntimeError, ValueError, OSError) as error:
                    close_error = error
                    report.update(status='INCOMPLETE', semantic_error=str(error))
                report['online_semantic'] = {**semantic.stats, 'policy': semantic.policy,
                                             'closed': semantic.closed, 'active_at_close': semantic.active is not None}
            if memory is not None:
                try:
                    memory.close()
                except (RuntimeError, TimeoutError) as error:
                    close_error = error
                    report.update(status='INCOMPLETE', memory_error=str(error))
                report['online_memory'] = {'database': str(args.memory_db.resolve()),
                    'session_id': memory.context['session_id'], 'policy': memory.context['policy'], **memory.stats,
                    'writer_thread_closed': not memory.thread.is_alive()}
            if check is not None and report['status'] == 'INCOMPLETE':
                report.update(check.incomplete_evidence(), perception=check.evidence())
            report['live_capture_executed'] = reference is None and check is not None and bool(check.rows)
            if 'runtime' in report:
                report['peak_cuda_allocated_bytes'] = torch.cuda.max_memory_allocated()
                report['peak_cuda_reserved_bytes'] = torch.cuda.max_memory_reserved()
            args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
        finally:
            if node is not None:
                node.destroy_node()
            if initialized and rclpy.ok():
                rclpy.shutdown()
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)
        if close_error is not None:
            raise close_error
    print('MEASURED: concurrent source-time perception and SLAM', flush=True)


if __name__ == '__main__':
    main()
