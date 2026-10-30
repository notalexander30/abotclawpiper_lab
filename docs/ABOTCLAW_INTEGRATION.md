# Adding ABot-Claw to the UR10e simulation stack

This document is the handoff for the person integrating ABot-Claw. The robot
simulation and typed ROS skill layer are complete; ABot-Claw itself is not
installed or connected in this repository. Do not report the agent integration
as working until the end-to-end checks in this document pass.

The upstream [ABot-Claw project](https://github.com/amap-cvlab/ABot-Claw)
uses an OpenClaw layer, shared services and robot-specific agent servers. Its
published PiPer robot layer targets a physical PiPer arm, ROS 1, camera topics
and its own HTTP server. This repository instead contains a simulated **UR10e**,
ROS 2 Humble and Gazebo state-based block skills. Reuse ABot-Claw's orchestration
pattern, but connect it to the ROS 2 interfaces documented here instead of
substituting the PiPer driver.

## Current stack

```text
Natural-language user
        │
        ▼
ABot-Claw / OpenClaw planner              future integration
        │ structured, allowlisted request
        ▼
UR10e adapter or robot agent server       future component
        │ ROS 2 action/service calls
        ▼
block_skills server                       implemented
        ├── Gazebo state lookup
        ├── MoveIt collision-aware planning
        ├── ros2_control execution
        ├── IFRA_LinkAttacher grasp/release
        └── physical verification + evidence
```

ABot-Claw should decide **which predefined skill to request**. The ROS node
remains responsible for coordinates, reachability checks, planning, execution,
attachment, placement verification and recovery state.

## What already exists

| ROS endpoint | Type | Purpose |
| --- | --- | --- |
| `/skills/pick_place` | `block_interfaces/action/PickPlace` | Coordinate placement or stacking with feedback and result |
| `/skills/status` | `std_srvs/srv/Trigger` | Read readiness, busy, held-block and fault state |
| `/blocks` | `block_interfaces/srv/Blocks` | List, spawn, random spawn, move and randomize blocks |
| `/gazebo/get_entity_state` | `gazebo_msgs/srv/GetEntityState` | Read current simulated pose and velocity |

The public action definition is
[`src/block_interfaces/action/PickPlace.action`](../src/block_interfaces/action/PickPlace.action).
Its goal supports two modes:

```text
Coordinate placement:
  block = "red_block"
  support_block = ""
  target = block-centre pose in world

Stacking:
  block = "green_block"
  support_block = "blue_block"
  target = unused; server derives it from the support's current pose
```

Set `evidence` to `screenshot` when a visible Gazebo window is available, or
`none` for state-only headless verification.

## Recommended adapter boundary

Create a small adapter that exposes only typed robot operations. Do not give
the language model unrestricted shell access or let it publish arbitrary joint
trajectories. A minimal agent-facing schema is:

```json
{
  "skill": "stack",
  "block": "green_block",
  "support": "blue_block",
  "evidence": "screenshot"
}
```

Recommended allowlisted operations:

```text
get_status()
list_blocks()
pick_place(block, x, y, z, yaw, evidence)
stack(block, support, evidence)
add_block(color, optional_name, optional_seed)
read_result(task_id)
```

Keep `move`, `spawn` and `randomize` as operator/development operations unless
the agent has a specific scene-setup role. They change Gazebo state without
physical robot manipulation.

## Mapping natural language to skills

| User request | Adapter request |
| --- | --- |
| “What blocks are available?” | `list_blocks()` |
| “Move the red block to x 0.82, y -0.28” | `pick_place("red_block", 0.82, -0.28, 0.675, 0, evidence)` |
| “Put blue on red” | `stack("blue_block", "red_block", evidence)` |
| “Make a red-blue-green stack” | First blue on red; after verified success, green on blue |
| “Add another yellow block” | `add_block("yellow")` |
| “Did task TASK_ID finish?” | `read_result(TASK_ID)` |

For multi-step plans, wait for one action result before dispatching the next.
The server rejects concurrent manipulation and block mutation while busy.

## Result contract for the agent

The adapter must return the action result without replacing failures with a
friendly success message. The important fields are:

| Field | Required interpretation |
| --- | --- |
| `success` | Complete requested task succeeded |
| `verified` | Final Gazebo state passed repeated physical checks |
| `already_complete` | Arrangement existed and was reverified without motion |
| `code` | Machine-readable outcome or failure category |
| `message` | Human-readable explanation |
| `holding_block` | A block remains attached; stop further manipulation and restart |
| `task_id` | Stable key for the saved report/evidence |
| `evidence_files` | Screenshot paths when requested |
| `report_file` | Durable JSON task report |

ABot-Claw may report completion only when:

```text
success == true
verified == true
requested evidence exists
holding_block == false
```

If `already_complete` is true with the conditions above, the correct response
is “already stacked and verified.” If physical verification passes but required
evidence fails, report the evidence failure and retry the same request; the
idempotent check avoids repeating robot motion.

## Failure and recovery behavior

| Code/state | Agent behavior |
| --- | --- |
| `BLOCK_NOT_TOP` | Explain which block is on top; replan from the top downward or reset |
| `STACK_LIMIT` | Do not request a stack taller than the configured three blocks |
| `PLANNING_FAILED` | Do not claim movement; inspect layout and choose another valid target |
| `MOTION_FAILED` / `TRACKING_FAILED` | Stop the plan and report the execution error |
| `EVIDENCE_UNAVAILABLE` | Keep physical outcome distinct from missing screenshot evidence |
| `holding_block=true` | Stop all further tasks and restart the simulation |
| Busy rejection | Wait for the current action result, then reconsider the scene |

Never automatically replay an execution failure. The physical scene may have
changed even when the action did not complete.

## Where to run the adapter

For the first integration, run the adapter in the same `ur10e:humble`
container. It will inherit ROS 2 Humble, `ROS_DOMAIN_ID=42`, Cyclone DDS and the
workspace setup from `/entrypoint.sh`. This avoids cross-container DDS discovery
work while the contract is being developed.

If ABot-Claw requires an HTTP robot-agent interface, add a small HTTP server to
the container that translates validated requests into the ROS action and
services above. Publish its port explicitly in the `docker run` command, for
example `-p 8880:8880`. The endpoint names and authentication must follow the
ABot-Claw version your friend installs; this repository does not invent or pin
an upstream HTTP API.

When configuring ABot-Claw's robot registry, register this as a new robot type,
such as `ur10e_sim`. Do not label it `piper`: ABot-Claw's documented PiPer route
is for a different physical arm and ROS stack. A clear configuration could use:

```text
UR10E_SIM_BASE_URL=http://ROBOT_HOST:8880
capabilities=block_list,pick_place,stack,add_block,result
```

Update ABot-Claw's mission routing so block manipulation requests select
`ur10e_sim`, while its normal PiPer route continues to select the real PiPer
agent server.

## ROS-native adapter skeleton

The implementation can use the same pattern as
[`cli.py`](../src/block_skills/block_skills/cli.py):

```python
from rclpy.action import ActionClient
from block_interfaces.action import PickPlace

client = ActionClient(node, PickPlace, "/skills/pick_place")
goal = PickPlace.Goal()
goal.block = "green_block"
goal.support_block = "blue_block"
goal.evidence = "screenshot"

# Wait for the server, send the goal, stream feedback, then await the result.
# Return every result field to ABot-Claw without converting failure to success.
```

Use a `ReentrantCallbackGroup` or a multithreaded executor only if the adapter
also needs to serve status while awaiting an action. Serialize task submission
at the adapter boundary even though the skill server independently rejects
concurrent requests.

## End-to-end acceptance test

Start from a fresh GUI scene and verify readiness using [instructor setup](INSTRUCTOR_SETUP.md).
Then send these requests through ABot-Claw, not directly through the CLI:

1. “List the available blocks.”
2. “Stack blue on red.”
3. Wait for `success=true` and `verified=true`.
4. “Stack green on blue.”
5. Wait for `success=true`, `verified=true` and a saved screenshot.
6. Repeat “Stack green on blue.”
7. Confirm `already_complete=true` and no robot motion.
8. Request an unknown block and confirm ABot-Claw reports the structured error.
9. Try moving red from under the stack and confirm `BLOCK_NOT_TOP` is reported.

The integration is complete only when natural-language requests reach the
typed ROS action, feedback is visible, failures remain failures, the final
Gazebo stack is physically verified, and ABot-Claw returns the saved task ID
and evidence path.

## Current integration status

| Layer | Status |
| --- | --- |
| Gazebo UR10e/table/blocks | Implemented and historically verified |
| MoveIt and controller execution | Implemented and historically verified |
| Typed pick/place and stack action | Implemented and historically verified |
| Screenshot and JSON evidence | Implemented and historically verified |
| ABot-Claw adapter/server | Design documented; not implemented |
| Natural-language end-to-end test | Not run |

Keep this status honest as work proceeds. The simulation evidence in
[`verification.md`](verification.md) does not verify ABot-Claw integration.
