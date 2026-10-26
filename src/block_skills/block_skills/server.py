"""Serialized, cancellable pick/place using standard MoveIt and Gazebo APIs.

Blocking waits run in a reentrant callback group with a multithreaded executor;
future completion and cancellation always have executor threads available.
"""
import copy
import math
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from action_msgs.msg import GoalStatus
from control_msgs.action import GripperCommand
from geometry_msgs.msg import Pose, PoseStamped, Quaternion
from gazebo_msgs.srv import GetEntityState, SetEntityState, SpawnEntity
from linkattacher_msgs.srv import AttachLink, DetachLink
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import (AttachedCollisionObject, CollisionObject, Constraints,
                            OrientationConstraint, PositionConstraint, PlanningScene,
                            AllowedCollisionEntry, PlanningSceneComponents)
from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from std_srvs.srv import Trigger
from block_interfaces.action import PickPlace
from block_interfaces.msg import Block
from block_interfaces.srv import Blocks
from block_skills.geometry import (load_config, table_top, table_legs, yaw_quat, multiply, rotate,
    upright_yaw, validate_position, validate_name, check_spacing, random_positions, random_free_position, support_chain, block_sdf)
from block_skills.reports import timestamp, pose_record, write_report

EE = 'EE_robotiq_2f85'
TOUCH = ['robotiq_85_left_finger_tip_link', 'robotiq_85_right_finger_tip_link',
         'robotiq_85_left_finger_link', 'robotiq_85_right_finger_link', EE]


class SkillError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def xyz(pose):
    return [pose.position.x, pose.position.y, pose.position.z]


def quat(pose):
    return [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]


def pose_at(position, orientation=None):
    pose = Pose()
    pose.position.x, pose.position.y, pose.position.z = map(float, position)
    pose.orientation = Quaternion(**dict(zip(['x', 'y', 'z', 'w'], map(float, orientation or [0, 0, 0, 1]))))
    return pose


class Server(Node):
    def __init__(self):
        super().__init__('block_skills')
        self.config = load_config(self.declare_parameter('config', '').value)
        self.artifact_dir = Path(self.declare_parameter('artifact_dir', str(Path.cwd()/'artifacts')).value)
        self.group = ReentrantCallbackGroup()
        self.lock = threading.Lock()
        self.ready = False
        self.initializing = False
        self.fault = ''
        self.held = ''
        self.grasp_transform = None
        self.registry = {}
        self.active = None
        self.joint_received = 0.0
        self.create_subscription(JointState, '/joint_states', self.joints, 10, callback_group=self.group)
        self.service_clients = {}
        for name, kind in [('/gazebo/get_entity_state', GetEntityState),
                           ('/gazebo/set_entity_state', SetEntityState),
                           ('/spawn_entity', SpawnEntity), ('/ATTACHLINK', AttachLink),
                           ('/DETACHLINK', DetachLink), ('/apply_planning_scene', ApplyPlanningScene),
                           ('/get_planning_scene', GetPlanningScene)]:
            self.service_clients[name] = self.create_client(kind, name, callback_group=self.group)
        self.move = ActionClient(self, MoveGroup, '/move_action', callback_group=self.group)
        self.grippers = [ActionClient(self, GripperCommand, f'/robotiq_controller_{suffix}/gripper_cmd', callback_group=self.group)
                         for suffix in ['LKJ', 'RKJ', 'LIKJ', 'RIKJ', 'LFTJ', 'RFTJ']]
        self.create_service(Blocks, '/blocks', self.blocks, callback_group=self.group)
        self.create_service(Trigger, '/skills/status', self.status, callback_group=self.group)
        self.action = ActionServer(self, PickPlace, '/skills/pick_place', execute_callback=self.execute,
            goal_callback=self.accept, cancel_callback=lambda _: CancelResponse.ACCEPT, callback_group=self.group)
        self.timer = self.create_timer(1.0, self.initialize, callback_group=self.group,
                                       clock=rclpy.clock.Clock(clock_type=rclpy.clock.ClockType.STEADY_TIME))

    def joints(self, msg):
        if 'shoulder_pan_joint' in msg.name:
            self.joint_received = time.monotonic()

    def wait(self, future, timeout=15.0, cancellable=False):
        end = time.monotonic() + timeout
        while rclpy.ok() and not future.done():
            if cancellable:
                self.check_cancel()
            if time.monotonic() > end:
                raise SkillError('TIMEOUT', 'Timed out waiting for a simulation/planning response.')
            time.sleep(0.02)
        if not rclpy.ok():
            raise SkillError('SHUTDOWN', 'ROS is shutting down.')
        return future.result()

    def call(self, name, request, timeout=15.0):
        client = self.service_clients[name]
        if not client.wait_for_service(timeout_sec=2.0):
            raise SkillError('UNAVAILABLE', f'Service unavailable: {name}')
        try:
            return self.wait(client.call_async(request), timeout)
        except SkillError as exc:
            if exc.code == 'TIMEOUT' and name not in ['/gazebo/get_entity_state', '/get_planning_scene']:
                self.fault = f'Outcome of {name} is uncertain after timeout; restart simulation.'
            raise

    def state(self, name):
        result = self.call('/gazebo/get_entity_state', GetEntityState.Request(name=name, reference_frame='world'))
        if not result.success:
            raise SkillError('MISSING_MODEL', f'Gazebo entity not found: {name}')
        return result.state

    def stamped(self, pose):
        result = PoseStamped()
        result.header.frame_id = 'world'
        result.header.stamp = self.get_clock().now().to_msg()
        result.pose = pose
        return result

    def initialize(self):
        if self.ready or self.initializing or self.fault:
            return
        if not all(c.service_is_ready() for c in self.service_clients.values()) or not self.move.server_is_ready():
            return
        if not all(c.server_is_ready() for c in self.grippers) or not self.joint_received:
            return
        self.initializing = True
        try:
            for block in self.config['blocks']:
                self.spawn(block['name'], block['color'], pose_at(block['position'], yaw_quat(block.get('yaw', 0))))
            time.sleep(1)
            self.sync_scene()
            self.ready = True
            self.timer.cancel()
            self.get_logger().info('READY: UR10e + Robotiq 2F-85; /blocks and /skills/pick_place available.')
        except Exception as exc:
            self.fault = str(exc)
            self.get_logger().error(f'Initialization failed: {exc}')

    def status(self, _, response):
        response.success = self.ready and not self.fault and time.monotonic()-self.joint_received < 3
        response.message = f'ready={self.ready}; busy={self.lock.locked()}; holding={self.held or "none"}; fault={self.fault or "none"}'
        return response

    def spawn(self, name, color, pose):
        validate_name(name)
        if color not in self.config['colors']:
            raise ValueError(f'Unknown color {color}; add it to blocks.json first.')
        if name in self.registry:
            raise ValueError(f'Block {name} already exists.')
        request = SpawnEntity.Request(name=name,
            xml=block_sdf(name, self.config['block_size'], self.config['colors'][color]), initial_pose=pose,
            reference_frame='world')
        result = self.call('/spawn_entity', request)
        if not result.success:
            raise SkillError('SPAWN_FAILED', result.status_message)
        self.registry[name] = color

    def block_list(self):
        result = []
        for name, color in self.registry.items():
            result.append(Block(name=name, color=color, size=self.config['block_size'], pose=self.stamped(self.state(name).pose)))
        return result

    def blocks(self, request, response):
        # All reads and mutations serialize with skills, so clients never receive
        # a mixed snapshot or reposition a block while the robot is carrying it.
        if not self.ready:
            response.message = f'Not ready: {self.fault or "waiting for simulation"}'
            return response
        if not self.lock.acquire(blocking=False):
            response.message = 'BUSY: wait for the active skill.'
            return response
        try:
            if self.held or self.fault:
                raise ValueError(f'Restart simulation to recover: holding={self.held}, fault={self.fault}')
            if request.operation == 'list':
                pass
            elif request.operation == 'spawn_random':
                if request.color not in self.config['colors']:
                    raise ValueError(f'Unknown color {request.color}; add it to blocks.json first.')
                name = request.name or f'{request.color}_block'
                if not request.name:
                    index = 2
                    while name in self.registry:
                        name = f'{request.color}_block_{index}'
                        index += 1
                validate_name(name)
                if name in self.registry:
                    raise ValueError(f'Block {name} already exists.')
                point, yaw = random_free_position(self.config, [xyz(b.pose.pose) for b in self.block_list()], request.seed)
                self.spawn(name, request.color, pose_at(point, yaw_quat(yaw)))
            elif request.operation in ['spawn', 'move']:
                if request.pose.header.frame_id != 'world':
                    raise ValueError('frame_id must be world.')
                validate_position(self.config, xyz(request.pose.pose))
                upright_yaw(quat(request.pose.pose))
                current = self.block_list()
                check_spacing(self.config, xyz(request.pose.pose), [xyz(b.pose.pose) for b in current if b.name != request.name])
                if request.operation == 'spawn':
                    self.spawn(request.name, request.color, request.pose.pose)
                else:
                    if request.name not in self.registry:
                        raise ValueError('Unknown block model name.')
                    self.set_pose(request.name, request.pose.pose)
            elif request.operation == 'randomize':
                poses = random_positions(self.config, len(self.registry), request.seed)
                for name, (position, yaw) in zip(self.registry, poses):
                    self.set_pose(name, pose_at(position, yaw_quat(yaw)))
            else:
                raise ValueError('operation must be list, spawn, spawn_random, move or randomize.')
            if request.operation != 'list':
                time.sleep(0.5)
                self.sync_scene()
            response.blocks = self.block_list()
            response.success = True
            response.message = request.operation + ' complete'
        except Exception as exc:
            response.message = str(exc)
        finally:
            self.lock.release()
        return response

    def set_pose(self, name, pose):
        request = SetEntityState.Request()
        request.state.name = name
        request.state.pose = pose
        request.state.reference_frame = 'world'
        if not self.call('/gazebo/set_entity_state', request).success:
            raise SkillError('STATE_FAILED', f'Could not reposition {name}')

    def box(self, name, size, pose, frame='world'):
        obj = CollisionObject()
        obj.id, obj.header.frame_id = name, frame
        obj.operation = CollisionObject.ADD
        obj.primitives = [SolidPrimitive(type=SolidPrimitive.BOX, dimensions=list(map(float, size)))]
        obj.primitive_poses = [pose]
        return obj

    def apply(self, scene):
        scene.is_diff = True
        scene.robot_state.is_diff = True
        if not self.call('/apply_planning_scene', ApplyPlanningScene.Request(scene=scene)).success:
            raise SkillError('SCENE_FAILED', 'MoveIt rejected the planning scene update.')

    def sync_scene(self):
        scene = PlanningScene()
        scene.world.collision_objects = [self.box('table', self.config['table']['size'], pose_at(self.config['table']['center'])),
            self.box('floor', [6, 6, 0.02], pose_at([0, 0, -0.02]))]
        for index, (position, dimensions) in enumerate(table_legs(self.config)):
            scene.world.collision_objects.append(self.box(f'table_leg_{index}', dimensions, pose_at(position)))
        for name in self.registry:
            if name != self.held:
                scene.world.collision_objects.append(self.box(name, [self.config['block_size']]*3, self.state(name).pose))
        self.apply(scene)

    def allow_touch(self, name, allow):
        request = GetPlanningScene.Request()
        request.components.components = PlanningSceneComponents.ALLOWED_COLLISION_MATRIX
        matrix = self.call('/get_planning_scene', request).scene.allowed_collision_matrix
        for link in [name] + TOUCH:
            if link not in matrix.entry_names:
                matrix.entry_names.append(link)
                for row in matrix.entry_values:
                    row.enabled.append(False)
                matrix.entry_values.append(AllowedCollisionEntry(enabled=[False]*len(matrix.entry_names)))
        index = matrix.entry_names.index(name)
        for link in TOUCH:
            other = matrix.entry_names.index(link)
            matrix.entry_values[index].enabled[other] = allow
            matrix.entry_values[other].enabled[index] = allow
        scene = PlanningScene(allowed_collision_matrix=matrix)
        self.apply(scene)

    def attach(self, name):
        request = AttachLink.Request(model1_name='ur10e', link1_name=EE, model2_name=name, link2_name='link')
        # Conservatively report held if the response is lost after Gazebo attaches.
        self.held = name
        result = self.call('/ATTACHLINK', request)
        if not result.success:
            self.held = ''
            raise SkillError('ATTACH_FAILED', result.message)
        self.held = name  # Preserve physical attachment state even if MoveIt update fails.
        ee_pose, block_pose = self.state('ur10e::'+EE).pose, self.state(name).pose
        inverse = [-v for v in quat(ee_pose)[:3]] + [ee_pose.orientation.w]
        relative = pose_at(rotate(inverse, [a-b for a, b in zip(xyz(block_pose), xyz(ee_pose))]), multiply(inverse, quat(block_pose)))
        self.grasp_transform = relative
        self.get_logger().info(f'Attachment: block={xyz(block_pose)}, TCP={xyz(ee_pose)}, relative={xyz(relative)}')
        scene = PlanningScene()
        # MoveIt removes the world object automatically when attaching it.
        attached = AttachedCollisionObject(link_name=EE, touch_links=TOUCH,
            object=self.box(name, [self.config['block_size']]*3, relative, EE))
        scene.robot_state.attached_collision_objects = [attached]
        self.apply(scene)

    def detach(self, name):
        request = DetachLink.Request(model1_name='ur10e', link1_name=EE, model2_name=name, link2_name='link')
        result = self.call('/DETACHLINK', request)
        if not result.success:
            raise SkillError('DETACH_FAILED', result.message)
        self.held = ''
        self.grasp_transform = None
        scene = PlanningScene()
        scene.robot_state.attached_collision_objects = [AttachedCollisionObject(link_name=EE, object=CollisionObject(id=name, operation=CollisionObject.REMOVE))]
        scene.world.collision_objects = [self.box(name, [self.config['block_size']]*3, self.state(name).pose)]
        self.apply(scene)

    def accept(self, request):
        if not self.ready or self.fault or self.held or not self.lock.acquire(blocking=False):
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def check_cancel(self):
        if self.active and self.active.is_cancel_requested:
            raise SkillError('CANCELED', 'Skill canceled. Any attached block remains held; restart simulation to recover.')

    def feedback(self, stage, progress, message):
        self.check_cancel()
        self.active.publish_feedback(PickPlace.Feedback(stage=stage, progress=float(progress), message=message))
        self.get_logger().info(f'{stage}: {message}')

    def run_action(self, client, goal, timeout=90):
        self.check_cancel()
        if not client.wait_for_server(timeout_sec=3):
            raise SkillError('UNAVAILABLE', 'Motion action server unavailable.')
        try:
            handle = self.wait(client.send_goal_async(goal))
        except SkillError:
            self.fault = 'Motion acceptance could not be confirmed; restart simulation.'
            raise
        if not handle.accepted:
            raise SkillError('MOTION_REJECTED', 'Motion goal rejected.')
        future = handle.get_result_async()
        try:
            result = self.wait(future, timeout=timeout, cancellable=True)
        except SkillError:
            self.wait(handle.cancel_goal_async(), timeout=5)
            try:
                self.wait(future, timeout=10)
            except SkillError:
                self.fault = 'Motion stop could not be confirmed; restart simulation.'
            raise
        if result.status != GoalStatus.STATUS_SUCCEEDED:
            error = getattr(result.result, 'error_code', None)
            if error is not None:
                no_plan = not result.result.planned_trajectory.joint_trajectory.points
                raise SkillError('PLANNING_FAILED' if no_plan else 'MOTION_FAILED',
                                 f'MoveIt returned error {error.val}; action status {result.status}.')
            raise SkillError('MOTION_FAILED', f'Motion action ended with status {result.status}.')
        return result.result

    def move_to(self, pose, linear=False):
        if time.monotonic()-self.joint_received > 3:
            raise SkillError('STALE_STATE', 'Robot joint state is stale; simulation may be paused.')
        self.sync_scene()
        goal = MoveGroup.Goal()
        request = goal.request
        request.group_name = 'ur10e_arm'
        request.pipeline_id = 'pilz' if linear else 'ompl'
        request.planner_id = 'LIN' if linear else 'RRTConnect'
        request.num_planning_attempts = 5
        request.allowed_planning_time = 8.0
        request.max_velocity_scaling_factor = 0.2
        request.max_acceleration_scaling_factor = 0.2
        request.start_state.is_diff = True
        request.workspace_parameters.header.frame_id = 'world'
        request.workspace_parameters.min_corner.x = -2.0
        request.workspace_parameters.min_corner.y = -2.0
        request.workspace_parameters.min_corner.z = -0.1
        request.workspace_parameters.max_corner.x = 2.0
        request.workspace_parameters.max_corner.y = 2.0
        request.workspace_parameters.max_corner.z = 3.0
        position = PositionConstraint()
        position.header.frame_id, position.link_name, position.weight = 'world', EE, 1.0
        position.constraint_region.primitives = [SolidPrimitive(type=SolidPrimitive.SPHERE, dimensions=[0.002])]
        region_pose = copy.deepcopy(pose)
        region_pose.orientation = Quaternion(w=1.0)
        position.constraint_region.primitive_poses = [region_pose]
        orientation = OrientationConstraint()
        orientation.header.frame_id, orientation.link_name, orientation.weight = 'world', EE, 1.0
        orientation.orientation = pose.orientation
        orientation.absolute_x_axis_tolerance = 0.015
        orientation.absolute_y_axis_tolerance = 0.015
        orientation.absolute_z_axis_tolerance = 0.015
        request.goal_constraints = [Constraints(position_constraints=[position], orientation_constraints=[orientation])]
        goal.planning_options.planning_scene_diff.is_diff = True
        goal.planning_options.planning_scene_diff.robot_state.is_diff = True
        for attempt in range(3):
            try:
                result = self.run_action(self.move, goal)
                break
            except SkillError as exc:
                if exc.code != 'PLANNING_FAILED' or attempt == 2:
                    raise
                self.get_logger().warning(f'Planning attempt {attempt+1} failed; retrying with a fresh scene.')
                self.sync_scene()
        if result.error_code.val != 1:
            raise SkillError('PLANNING_FAILED', f'MoveIt error code {result.error_code.val}')
        actual = self.state('ur10e::'+EE).pose
        if math.dist(xyz(actual), xyz(pose)) > 0.012:
            raise SkillError('TRACKING_FAILED', 'Gripper did not reach the requested pose.')

    def gripper(self, close=False):
        # All six original IFRA gripper controllers move simultaneously.
        # Match the parallel linkage while leaving light contact to LinkAttacher.
        angle = max(0.0, min(0.65, (0.085-self.config['block_size']-0.012)/0.10)) if close else 0.0
        handles = []
        try:
            futures = []
            for i, client in enumerate(self.grippers):
                self.check_cancel()
                goal = GripperCommand.Goal()
                goal.command.position = angle if i < 4 else -angle
                goal.command.max_effort = 20.0
                futures.append(client.send_goal_async(goal))
            for future in futures:
                handle = self.wait(future)
                if not handle.accepted:
                    raise SkillError('GRIPPER_FAILED', 'Gripper controller rejected the goal.')
                handles.append(handle)
            for handle in handles:
                result = self.wait(handle.get_result_async(), timeout=15, cancellable=True)
                if result.status != GoalStatus.STATUS_SUCCEEDED or not result.result.reached_goal:
                    raise SkillError('GRIPPER_FAILED', 'Gripper failed to reach its commanded position.')
        except Exception:
            for handle in handles:
                self.wait(handle.cancel_goal_async(), timeout=5)
            raise

    def resolve(self, selector):
        if selector in self.registry:
            return selector
        matches = [name for name, color in self.registry.items() if color == selector]
        if len(matches) != 1:
            raise SkillError('UNKNOWN_BLOCK' if not matches else 'AMBIGUOUS_BLOCK',
                             f'{selector!r} identifies {len(matches)} blocks; use an exact model name.')
        return matches[0]

    def tool_pose(self, block_pose, height=0):
        yaw = upright_yaw(quat(block_pose))
        if self.held and self.grasp_transform is not None:
            relative = self.grasp_transform
            inverse = [-v for v in quat(relative)[:3]] + [relative.orientation.w]
            orientation = multiply(quat(block_pose), inverse)
            offset = rotate(orientation, xyz(relative))
            position = [a-b for a, b in zip(xyz(block_pose), offset)]
            position[2] += height
            return pose_at(position, orientation)
        # IFRA's TCP +X is the finger approach axis, directed down into the block.
        orientation = multiply(yaw_quat(yaw), [0, math.sqrt(0.5), 0, math.sqrt(0.5)])
        p = xyz(block_pose)
        p[2] += self.config['grasp_offset'] + height
        return pose_at(p, orientation)

    def evidence_capture(self, output=None):
        command = [sys.executable, '-m', 'block_skills.capture']
        if output is not None:
            command += ['--output', str(output)]
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SkillError('EVIDENCE_FAILED', str(exc)) from exc
        if process.returncode:
            raise SkillError('EVIDENCE_UNAVAILABLE' if output is None else 'EVIDENCE_FAILED',
                             process.stderr.strip()[-1500:] or 'Gazebo screenshot capture failed.')

    def ensure_support(self, references):
        records = {}
        for name, expected in references.items():
            state = self.state(name)
            pose = state.pose
            yaw = upright_yaw(quat(pose))
            if (math.dist(xyz(pose), xyz(expected)) > .003
                    or abs(math.remainder(yaw-upright_yaw(quat(expected)), 2*math.pi)) > .05):
                raise SkillError('SUPPORT_MOVED', f'Supporting block {name} moved; placement was not confirmed.')
            speed = math.sqrt(sum(v*v for v in [state.twist.linear.x, state.twist.linear.y, state.twist.linear.z]))
            angular = math.sqrt(sum(v*v for v in [state.twist.angular.x, state.twist.angular.y, state.twist.angular.z]))
            if speed > .01 or angular > .08 or rotate(quat(pose), [0, 0, 1])[2] < math.cos(.04):
                raise SkillError('UNSTABLE_SUPPORT', f'Supporting block {name} is not upright and settled.')
            records[name] = pose_record(self.stamped(pose))
        return records

    def verify_placement(self, name, target, references, result, samples, count=10):
        result.verified = False
        tolerance = self.config.get('stack_position_tolerance', .005) if references else self.config['placement_tolerance']
        for _ in range(count):
            self.check_cancel()
            state = self.state(name)
            result.final_pose = self.stamped(state.pose)
            if math.dist(xyz(state.pose), xyz(target.pose)) > tolerance:
                raise SkillError('PLACEMENT_FAILED', f'Final block centre differs from target: {xyz(state.pose)}')
            yaw_error = abs(math.remainder(upright_yaw(quat(state.pose))-upright_yaw(quat(target.pose)), 2*math.pi))
            if yaw_error > self.config['yaw_tolerance']:
                raise SkillError('PLACEMENT_FAILED', 'Final block orientation is outside tolerance.')
            speed = math.sqrt(sum(v*v for v in [state.twist.linear.x, state.twist.linear.y, state.twist.linear.z]))
            angular = math.sqrt(sum(v*v for v in [state.twist.angular.x, state.twist.angular.y, state.twist.angular.z]))
            if speed > .01 or angular > .08:
                raise SkillError('PLACEMENT_FAILED', 'Block has not settled.')
            if references and rotate(quat(state.pose), [0, 0, 1])[2] < math.cos(.04):
                raise SkillError('PLACEMENT_FAILED', 'Stacked block is tilted.')
            supports = self.ensure_support(references)
            samples.append({'at': timestamp(), 'pose': pose_record(result.final_pose),
                            'linear_speed': speed, 'angular_speed': angular, 'supports': supports})
            if count > 1:
                time.sleep(.2)
        result.verified = True

    def save_task_report(self, result, request, name, support, target, samples, started):
        result.holding_block = bool(self.held)
        write_report(result.report_file, {
            'task_id': result.task_id, 'started_at': started, 'finished_at': timestamp(),
            'task': 'stack' if request.support_block else 'place',
            'status': 'completed' if result.success else 'failed', 'success': result.success,
            'verified': result.verified, 'already_complete': result.already_complete,
            'code': result.code, 'message': result.message, 'block': name or request.block,
            'color': self.registry.get(name), 'support_block': support,
            'target': pose_record(target), 'final_pose': pose_record(result.final_pose),
            'holding_block': result.holding_block,
            'evidence_required': request.evidence or 'none', 'evidence_files': list(result.evidence_files),
            'verification_samples': samples,
        })

    def complete_task(self, result, request, name, support, target, references, samples, started):
        if request.evidence == 'screenshot':
            self.feedback('evidence', .99, 'Save a Gazebo screenshot after physical verification.')
            screenshot = Path(result.report_file).parent/'scene.png'
            self.evidence_capture(screenshot)
            self.verify_placement(name, target, references, result, samples, count=1)
            result.evidence_files = [str(screenshot)]
        self.check_cancel()
        result.success, result.code = True, 'OK'
        result.message = (f'{name} is already stacked on {support}; verified without robot motion.' if result.already_complete and support
                          else f'{name} is already at the requested location; verified without robot motion.' if result.already_complete
                          else f'{name} stacked on {support} and verified.' if support else f'{name} placed and verified.')
        self.save_task_report(result, request, name, support, target, samples, started)

    def execute(self, handle):
        self.active = handle
        result = PickPlace.Result(task_id=uuid.uuid4().hex)
        task_dir = self.artifact_dir/result.task_id
        result.report_file = str(task_dir/'result.json')
        started, samples = timestamp(), []
        name, support, touched = '', '', False
        target, references = PoseStamped(), {}
        try:
            self.feedback('validate', 0.0, 'Validate block, support, target, and latest Gazebo poses.')
            if handle.request.evidence not in ['', 'none', 'screenshot']:
                raise ValueError('evidence must be none or screenshot.')
            name = self.resolve(handle.request.block)
            snapshot = {b.name: b.pose.pose for b in self.block_list()}
            positions = {n: xyz(p) for n, p in snapshot.items()}
            start = snapshot[name]
            source_chain = support_chain(self.config, name, positions)
            for n in source_chain:
                upright_yaw(quat(snapshot[n]))
            if handle.request.support_block:
                support = self.resolve(handle.request.support_block)
                if support == name:
                    raise ValueError('A block cannot support itself.')
                chain = support_chain(self.config, support, positions)
                if name in chain:
                    raise ValueError('Cannot move a supporting block on top of its own stack.')
                if len(chain) >= self.config.get('max_stack_height', 3):
                    raise SkillError('STACK_LIMIT', 'Requested stack exceeds the configured maximum height.')
                references = {n: copy.deepcopy(snapshot[n]) for n in chain}
                self.ensure_support(references)
                point = xyz(snapshot[support])
                point[2] += self.config['block_size']
                target = self.stamped(pose_at(point, yaw_quat(upright_yaw(quat(snapshot[support])))))
            else:
                target = handle.request.target
                if target.header.frame_id != 'world':
                    raise ValueError('Target frame_id must be world; coordinates are the block centre.')
                validate_position(self.config, xyz(target.pose))
                upright_yaw(quat(target.pose))
            if handle.request.evidence == 'screenshot':
                self.evidence_capture()  # Fail before movement if required evidence cannot be captured.
            task_dir.mkdir(parents=True, exist_ok=True)
            tolerance = self.config.get('stack_position_tolerance', .005) if support else self.config['placement_tolerance']
            already = (math.dist(xyz(start), xyz(target.pose)) <= tolerance
                       and abs(math.remainder(upright_yaw(quat(start))-upright_yaw(quat(target.pose)), 2*math.pi)) <= self.config['yaw_tolerance'])
            if already:
                self.feedback('verify', .95, 'Requested arrangement already exists; verify it without moving the robot.')
                self.verify_placement(name, target, references, result, samples)
                result.already_complete = True
                self.complete_task(result, handle.request, name, support, target, references, samples, started)
                handle.succeed()
                return result
            for other, point in positions.items():
                if other != name and abs(point[2]-start.position.z-self.config['block_size']) < .008 and math.hypot(point[0]-start.position.x, point[1]-start.position.y) < .04:
                    raise SkillError('BLOCK_NOT_TOP', f'{other} is on top of {name}; remove it first.')
            check_spacing(self.config, xyz(start), [point for n, point in positions.items() if n not in source_chain])
            check_spacing(self.config, xyz(target.pose), [point for n, point in positions.items() if n != name and n not in references])
            self.sync_scene()
            self.feedback('open', 0.05, 'Open the Robotiq gripper.')
            self.gripper()
            height = self.config['approach_height']
            self.ensure_support(references)
            self.feedback('approach', 0.15, 'Plan collision-aware approach to the current block pose.')
            self.move_to(self.tool_pose(start, height))
            latest = self.state(name).pose
            if math.dist(xyz(start), xyz(latest)) > 0.008 or abs(math.remainder(upright_yaw(quat(start))-upright_yaw(quat(latest)), 2*math.pi)) > 0.08:
                raise SkillError('BLOCK_MOVED', 'Block moved during approach; retry using its latest pose.')
            self.allow_touch(name, True)
            touched = True
            self.feedback('descend', 0.3, 'Descend vertically with collision checking enabled.')
            self.move_to(self.tool_pose(latest), linear=True)
            if math.dist(xyz(self.state(name).pose), xyz(latest)) > 0.012:
                raise SkillError('BLOCK_MOVED', 'Block moved before grasp; retry.')
            self.feedback('grasp', 0.4, 'Close gripper and attach using IFRA_LinkAttacher.')
            self.gripper(close=True)
            closed_pose = self.state(name).pose
            if math.dist(xyz(closed_pose), xyz(latest)) > 0.008:
                self.gripper()
                raise SkillError('GRASP_FAILED', 'Block shifted during closure; refusing to attach away from the grasp pose.')
            self.attach(name)
            self.feedback('lift', 0.5, 'Lift and verify that the block follows the gripper.')
            self.move_to(self.tool_pose(latest, height), linear=True)
            lifted = self.state(name).pose
            if abs(lifted.position.z-latest.position.z-height) > 0.025:
                raise SkillError('GRASP_FAILED', 'Block did not follow the commanded lift.')
            self.feedback('transport', 0.6, 'Plan transport with the attached block as collision geometry.')
            self.move_to(self.tool_pose(target.pose, height))
            self.ensure_support(references)
            self.feedback('lower', 0.75, 'Lower vertically to the destination.')
            self.move_to(self.tool_pose(target.pose, 0.004), linear=True)
            self.ensure_support(references)
            self.feedback('release', 0.85, 'Open the gripper and detach the block.')
            self.gripper()
            self.ensure_support(references)
            # Let the final arm/gripper command settle before removing the joint.
            release_end = time.monotonic()+5
            settled = 0
            while settled < 5:
                self.check_cancel()
                state = self.state(name)
                speed = math.sqrt(sum(v*v for v in [state.twist.linear.x, state.twist.linear.y, state.twist.linear.z]))
                angular = math.sqrt(sum(v*v for v in [state.twist.angular.x, state.twist.angular.y, state.twist.angular.z]))
                settled = settled+1 if speed < .01 and angular < .08 else 0
                if time.monotonic() > release_end:
                    raise SkillError('UNSTABLE_RELEASE', f'Block is moving before release: linear={speed}, angular={angular}')
                time.sleep(.05)
            self.get_logger().info(f'Release velocity: linear={speed}, angular={angular}')
            self.detach(name)
            time.sleep(0.7)
            self.ensure_support(references)
            self.feedback('retreat', 0.9, 'Retreat vertically from the placed block.')
            self.move_to(self.tool_pose(target.pose, height), linear=True)
            self.allow_touch(name, False)
            touched = False
            self.feedback('verify', 0.95, 'Verify settled pose, orientation, velocity, and supporting blocks.')
            self.verify_placement(name, target, references, result, samples)
            self.sync_scene()
            self.complete_task(result, handle.request, name, support, target, references, samples, started)
            handle.succeed()
        except Exception as exc:
            result.success = False
            result.code = exc.code if isinstance(exc, SkillError) else 'INVALID_REQUEST' if isinstance(exc, ValueError) else 'INTERNAL_ERROR'
            result.message = str(exc)
            self.get_logger().error(f'{result.code}: {exc}')
            if self.held:
                self.fault = 'Interrupted while holding a block; restart simulation to recover.'
            try:
                self.save_task_report(result, handle.request, name, support, target, samples, started)
            except Exception as report_error:
                self.get_logger().error(f'Task report could not be saved: {report_error}')
                result.report_file = ''
            if result.code == 'CANCELED':
                handle.canceled()
            else:
                handle.abort()
        finally:
            if touched and not self.held:
                try:
                    self.allow_touch(name, False)
                except Exception as exc:
                    self.fault = f'Collision permission cleanup failed: {exc}'
            result.holding_block = bool(self.held)
            self.active = None
            self.lock.release()
        return result


def main():
    rclpy.init()
    node = Server()
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
