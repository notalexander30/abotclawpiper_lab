# Initial inspection

Inspected before installing dependencies or implementing the simulation, 22 October 2026.

| Item | Finding |
| --- | --- |
| Workspace | `/home/xander/abotclaw+piper`, initially empty |
| Host OS | Ubuntu 26.04.1, x86_64 |
| Host ROS | Lyrical in `/opt/ros/lyrical` |
| Docker | Engine 29.1.3 available to the current user |
| Compose | Not installed; project uses direct `docker run` commands |
| Memory | Approximately 14 GiB RAM plus 4 GiB swap |
| Disk | Approximately 64 GiB available before setup |
| Graphics | NVIDIA RTX 4050 Mobile and AMD integrated graphics; XWayland available |
| Required container OS | Ubuntu 22.04 (Jammy), ROS 2 Humble, Gazebo Classic 11 |

No host ROS packages, Python environment, shell startup files, or graphics drivers
were changed. Build dependencies are installed in Docker.

## Reuse decisions

Reviewed the repositories' READMEs, installation guide, UR10e configurations,
URDF/xacro, SRDF, joint limits, controller configurations, simulation/MoveIt
launch files, UR10e demo program, parallel gripper helper, and LinkAttacher
implementation. Exact revisions are recorded in `repositories.json`.

- The IFRA `ur10e_2` configuration supplies the UR10e and Robotiq 2F-85.
- The robot and gripper models, meshes, stand, joint limits, kinematics and
  controllers are used directly from their installed IFRA packages.
- `IFRA_LinkAttacher` is built unchanged and supplies `/ATTACHLINK` and
  `/DETACHLINK`. Its implementation has one global attachment state, so the
  skill server serializes all manipulation and block mutation requests.
- IFRA's `parallelGripper.py` imports `objectpose_msgs` and subscribes to
  IFRA_ObjectPose topics. Its higher-level sequence is implemented here against
  Gazebo's standard `GetEntityState` service instead.
- The included UR10e demo is a fixed motion sequence without an end effector;
  it does not provide this requested dynamic, collision-aware block task.
- IFRA launch files hardcode the world and some paths under `~/dev_ws`, parse
  arguments from `sys.argv`, and start their custom execution nodes. The custom
  launch file reuses their assets and configuration with normal ROS launch
  arguments, an external JSON scene and standard MoveIt actions.
- The upstream installation guide requests a modification to an installed
  MoveIt header for its custom execution nodes. Those nodes are not needed by
  this implementation; the standard MoveIt installation is left intact.
- IFRA documents Gazebo control 0.4.6 for URDF compatibility. This dependency
  is pinned to their specified commit and built from source.
- The generated SRDF omits the redundant virtual joint to `base_link`, because
  the reused URDF already contains the fixed `world -> stand -> base_link`
  chain. The upstream file itself is unchanged.
- OMPL handles collision-aware free-space motion; the Pilz LIN planner handles
  vertical approach, lift, lowering and retreat. Both use the same MoveIt scene.

## References

- [IFRA installation guide](https://github.com/IFRA-Cranfield/ros2_SimRealRobotControl/blob/9645e14a36cd7411871c9572275e6435ab41dac7/instructions/Installation.md)
- [IFRA UR10e configurations](https://github.com/IFRA-Cranfield/ros2_SimRealRobotControl/blob/9645e14a36cd7411871c9572275e6435ab41dac7/packages/ros2srrc_ur10e/config/configurations.yaml)
- [IFRA LinkAttacher](https://github.com/IFRA-Cranfield/IFRA_LinkAttacher/tree/b056289ba93ccb549db98926dcbb9679642d0c8d)
