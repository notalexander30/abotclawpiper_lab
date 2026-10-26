"""Ensure the real ROS node can construct before launching Gazebo."""
from pathlib import Path
import pytest

rclpy = pytest.importorskip('rclpy')
pytest.importorskip('block_interfaces.action')
from block_skills.server import Server


def test_server_constructs_without_simulation(monkeypatch):
    config = Path(__file__).parents[1] / 'config' / 'blocks.json'
    monkeypatch.setenv('ROS_DOMAIN_ID', '213')
    rclpy.init(args=['--ros-args', '-p', f'config:={config}'])
    node = None
    try:
        node = Server()
        assert not node.ready
        assert node.get_name() == 'block_skills'
    finally:
        if node:
            node.action.destroy()
            node.destroy_node()
        rclpy.shutdown()
