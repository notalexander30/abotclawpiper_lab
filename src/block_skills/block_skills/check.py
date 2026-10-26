"""Integration checks against a running simulation; never substitutes for Gazebo."""
import math
import sys
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from block_interfaces.srv import Blocks
from block_interfaces.action import PickPlace
from geometry_msgs.msg import PoseStamped
from std_srvs.srv import Trigger
from block_skills.cli import wait


def main():
    rclpy.init()
    node = Node('simulation_checks')
    try:
        status = node.create_client(Trigger, '/skills/status')
        assert status.wait_for_service(timeout_sec=15), 'Missing skill status service'
        assert wait(node, status.call_async(Trigger.Request()), 10).success, 'Server not ready'
        blocks = node.create_client(Blocks, '/blocks')
        assert blocks.wait_for_service(timeout_sec=5)
        snapshot = wait(node, blocks.call_async(Blocks.Request(operation='list')), 15)
        assert snapshot.success and len(snapshot.blocks) >= 3
        assert {'red', 'blue', 'green'}.issubset({b.color for b in snapshot.blocks})
        for block in snapshot.blocks:
            assert block.pose.header.frame_id == 'world'
            assert abs(block.pose.pose.position.z-0.675) < 0.01
        print('PASS: readiness, Gazebo block poses and initial colors', flush=True)
        action = ActionClient(node, PickPlace, '/skills/pick_place')
        assert action.wait_for_server(timeout_sec=5)
        target = PoseStamped()
        target.header.frame_id = 'world'
        target.pose.position.x, target.pose.position.y, target.pose.position.z = 10.0, 0.0, 0.675
        target.pose.orientation.w = 1.0
        for selector, expected in [('missing_block', 'UNKNOWN_BLOCK'), ('red_block', 'INVALID_REQUEST')]:
            handle = wait(node, action.send_goal_async(PickPlace.Goal(block=selector, target=target)), 10)
            assert handle.accepted
            result = wait(node, handle.get_result_async(), 20).result
            assert not result.success and result.code == expected, result
        print('PASS: unknown block and unreachable target rejected', flush=True)
        # Full physical pick/place: no teleporting or mocked planner.
        target.pose.position.x, target.pose.position.y = 0.82, -0.28
        handle = wait(node, action.send_goal_async(PickPlace.Goal(block='red_block', target=target),
            feedback_callback=lambda f: print(f.feedback.stage, flush=True)), 10)
        assert handle.accepted
        result = wait(node, handle.get_result_async(), 300).result
        assert result.success and not result.holding_block, result
        final = wait(node, blocks.call_async(Blocks.Request(operation='list')), 15)
        red = next(b for b in final.blocks if b.name == 'red_block').pose.pose.position
        assert math.dist([red.x, red.y, red.z], [0.82, -0.28, 0.675]) < 0.02
        print('PASS: physical pick, attach, transport, detach, placement verification', flush=True)
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        raise
    finally:
        node.destroy_node()
        rclpy.shutdown()
