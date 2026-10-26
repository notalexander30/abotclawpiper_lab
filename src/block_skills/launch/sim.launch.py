"""Reuse IFRA's URDF, SRDF, limits and controllers with a configurable world."""
import os
import tempfile
import yaml
import xacro
from ament_index_python.packages import get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from block_skills.geometry import load_config, world_sdf


def read_yaml(package, path):
    with open(os.path.join(share(package), path)) as stream:
        return yaml.safe_load(stream)


def setup(context):
    config_path = LaunchConfiguration('config').perform(context)
    config = load_config(config_path)
    world_path = os.path.join(tempfile.mkdtemp(prefix='ur10e_'), 'table.world')
    with open(world_path, 'w') as stream:
        stream.write(world_sdf(config))
    rviz_config = read_yaml('ros2srrc_moveit', 'config/ros2srrc.rviz')
    for display in rviz_config['Visualization Manager']['Displays']:
        if display.get('Class') == 'moveit_rviz_plugin/MotionPlanning':
            display['Planning Request']['Planning Group'] = 'ur10e_arm'
            display['Planning Request']['Query Goal State'] = True
            display['Scene Geometry']['Scene Alpha'] = 0.35
            display['Velocity_Scaling_Factor'] = 0.2
            display['Acceleration_Scaling_Factor'] = 0.2
    rviz_config['Panels'] = [{'Class': 'rviz_common/Displays', 'Name': 'Displays'}]
    rviz_path = os.path.join(os.path.dirname(world_path), 'robot.rviz')
    with open(rviz_path, 'w') as stream:
        yaml.safe_dump(rviz_config, stream)
    urdf = xacro.process_file(os.path.join(share('ros2srrc_ur10e'), 'urdf', 'ur10e_robotiq_2f85.urdf.xacro'),
                              mappings={'EE': 'true', 'EE_name': 'robotiq_2f85', 'prefix': ''}).toxml()
    semantic = xacro.process_file(os.path.join(share('ros2srrc_moveit'), 'config', 'ur10e_robotiq_2f85.srdf'),
                                 mappings={'prefix': '', 'name': 'ur10e'})
    semantic.documentElement.setAttribute('name', 'ur10e')
    # IFRA's SRDF virtual joint targets base_link although its URDF already has
    # a fixed world->stand->base chain. Remove only the redundant generated tag.
    for joint in list(semantic.getElementsByTagName('virtual_joint')):
        joint.parentNode.removeChild(joint)
    limits = read_yaml('ros2srrc_robots', 'ur10e/config/joint_limits.yaml')
    limits['joint_limits'].update(read_yaml('ros2srrc_endeffectors', 'robotiq_2f85/config/joint_limits.yaml')['joint_limits'])
    limits.update(read_yaml('ros2srrc_robots', 'ur10e/config/pilz_cartesian_limits.yaml'))
    kinematics = read_yaml('ros2srrc_robots', 'ur10e/config/kinematics.yaml')
    kinematics['ur10e_arm']['kinematics_solver_timeout'] = 0.1
    controllers = read_yaml('ros2srrc_robots', 'ur10e/config/controller_moveit2.yaml')
    controllers['controller_names'] = ['joint_trajectory_controller']
    controllers.pop('scaled_joint_trajectory_controller', None)
    grippers = read_yaml('ros2srrc_endeffectors', 'robotiq_2f85/config/controller_moveit2.yaml')
    controllers['controller_names'] += grippers['controller_names']
    controllers.update({k: v for k, v in grippers.items() if k != 'controller_names'})
    robot = {'robot_description': urdf, 'robot_description_semantic': semantic.toxml(),
             'robot_description_kinematics': kinematics, 'robot_description_planning': limits,
             'use_sim_time': True}
    planning = {
        'planning_pipelines': ['ompl', 'pilz'], 'default_planning_pipeline': 'ompl',
        'ompl': {
            'planning_plugin': 'ompl_interface/OMPLPlanner',
            'request_adapters': 'default_planner_request_adapters/AddTimeOptimalParameterization default_planner_request_adapters/ResolveConstraintFrames default_planner_request_adapters/FixWorkspaceBounds default_planner_request_adapters/FixStartStateBounds default_planner_request_adapters/FixStartStateCollision default_planner_request_adapters/FixStartStatePathConstraints',
            'start_state_max_bounds_error': 0.1,
            'planner_configs': {'RRTConnect': {'type': 'geometric::RRTConnect', 'range': 0.0}},
            'ur10e_arm': {'planner_configs': ['RRTConnect'], 'longest_valid_segment_fraction': 0.005},
        },
        'pilz': {'planning_plugin': 'pilz_industrial_motion_planner/CommandPlanner',
                 'request_adapters': '', 'default_planner_config': 'PTP'},
        'moveit_controller_manager': 'moveit_simple_controller_manager/MoveItSimpleControllerManager',
        'moveit_simple_controller_manager': controllers,
        'trajectory_execution.allowed_execution_duration_scaling': 2.0,
        'trajectory_execution.allowed_goal_duration_margin': 2.0,
        'trajectory_execution.allowed_start_tolerance': 0.02,
        'publish_planning_scene': True, 'publish_geometry_updates': True,
        'publish_state_updates': True, 'publish_transforms_updates': True,
    }
    gazebo = IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(share('gazebo_ros'), 'launch', 'gazebo.launch.py')),
        launch_arguments={'world': world_path, 'gui': LaunchConfiguration('gui'), 'verbose': 'false'}.items())
    nodes = [gazebo,
        Node(package='robot_state_publisher', executable='robot_state_publisher', parameters=[robot], output='log'),
        Node(package='gazebo_ros', executable='spawn_entity.py', arguments=['-topic', 'robot_description', '-entity', 'ur10e'], output='screen'),
        Node(package='controller_manager', executable='spawner', arguments=[
            'joint_state_broadcaster', 'joint_trajectory_controller', *grippers['controller_names'],
            '--controller-manager-timeout', '120'], output='screen'),
        Node(package='moveit_ros_move_group', executable='move_group', parameters=[robot, planning], output='log'),
        Node(package='block_skills', executable='server', parameters=[{'config': config_path, 'use_sim_time': True}], output='screen'),
        Node(package='rviz2', executable='rviz2', condition=IfCondition(LaunchConfiguration('rviz')),
             arguments=['-d', rviz_path],
             parameters=[robot, planning], output='log'),
    ]
    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('config', default_value=os.path.join(share('block_skills'), 'config', 'blocks.json')),
        OpaqueFunction(function=setup),
    ])
