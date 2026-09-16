"""Measure mapping interfaces on the verified bag; geometry quality is separate."""

from pathlib import Path
import sys

import numpy as np
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from rtabmap_msgs.msg import Info, MapGraph
from tf2_msgs.msg import TFMessage
from tf2_ros import TransformException

from check_rtabmap_odometry import OdomCheck, check_pose, main, stamp_ns


sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from rgbd_geometry import match_source_stamp


def pose_values(position, orientation):
    row = {'position_m': [position.x, position.y, position.z],
           'quaternion_xyzw': [orientation.x, orientation.y, orientation.z, orientation.w],
           'covariance_diagonal': [0.0]*6}
    check_pose(row, False)
    return {key: row[key] for key in ('position_m', 'quaternion_xyzw')}


class MappingCheck(OdomCheck):
    def __init__(self):
        super().__init__()
        self.mapping_info, self.graphs = [], []
        self.map_tf_count = 0

    def subscribe(self, node):
        super().subscribe(node)
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE)
        node.create_subscription(Info, '/info', self.mapping_stats, qos)
        node.create_subscription(MapGraph, '/mapGraph', self.map_graph, qos)

    def transforms(self, message, static):
        remaining = []
        for transform in message.transforms:
            if not static and (transform.header.frame_id, transform.child_frame_id) == ('map', 'odom'):
                pose_values(transform.transform.translation, transform.transform.rotation)
                self.tf.set_transform(transform, 'rtabmap')
                self.map_tf_count += 1
            else:
                remaining.append(transform)
        super().transforms(TFMessage(transforms=remaining), static)

    def mapping_stats(self, message):
        if message.header.frame_id != 'map' or len(message.stats_keys) != len(message.stats_values):
            raise ValueError('Invalid mapping statistics frame or fields')
        if not np.all(np.isfinite(message.stats_values)):
            raise ValueError('Non-finite mapping statistics')
        self.mapping_info.append({'stamp_ns': stamp_ns(message.header.stamp), 'node_id': message.ref_id,
                                 'loop_closure_id': message.loop_closure_id,
                                 'proximity_detection_id': message.proximity_detection_id,
                                 'stats': dict(zip(message.stats_keys, message.stats_values))})

    def map_graph(self, message):
        if message.header.frame_id != 'map' or len(message.poses_id) != len(message.poses):
            raise ValueError('Invalid map graph frame or pose fields')
        if len(set(message.poses_id)) != len(message.poses_id):
            raise ValueError('Duplicate map graph node IDs')
        correction = pose_values(message.map_to_odom.translation, message.map_to_odom.rotation)
        self.graphs.append({'stamp_ns': stamp_ns(message.header.stamp), 'map_to_odom': correction,
                            'poses': [{'node_id': node_id, **pose_values(p.position, p.orientation)}
                                      for node_id, p in zip(message.poses_id, message.poses)],
                            'links': [{'from_id': link.from_id, 'to_id': link.to_id, 'type': link.type}
                                      for link in message.links]})

    def incomplete_evidence(self):
        return {**super().incomplete_evidence(), 'mapping_info': self.mapping_info,
                'map_graphs': self.graphs, 'map_tf_messages': self.map_tf_count}

    def finish(self, reference):
        result = super().finish(reference)
        if not self.mapping_info or not self.graphs or not self.graphs[-1]['poses']:
            raise ValueError('No nonempty mapping graph or statistics')
        tracked = sorted(row['stamp_ns'] for row in self.info if not row['lost'])
        mapped, unavailable = [], []
        for row in self.mapping_info:
            stamp = match_source_stamp(row['stamp_ns'], tracked)
            association = {'stamp_ns': stamp, 'mapping_stamp_ns': row['stamp_ns'],
                           'stamp_roundtrip_error_ns': row['stamp_ns']-stamp, 'node_id': row['node_id']}
            try:
                transform = self.tf.lookup_transform('map', 'camera_color_optical_frame', Time(nanoseconds=stamp))
            except TransformException as error:
                unavailable.append({**association, 'reason': str(error)})
                continue
            mapped.append({**association,
                           **pose_values(transform.transform.translation, transform.transform.rotation)})
        if not mapped or not self.map_tf_count:
            raise ValueError('No mapped observation has a timestamped map-to-camera TF chain')
        result['mapping'] = {'interface_checks_passed': True, 'info_messages': len(self.mapping_info),
                             'graph_messages': len(self.graphs), 'map_tf_messages': self.map_tf_count,
                             'final_graph_nodes': len(self.graphs[-1]['poses']),
                             'reported_loop_closures': sum(row['loop_closure_id'] > 0 for row in self.mapping_info),
                             'reported_proximity_detections': sum(row['proximity_detection_id'] > 0 for row in self.mapping_info),
                             'validated_map_observations': mapped, 'excluded_tf_unavailable': unavailable,
                             'info': self.mapping_info, 'graphs': self.graphs,
                             'pose_contract': 'map -> camera_color_optical_frame at the observation stamp from recorded online TF; final graph optimization may revise historical poses.',
                             'limitation': 'Database reopening/export are checked separately. Partial coverage and reported loop closures do not establish geometric accuracy or real-time operation.'}
        return result


if __name__ == '__main__':
    main(MappingCheck)
