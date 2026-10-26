"""Pure geometry/validation shared by the node, CLI and tests (metres/radians)."""
import json
import math
import random
import re
from xml.sax.saxutils import escape


def table_top(config):
    return config['table']['center'][2] + config['table']['size'][2] / 2


def table_legs(config):
    center, size = config['table']['center'], config['table']['size']
    height = center[2] - size[2]/2
    return [([center[0]+sx*(size[0]/2-.05), center[1]+sy*(size[1]/2-.05), height/2], [.05, .05, height])
            for sx in [-1, 1] for sy in [-1, 1]]


def yaw_quat(yaw):
    return [0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)]


def multiply(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return [w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z]


def rotate(q, point):
    return multiply(multiply(q, list(point) + [0.0]), [-q[0], -q[1], -q[2], q[3]])[:3]


def upright_yaw(q):
    if not all(math.isfinite(v) for v in q) or abs(sum(v*v for v in q)-1) > 0.01:
        raise ValueError('Orientation must be a finite unit quaternion.')
    if rotate(q, [0, 0, 1])[2] < math.cos(0.12):
        raise ValueError('Only upright blocks are supported; roll/pitch must be near zero.')
    x, y, z, w = q
    return math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))


def validate_position(config, xyz):
    if len(xyz) != 3 or not all(math.isfinite(v) for v in xyz):
        raise ValueError('Coordinates must be three finite numbers.')
    for value, axis in zip(xyz[:2], ['x', 'y']):
        lo, hi = config['workspace'][axis]
        if not lo <= value <= hi:
            raise ValueError(f'Unreachable/outside configured table workspace: {axis}={value}, allowed [{lo}, {hi}].')
    expected_z = table_top(config) + config['block_size']/2
    if abs(xyz[2]-expected_z) > 0.008:
        raise ValueError(f'Block centre z must be {expected_z:.3f} m for table placement; use the stack skill to place on another block.')


def validate_name(name):
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', name):
        raise ValueError('Use a model name starting with a lowercase letter, then letters, digits or underscores (max 48).')


def check_spacing(config, xyz, positions):
    for other in positions:
        if math.hypot(xyz[0]-other[0], xyz[1]-other[1]) < config['workspace']['spacing']:
            raise ValueError('Location is too close to another block; use the configured minimum spacing.')


def random_positions(config, count, seed):
    rng = random.Random(seed)
    positions = []
    for _ in range(count):
        for attempt in range(2000):
            xyz = [rng.uniform(*config['workspace'][a]) for a in ['x', 'y']]
            xyz.append(table_top(config) + config['block_size']/2)
            try:
                check_spacing(config, xyz, positions)
                positions.append(xyz)
                break
            except ValueError:
                continue
        else:
            raise ValueError('Too many blocks for this workspace and spacing; no changes made.')
    return [(p, rng.uniform(-math.pi, math.pi)) for p in positions]


def random_free_position(config, occupied, seed):
    """Sample one new location without repositioning any existing blocks."""
    rng = random.Random(seed)
    for _ in range(2000):
        point = [rng.uniform(*config['workspace'][axis]) for axis in ['x', 'y']]
        point.append(table_top(config) + config['block_size']/2)
        try:
            check_spacing(config, point, occupied)
            return point, rng.uniform(-math.pi, math.pi)
        except ValueError:
            continue
    raise ValueError('No free spawn location found; existing blocks were not moved.')


def support_chain(config, name, positions):
    """Return a top-to-bottom chain grounded on the table, never a floating stack."""
    chain = [name]
    size = config['block_size']
    base_z = table_top(config) + size/2
    while True:
        point = positions[chain[-1]]
        validate_position(config, [point[0], point[1], base_z])
        if abs(point[2]-base_z) < .006:
            return chain
        if point[2] < base_z or len(chain) >= config.get('max_stack_height', 3):
            raise ValueError('Block is below the table or exceeds the supported stack height.')
        parents = [other for other, p in positions.items() if other not in chain
                   and abs(point[2]-p[2]-size) < .006
                   and math.hypot(point[0]-p[0], point[1]-p[1]) < .006]
        if len(parents) != 1:
            raise ValueError('Block is floating, off-centre, or has no unique supporting block.')
        chain.append(parents[0])


def load_config(path):
    with open(path) as stream:
        config = json.load(stream)
    if config['frame'] != 'world':
        raise ValueError('This simulation uses the Gazebo world frame.')
    if not 0.025 <= config['block_size'] <= 0.06:
        raise ValueError('Block size must be between 0.025 and 0.06 m for this gripper.')
    if config['workspace']['spacing'] < config['block_size'] * 2:
        raise ValueError('Spacing must be at least twice the block size.')
    names, positions = set(), []
    for block in config['blocks']:
        validate_name(block['name'])
        if block['name'] in names or block['color'] not in config['colors']:
            raise ValueError('Duplicate block name or unknown color.')
        names.add(block['name'])
        validate_position(config, block['position'])
        check_spacing(config, block['position'], positions)
        positions.append(block['position'])
    return config


def block_sdf(name, size, color):
    validate_name(name)
    inertia = 0.1*size*size/6
    rgba = ' '.join(str(v) for v in color)
    return f'''<sdf version="1.6"><model name="{escape(name)}"><link name="link">
      <inertial><mass>0.1</mass><inertia><ixx>{inertia}</ixx><iyy>{inertia}</iyy><izz>{inertia}</izz></inertia></inertial>
      <collision name="collision"><max_contacts>8</max_contacts><geometry><box><size>{size} {size} {size}</size></box></geometry>
        <surface><friction><ode><mu>0.8</mu><mu2>0.8</mu2></ode></friction>
          <contact><ode><kp>100000</kp><kd>100</kd><max_vel>0.02</max_vel><min_depth>0.0001</min_depth></ode></contact>
          <bounce><restitution_coefficient>0</restitution_coefficient><threshold>0.001</threshold></bounce>
        </surface></collision>
      <visual name="visual"><geometry><box><size>{size} {size} {size}</size></box></geometry>
        <material><ambient>{rgba}</ambient><diffuse>{rgba}</diffuse></material></visual>
    </link></model></sdf>'''


def world_sdf(config):
    center = ' '.join(map(str, config['table']['center']))
    size = ' '.join(map(str, config['table']['size']))
    legs = ''
    for index, (position, dimensions) in enumerate(table_legs(config)):
        p, d = ' '.join(map(str, position)), ' '.join(map(str, dimensions))
        legs += f'''<model name="table_leg_{index}"><static>true</static><pose>{p} 0 0 0</pose><link name="link">
          <collision name="collision"><geometry><box><size>{d}</size></box></geometry></collision>
          <visual name="visual"><geometry><box><size>{d}</size></box></geometry><material><ambient>0.25 0.25 0.3 1</ambient></material></visual>
        </link></model>'''
    return f'''<sdf version="1.6"><world name="default">
      <gravity>0 0 -9.81</gravity>
      <physics type="ode"><max_step_size>0.001</max_step_size><real_time_update_rate>1000</real_time_update_rate>
        <ode><solver><type>quick</type><iters>100</iters><sor>1.0</sor></solver></ode>
      </physics>
      <light name="sun" type="directional"><pose>0 0 10 0 0 0</pose><diffuse>0.9 0.9 0.9 1</diffuse><direction>-0.5 0.2 -1</direction></light>
      <scene><ambient>0.5 0.5 0.5 1</ambient><background>0.75 0.8 0.85 1</background></scene>
      <model name="ground"><static>true</static><link name="link">
        <collision name="collision"><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry></collision>
        <visual name="visual"><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry><material><ambient>0.5 0.5 0.5 1</ambient></material></visual>
      </link></model>
      <model name="table"><static>true</static><pose>{center} 0 0 0</pose><link name="link">
        <collision name="collision"><geometry><box><size>{size}</size></box></geometry></collision>
        <visual name="visual"><geometry><box><size>{size}</size></box></geometry><material><ambient>0.5 0.35 0.2 1</ambient><diffuse>0.5 0.35 0.2 1</diffuse></material></visual>
      </link></model>
      {legs}
      <plugin name="gazebo_ros_state" filename="libgazebo_ros_state.so"><ros><namespace>/gazebo</namespace></ros><update_rate>30</update_rate></plugin>
      <plugin name="gazebo_link_attacher" filename="libgazebo_link_attacher.so"/>
      <gui><camera name="camera"><pose>2.5 -2.5 2.0 0 0.35 2.35</pose></camera></gui>
    </world></sdf>'''
