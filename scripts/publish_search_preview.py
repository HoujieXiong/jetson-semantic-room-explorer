"""Run frozen-memory search and publish bounded ROS 2 goal/path previews."""

import argparse
import json
import math
from pathlib import Path
import sqlite3
import time

from extract_mapped_rgbd import file_hash
from run_offline_search import run_search


TOPICS = {name: '/semantic_explorer/preview/'+name for name in ('decision', 'goal', 'path')}


def select_preview(search, folder):
    """Select the shortest reachable candidate; retain every alternative in search.json."""
    if (search['dry_run'] is not True or search['motion_executed'] is not False
            or search['active_stage'] is not None or search['map_frame'] != 'map'
            or search['coordinate_unit'] != 'meter'):
        raise ValueError('Expected completed metric dry-run search')
    stages = {}
    for stage in search['stages']:
        path = folder/stage['report']
        if file_hash(path) != stage['sha256']:
            raise ValueError('Search stage changed before publication')
        stages[stage['name']] = json.loads(path.read_text())
    chosen = None
    if search['branch'] == 'object_route':
        available = [row for row in search['outcomes'] if row['status'] == 'ROUTE_READY']
        if available:
            row = min(available, key=lambda r: (r['length_m'], r['object_id']))
            route = next(r for r in stages['route']['results'] if r['object_id'] == row['object_id'])
            chosen = {'object_id': row['object_id'], 'goal': row['goal'], 'route': route}
    elif search['branch'] == 'frontier':
        if search['status'] == 'EXPLORATION_READY':
            exploration = stages['frontier']['exploration']
            chosen = {'object_id': None, 'goal': exploration['goal'], 'route': exploration['route']}
    else:
        raise ValueError('Unknown search branch')
    if chosen:
        route, goal = chosen['route'], chosen['goal']
        points = route['path_map_xy_m']
        if (route['status'] != 'ROUTE_READY' or not points
                or points[0] != search['start']['map_xy_m'] or points[-1] != goal['map_xy_m']):
            raise ValueError('Preview route endpoints disagree with start/goal')
        json.dumps(chosen, allow_nan=False)
    return {'dry_run': True, 'motion_executed': False, 'map_frame': 'map', 'coordinate_unit': 'meter',
            'query_label': search['query_label'], 'search_status': search['status'], 'branch': search['branch'],
            'start': search['start'], 'selection': chosen, 'outcomes': search['outcomes'],
            'selection_policy': 'Shortest reachable route, then object ID; geometric preference, not identity confidence',
            'search_sha256': file_hash(folder/'search.json'), 'memory_sha256': search['memory_sha256'],
            'limitation': search['limitation']}


def messages(decision, stamp):
    from geometry_msgs.msg import PoseStamped
    from nav_msgs.msg import Path as PathMessage
    from std_msgs.msg import String

    decision = {**decision, 'publication_stamp_ns': stamp.sec*10**9+stamp.nanosec,
                'stamp_semantics': 'Publication time; observation timestamps remain in search evidence'}
    result = {'decision': String(data=json.dumps(decision, allow_nan=False))}
    selection = decision['selection']
    if selection is None:
        return result

    def pose(point, yaw):
        msg = PoseStamped()
        msg.header.frame_id, msg.header.stamp = 'map', stamp
        msg.pose.position.x, msg.pose.position.y = map(float, point)
        msg.pose.orientation.z, msg.pose.orientation.w = math.sin(yaw/2), math.cos(yaw/2)
        return msg

    goal = selection['goal']
    result['goal'] = pose(goal['map_xy_m'], goal['yaw_rad'])
    path = PathMessage()
    path.header = result['goal'].header
    points = selection['route']['path_map_xy_m']
    for index, point in enumerate(points):
        yaw = (math.atan2(points[index+1][1]-point[1], points[index+1][0]-point[0])
               if index+1 < len(points) else goal['yaw_rad'])
        path.poses.append(pose(point, yaw))
    result['path'] = path
    return result


def publish(decision, duration_s, subscriber_timeout_s, report):
    import rclpy
    from rclpy.context import Context
    from rclpy.duration import Duration
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy

    context = Context()
    node = executor = None
    started = time.monotonic()
    try:
        rclpy.init(args=[], context=context)
        node = rclpy.create_node('semantic_search_preview', context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
        payloads = messages(decision, node.get_clock().now().to_msg())
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        publishers = {name: node.create_publisher(type(msg), TOPICS[name], qos) for name, msg in payloads.items()}
        report.update(topics={name: TOPICS[name] for name in payloads},
                      published_counts={name: 0 for name in payloads},
                      publication_stamp_ns=json.loads(payloads['decision'].data)['publication_stamp_ns'])
        deadline = time.monotonic()+subscriber_timeout_s
        while not all(pub.get_subscription_count() for pub in publishers.values()):
            if time.monotonic() >= deadline:
                raise TimeoutError('No subscriber for every preview topic before deadline')
            executor.spin_once(timeout_sec=.05)
        report['subscriber_wait_s'] = time.monotonic()-started
        report['subscriber_counts'] = {name: pub.get_subscription_count() for name, pub in publishers.items()}
        deadline, next_publish = time.monotonic()+duration_s, 0
        while time.monotonic() < deadline:
            if time.monotonic() >= next_publish:
                for name, pub in publishers.items():
                    pub.publish(payloads[name])
                    report['published_counts'][name] += 1
                next_publish = time.monotonic()+1
            executor.spin_once(timeout_sec=.05)
        report['dds_acknowledged'] = {name: pub.wait_for_all_acked(Duration(seconds=1))
                                      for name, pub in publishers.items()}
        if not all(report['dds_acknowledged'].values()):
            raise TimeoutError('Preview DDS acknowledgement deadline exceeded')
        report['status'] = 'PUBLISHED'
    finally:
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        context.try_shutdown()
        report['ros_context_closed'] = not context.ok()
        report['publication_duration_s'] = time.monotonic()-started


def run(memory, mapping, label, output, node_id=None, simulated_xy=None, duration_s=5, subscriber_timeout_s=10):
    if not (math.isfinite(duration_s) and .1 <= duration_s <= 60
            and math.isfinite(subscriber_timeout_s) and .1 <= subscriber_timeout_s <= 60):
        raise ValueError('Publication and subscriber waits must each be between 0.1 and 60 seconds')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'dry_run': True, 'motion_executed': False,
              'requested_duration_s': duration_s, 'subscriber_timeout_s': subscriber_timeout_s}
    try:
        search = run_search(memory, mapping, label, output/'search', node_id, simulated_xy)
        decision = select_preview(search, output/'search')
        report['decision'] = decision
        publish(decision, duration_s, subscriber_timeout_s, report)
    except (ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        (output/'publication.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('memory', 'mapping', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--label', required=True)
    start = parser.add_mutually_exclusive_group(required=True)
    start.add_argument('--start-node', type=int)
    start.add_argument('--simulated-start-xy', type=float, nargs=2, metavar=('X_M', 'Y_M'))
    parser.add_argument('--duration-s', type=float, default=5)
    parser.add_argument('--subscriber-timeout-s', type=float, default=10)
    args = parser.parse_args()
    result = run(args.memory.resolve(), args.mapping.resolve(), args.label, args.output.resolve(),
                 args.start_node, args.simulated_start_xy, args.duration_s, args.subscriber_timeout_s)
    print(json.dumps({'status': result['status'], 'report': str(args.output/'publication.json')}))
