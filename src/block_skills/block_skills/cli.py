"""Command-line client; also an example for a future agent adapter."""
import argparse
import json
import math
import secrets
from pathlib import Path
import re
import sys
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_srvs.srv import Trigger
from block_interfaces.action import PickPlace
from block_interfaces.srv import Blocks


def wait(node, future, seconds):
    rclpy.spin_until_future_complete(node, future, timeout_sec=seconds)
    if not future.done():
        raise TimeoutError('ROS request timed out.')
    return future.result()


def target(args):
    pose = PoseStamped()
    pose.header.frame_id = 'world'
    pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = args.x, args.y, args.z
    pose.pose.orientation.z = math.sin(args.yaw/2)
    pose.pose.orientation.w = math.cos(args.yaw/2)
    return pose


def parser():
    p = argparse.ArgumentParser(description='Manage Gazebo blocks and execute the UR10e pick/place skill.')
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    status = commands.add_parser('status')
    status.add_argument('--wait', type=float, default=0, help='Wait up to this many seconds for readiness.')
    randomize = commands.add_parser('randomize')
    randomize.add_argument('--seed', type=int, default=1)
    add = commands.add_parser('add', help='Add a colored block at a random free location.')
    add.add_argument('color')
    add.add_argument('--name', default='')
    add.add_argument('--seed', type=int, default=None)
    stack = commands.add_parser('stack', help='Stack one block on another; save a screenshot by default.')
    stack.add_argument('name', help='Block to pick (name or unique color).')
    stack.add_argument('support', help='Block to stack on (name or unique color).')
    stack.add_argument('--evidence', choices=['none', 'screenshot'], default='screenshot')
    stack.add_argument('--cancel-after', type=float, default=0)
    report = commands.add_parser('result', help='Read a saved task result for a future agent.')
    report.add_argument('task_id')
    for name in ['spawn', 'move', 'pick']:
        sub = commands.add_parser(name)
        sub.add_argument('name', help='Exact model name; pick also accepts an unambiguous color.')
        if name == 'spawn':
            sub.add_argument('color')
        sub.add_argument('x', type=float)
        sub.add_argument('y', type=float)
        sub.add_argument('z', type=float, help='Block centre height, metres in world frame.')
        sub.add_argument('--yaw', type=float, default=0, help='Block yaw, radians.')
        if name == 'pick':
            sub.add_argument('--cancel-after', type=float, default=0, help='Cancel after N seconds (testing).')
            sub.add_argument('--evidence', choices=['none', 'screenshot'], default='none')
    return p


def run(node, args):
    if args.command == 'result':
        if not re.fullmatch('[0-9a-f]{32}', args.task_id):
            raise ValueError('task_id must be the 32-character ID returned by a skill.')
        path = Path.cwd()/'artifacts'/args.task_id/'result.json'
        if not path.is_file():
            raise ValueError('Task result was not found.')
        print(path.read_text())
        return 0
    if args.command == 'status':
        client = node.create_client(Trigger, '/skills/status')
        end = time.monotonic() + args.wait
        while True:
            response = None
            if client.wait_for_service(timeout_sec=2):
                response = wait(node, client.call_async(Trigger.Request()), 5)
            if response and response.success:
                print(response.message)
                return 0
            if time.monotonic() >= end:
                print(response.message if response else 'Skill server unavailable.', file=sys.stderr)
                return 1
            time.sleep(1)
    if args.command in ['pick', 'stack']:
        client = ActionClient(node, PickPlace, '/skills/pick_place')
        if not client.wait_for_server(timeout_sec=10):
            raise RuntimeError('Pick/place action unavailable.')
        goal = PickPlace.Goal(block=args.name, evidence=args.evidence)
        if args.command == 'stack':
            goal.support_block = args.support
        else:
            goal.target = target(args)
        handle = wait(node, client.send_goal_async(goal, feedback_callback=lambda f:
            print(f'{f.feedback.progress:.0%} {f.feedback.stage}: {f.feedback.message}', flush=True)), 10)
        if not handle.accepted:
            raise RuntimeError('Skill rejected: server is busy, not ready, or needs recovery. Run blocks status.')
        future = handle.get_result_async()
        start, canceled = time.monotonic(), False
        try:
            while not future.done():
                rclpy.spin_once(node, timeout_sec=0.2)
                if args.cancel_after and not canceled and time.monotonic()-start > args.cancel_after:
                    wait(node, handle.cancel_goal_async(), 10)
                    canceled = True
                if time.monotonic()-start > 360:
                    wait(node, handle.cancel_goal_async(), 10)
                    wait(node, future, 20)
                    raise TimeoutError('Skill exceeded 360 seconds and was canceled.')
        except KeyboardInterrupt:
            wait(node, handle.cancel_goal_async(), 10)
            wait(node, future, 20)
        result = future.result().result
        p = result.final_pose.pose.position
        print(json.dumps({'success': result.success, 'code': result.code, 'message': result.message,
                          'holding_block': result.holding_block, 'position': [p.x, p.y, p.z],
                          'task_id': result.task_id, 'verified': result.verified,
                          'already_complete': result.already_complete,
                          'evidence_files': list(result.evidence_files), 'report_file': result.report_file}, indent=2))
        return 0 if result.success else 1
    client = node.create_client(Blocks, '/blocks')
    if not client.wait_for_service(timeout_sec=10):
        raise RuntimeError('Block service unavailable.')
    request = Blocks.Request(operation='spawn_random' if args.command == 'add' else args.command)
    if args.command == 'add':
        request.name, request.color = args.name, args.color
        request.seed = args.seed if args.seed is not None else secrets.randbits(63)
    if args.command in ['spawn', 'move']:
        request.name, request.pose = args.name, target(args)
        if args.command == 'spawn':
            request.color = args.color
    if args.command == 'randomize':
        request.seed = args.seed
    result = wait(node, client.call_async(request), 60)
    if not result.success:
        raise RuntimeError(result.message)
    if args.command == 'add':
        print(result.message, file=sys.stderr)
    print(json.dumps([{'name': b.name, 'color': b.color,
                      'position': [b.pose.pose.position.x, b.pose.pose.position.y, b.pose.pose.position.z],
                      'orientation': [b.pose.pose.orientation.x, b.pose.pose.orientation.y, b.pose.pose.orientation.z, b.pose.pose.orientation.w]}
                     for b in result.blocks], indent=2))
    return 0


def main():
    args = parser().parse_args()
    rclpy.init(args=[])
    node = Node('block_client')
    code = 1
    try:
        code = run(node, args)
    except (RuntimeError, TimeoutError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    sys.exit(code)
