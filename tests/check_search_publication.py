"""Receive bounded ROS preview traffic for independent goal/path verification."""

import argparse
import json
from pathlib import Path
import sys
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path as PathMessage
from std_msgs.msg import String
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from rosidl_runtime_py.convert import message_to_ordereddict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from publish_search_preview import TOPICS


def receive(output, duration_s):
    if not 0 < duration_s <= 600:
        raise ValueError('Receiver duration must be in (0, 600] seconds')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'counts': {name: 0 for name in TOPICS}, 'latest': {}}
    rclpy.init(args=[])
    node = rclpy.create_node('search_preview_receiver')
    begin = time.monotonic()
    try:
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)

        def received(name, message):
            report['counts'][name] += 1
            report['latest'][name] = message_to_ordereddict(message)

        for name, kind in [('decision', String), ('goal', PoseStamped), ('path', PathMessage)]:
            node.create_subscription(kind, TOPICS[name], lambda msg, name=name: received(name, msg), qos)
        (output/'ready.json').write_text(json.dumps({'status': 'READY', 'topics': TOPICS})+'\n')
        print('READY', flush=True)
        while time.monotonic()-begin < duration_s:
            rclpy.spin_once(node, timeout_sec=.1)
        report['status'] = 'RECEIVED' if report['counts']['decision'] else 'NO_MESSAGES'
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
        report['duration_s'] = time.monotonic()-begin
        (output/'received.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration-s', type=float, default=30)
    args = parser.parse_args()
    result = receive(args.output, args.duration_s)
    print(json.dumps({'status': result['status'], 'counts': result['counts']}))
    raise SystemExit(0 if result['status'] == 'RECEIVED' else 2)
