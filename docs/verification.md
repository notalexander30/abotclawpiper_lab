# Verification record

This document records tests completed on 22 October 2026. It is historical
evidence, not a claim that every future build or computer will produce the same
result. Run the commands in [README.md](../README.md#tests) on the target
computer before reporting that its simulation works.

Raw colcon output, temporary logs, build trees and task artifact folders are
generated data and are not distributed with the clean source repository. The
two retained images are representative evidence from verified runs:

- [scene.png](scene.png): UR10e, table and spaced colored blocks.
- [stack.png](stack.png): verified red–blue–green stack.

## Tested environment

| Component | Tested value |
| --- | --- |
| Host | Ubuntu 26.04.1, Linux x86_64 |
| Host ROS | Lyrical installed but unused |
| Container | Ubuntu 22.04.5, ROS 2 Humble |
| Gazebo | Gazebo Classic 11.10.2 |
| MoveIt | MoveIt 2.5.10 |
| Graphics | XWayland with Mesa software rendering |
| Robot | Original IFRA UR10e and Robotiq 2F-85 |
| Grasp simulation | IFRA_LinkAttacher |

The base-image digest is pinned in `docker/Dockerfile`; source revisions are
listed in `repositories.json`. Apt patch versions are resolved when the image
is built.

## Verified results

| Check | Recorded result |
| --- | --- |
| Pinned upstream build | Seven selected upstream packages compiled |
| Custom package tests | Nine passed with no failures or skips |
| Controller startup | Joint-state broadcaster, arm controller and six gripper controllers active |
| Gazebo pose lookup | Current red, blue and green poses retrieved |
| Invalid input | Unknown blocks, invalid frames and out-of-bounds targets rejected before motion |
| Red pick/place | Physical grasp, lift, transport, release, retreat and pose verification passed |
| Extra blocks | Red and yellow blocks spawned and returned by the service |
| Ambiguous color/occupied target | Rejected with machine-readable error codes |
| External repositioning | Skill used a blue block pose changed through Gazebo state service |
| Changed yaw | Blue placed and verified at yaw 0.35 rad |
| Collision obstacle | Approach planning failed without attaching the block |
| Concurrent requests | Second skill and scene mutation rejected while busy |
| Cancellation during planning | Canceled cleanly without holding a block |
| Cancellation after attachment | Held state and recovery fault reported; restart recovered |
| Randomization | A seed reproduced positions and required spacing |
| Randomized pick/place | Green was picked from a randomized pose and placed at a new yaw |
| Two-block stack | Blue placed on red and repeatedly verified |
| Three-block stack | Green placed on blue while all supports remained stable |
| Idempotent stack request | Returned `already_complete=true` without robot motion |
| Stack height | Fourth block rejected with `STACK_LIMIT` |
| Support protection | Removing a supporting block rejected with `BLOCK_NOT_TOP` |
| Screenshot evidence | Visible Gazebo window captured and matched a durable JSON report |
| Missing display | Returned `EVIDENCE_UNAVAILABLE` without claiming success |

## Measured examples

Positions are block centres in metres in the Gazebo `world` frame.

| Case | Requested position | Measured final position |
| --- | --- | --- |
| Red pick/place | `(0.82, -0.28, 0.675)` | `(0.819976, -0.280015, 0.675000)` |
| Green after randomization | `(0.45, -0.40, 0.675)` | `(0.449996, -0.399982, 0.674991)` |
| GUI demo red | `(0.85, -0.35, 0.675)` | `(0.849972, -0.349958, 0.675000)` |
| GUI demo blue | `(0.85, 0.00, 0.675)` | `(0.849971, 0.000014, 0.675000)` |
| GUI demo green | `(0.85, 0.35, 0.675)` | `(0.849990, 0.349997, 0.675000)` |
| Top of verified three-block stack | Derived from supports | `(0.549962, -0.279986, 0.774678)` |

The stack task used eleven pose/orientation/velocity samples, including a
second physical check after screenshot capture. The first development attempt
tipped after release and correctly returned failure. Contact stiffness,
damping, correction velocity, contact points and solver iterations were then
tuned, and later two- and three-block tests passed at the 5 mm stack tolerance.

## Manual RViz diagnosis

On 22 October 2026, all controllers were active, Gazebo was unpaused and RViz
was connected to `ur10e_arm`. A collision-aware `/move_action` goal offset the
shoulder-pan joint by 0.1 rad. MoveIt returned success with eight trajectory
points, while `/joint_states` changed from 0.00000428 to 0.10038280 rad.

This verified the controller and MoveIt execution path. The launch was updated
to show the query-goal preview, use a translucent collision scene and expose
the Displays panel. Manual RViz clicks still require a goal different from the
current state before Plan and Execute can produce visible motion.

## Resolved implementation issues

- Renamed a service-client dictionary that collided with names reserved by
  `rclpy.Node`.
- Removed a redundant world-object removal during MoveIt attachment.
- Dispatched six gripper commands together to keep the parallel linkage
  aligned and avoid pushing the block.
- Used the measured block-to-gripper transform during transport.
- Added bounded retries when OMPL produced no trajectory; execution failures
  are reported without replaying motion.
- Added low-velocity settling checks before physical detachment.

## Limits of the verification

The native Ubuntu workflow, hardware GPU acceleration and a physical UR10e
were not tested. The supported objects are upright, uniformly sized cubes on
the configured table. The scene is refreshed before each movement; it is not a
dynamic-obstacle avoidance system. The configured stack limit is three aligned
cubes. Tilted, overhanging or taller stacks remain outside the tested scope.

Gazebo uses a simulated attachment joint, so this is not a friction-only grasp
test. Table placement tolerance is 0.02 m, stack placement tolerance is 0.005 m
and yaw tolerance is 0.15 rad. Success at the recorded poses does not guarantee
that every coordinate in the bounding workspace is kinematically reachable or
collision-free.

Expected upstream messages include the missing optional recognition action,
the absence of an Octomap sensor plugin, unrealistic visualized gripper-knuckle
inertias, and the TCP marker's missing collision geometry. These did not block
the verified tasks. Planning, controller, attachment, stale-state and evidence
errors remain actionable failures.
