import math
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from block_skills.geometry import (load_config, validate_position, upright_yaw,
    random_positions, random_free_position, support_chain, check_spacing, yaw_quat, multiply, rotate, block_sdf, world_sdf)


@pytest.fixture
def config():
    return load_config(Path(__file__).parents[1] / 'config' / 'blocks.json')


def test_workspace_rejects_unreachable_nonfinite_and_stacked(config):
    for point in [[4, 0, .675], [.6, float('nan'), .675], [.6, 0, 1.0], [.6, 0, .6]]:
        with pytest.raises(ValueError):
            validate_position(config, point)
    validate_position(config, [.6, 0, .675])


def test_orientation_and_tool_axis():
    with pytest.raises(ValueError):
        upright_yaw([0, 0, 0, 0])
    with pytest.raises(ValueError):
        upright_yaw([math.sqrt(.5), 0, 0, math.sqrt(.5)])
    q = multiply(yaw_quat(1.1), [0, math.sqrt(.5), 0, math.sqrt(.5)])
    assert rotate(q, [1, 0, 0]) == pytest.approx([0, 0, -1])
    assert upright_yaw(yaw_quat(-2.2)) == pytest.approx(-2.2)


def test_random_layouts_are_repeatable_and_spaced(config):
    assert random_positions(config, 5, 42) == random_positions(config, 5, 42)
    for seed in range(20):
        positions = []
        for point, yaw in random_positions(config, 5, seed):
            validate_position(config, point)
            check_spacing(config, point, positions)
            positions.append(point)
            assert -math.pi <= yaw <= math.pi
    with pytest.raises(ValueError):
        random_positions(config, 100, 42)


def test_world_contains_state_and_attacher_plugins(config):
    root = ET.fromstring(world_sdf(config))
    plugins = {p.attrib['filename'] for p in root.findall('world/plugin')}
    assert plugins == {'libgazebo_ros_state.so', 'libgazebo_link_attacher.so'}
    assert root.find("world/model[@name='table']") is not None
    block = ET.fromstring(block_sdf('red_block', .05, [1, 0, 0, 1]))
    assert block.find('model/link').attrib['name'] == 'link'


def test_random_add_preserves_occupied_locations(config):
    occupied = [b['position'][:] for b in config['blocks']]
    original = [p[:] for p in occupied]
    point, yaw = random_free_position(config, occupied, 42)
    validate_position(config, point)
    check_spacing(config, point, occupied)
    assert occupied == original
    assert (point, yaw) == random_free_position(config, occupied, 42)
    crowded = [[x/100, y/100, .675] for x in range(38, 96, 4) for y in range(-45, 46, 4)]
    with pytest.raises(ValueError, match='No free spawn location'):
        random_free_position(config, crowded, 1)


def test_stack_requires_grounded_aligned_supports(config):
    positions = {'red': [.55, -.28, .675], 'blue': [.55, -.28, .725], 'green': [.55, -.28, .775]}
    assert support_chain(config, 'green', positions) == ['green', 'blue', 'red']
    with pytest.raises(ValueError, match='no unique supporting'):
        support_chain(config, 'green', {'green': positions['green'], 'red': positions['red']})
    with pytest.raises(ValueError, match='no unique supporting'):
        support_chain(config, 'blue', {'blue': [.57, -.28, .725], 'red': positions['red']})
    with pytest.raises(ValueError):
        support_chain(config, 'green', {'green': [.55, -.28, 2.0]})
