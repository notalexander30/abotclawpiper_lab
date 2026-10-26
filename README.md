# UR10e simulation development runbook

This README is for building, running and changing the UR10e pick-and-place
simulation. For the guided three-hour lab with explanations and checkpoints,
use [TUTORIAL.md](TUTORIAL.md). To connect ABot-Claw or another agent to the
typed ROS skill layer, read [ABot-Claw integration](docs/ABOTCLAW_INTEGRATION.md).

<a id="start-with-docker"></a>

## Environment

| Component | Version or value |
| --- | --- |
| Container OS | Ubuntu 22.04 Jammy |
| ROS | ROS 2 Humble |
| Simulator | Gazebo Classic 11 |
| Motion planning | MoveIt 2 |
| Robot and gripper | IFRA UR10e with Robotiq 2F-85 |
| ROS middleware/domain | Cyclone DDS, domain 42 |
| Docker image/container | `ur10e:humble` / `ur10e` |

The image supplies ROS, Gazebo, MoveIt and the pinned upstream packages. The
project directory is mounted at `/work`, so custom builds and task artifacts
remain on the host. A Python virtual environment does not provide the required
ROS system libraries, Gazebo plugins or generated interfaces.

Run host commands from the project root:

```bash
cd /home/xander/abotclaw+piper
uname -s
uname -m
docker --version
docker info
git --version
echo "$DISPLAY"
command -v xauth
```

This Docker workflow requires a Linux host. `uname -s` identifies the operating
system; `uname -m` separately reports a CPU type such as `x86_64` or `aarch64`.
The complete stack was verified on Linux `x86_64`. The pinned ROS base image is
available for `amd64` and `arm64/v8`, but this project has not been verified
end-to-end on ARM. Docker and Git are required. `DISPLAY` and `xauth` are
required for Gazebo/RViz windows and screenshots. Host ROS is not used.

## Repository layout

| Path | Purpose |
| --- | --- |
| `docker/` | Ubuntu/Humble image and ROS entrypoint |
| `src/block_interfaces/` | Message, service and action definitions |
| `src/block_skills/` | Launch, configuration, CLI and manipulation server |
| `upstream/` | Pinned IFRA and `gazebo_ros2_control` repositories |
| `artifacts/` | Task JSON reports and screenshots |
| `docs/verification.md` | Historical verification results and limits |
| `docs/ABOTCLAW_INTEGRATION.md` | Handoff for adding ABot-Claw to the stack |
| `TUTORIAL.md` | Lab-style tutorial using this main workspace |

Put custom implementation changes in `src/`. Keep the checkouts under
`upstream/` unchanged; their revisions are recorded in `repositories.json`.

## Get the pinned upstream sources

If the three upstream folders already exist, first verify them:

```bash
git -C upstream/ros2_SimRealRobotControl rev-parse HEAD
git -C upstream/IFRA_LinkAttacher rev-parse HEAD
git -C upstream/gazebo_ros2_control rev-parse HEAD

git -C upstream/ros2_SimRealRobotControl status --short
git -C upstream/IFRA_LinkAttacher status --short
git -C upstream/gazebo_ros2_control status --short
```

The revisions must match [repositories.json](repositories.json). Empty status
output means a checkout has no local changes. For a new workspace:

```bash
mkdir -p upstream

git clone https://github.com/IFRA-Cranfield/ros2_SimRealRobotControl.git upstream/ros2_SimRealRobotControl
git -C upstream/ros2_SimRealRobotControl checkout 9645e14a36cd7411871c9572275e6435ab41dac7

git clone https://github.com/IFRA-Cranfield/IFRA_LinkAttacher.git upstream/IFRA_LinkAttacher
git -C upstream/IFRA_LinkAttacher checkout b056289ba93ccb549db98926dcbb9679642d0c8d

git clone https://github.com/ros-controls/gazebo_ros2_control.git upstream/gazebo_ros2_control
git -C upstream/gazebo_ros2_control checkout 9a3736cc742e73fc86355ef4fdb63326376ca1db
```

## Build

Build the image after changing Docker dependencies, the entrypoint or an
upstream checkout:

```bash
docker build -t ur10e:humble -f docker/Dockerfile .
```

Build the custom packages and run their unit tests:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "$PWD:/work" \
  ur10e:humble bash -c \
  'colcon build --base-paths src --symlink-install --parallel-workers 2 &&
   colcon test --base-paths src --event-handlers console_direct+ &&
   colcon test-result --verbose'
```

Repeat the custom build after changing interfaces, package metadata or
installed configuration. Python code uses a symlink install, so ordinary
Python edits become visible after restarting the affected node or simulation.

## Prepare the container user and GUI

Create the passwd/group mapping once per computer or host UID/GID. It keeps
generated files owned by the host user and gives Gazebo a valid user record.

```bash
mkdir -p .container
printf 'root:x:0:0:root:/root:/bin/bash\nsim:x:%s:%s:Simulation:/tmp:/bin/bash\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n' \
  "$(id -u)" "$(id -g)" > .container/passwd
printf 'root:x:0:\nsim:x:%s:\nnogroup:x:65534:\n' \
  "$(id -g)" > .container/group
```

For GUI mode, create a scoped Xauthority cookie from the desktop terminal:

```bash
touch .xauth
xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | xauth -f .xauth nmerge -
test -s .xauth
```

## Run everything with Gazebo and RViz

An old container named `ur10e` must be removed before creating a fresh one:

```bash
docker ps -a --filter name=ur10e
docker stop --time 15 ur10e
docker rm ur10e
```

Skip `docker stop` when the old container is already stopped. Start the full
GUI environment:

```bash
docker run --detach --init --name ur10e \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  --shm-size=512m \
  -v "$PWD:/work" \
  -v "$PWD/.container/passwd:/etc/passwd:ro" \
  -v "$PWD/.container/group:/etc/group:ro" \
  -e "DISPLAY=$DISPLAY" \
  -e XAUTHORITY=/work/.xauth \
  -e LIBGL_ALWAYS_SOFTWARE=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
  ur10e:humble ros2 launch block_skills sim.launch.py gui:=true rviz:=true
```

This starts Gazebo, RViz, MoveIt, robot state publication, all controllers,
IFRA_LinkAttacher and the block skill server. Wait for readiness:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks status --wait 150
```

Expected healthy state:

```text
ready=True; busy=False; holding=none; fault=none
```

## Run headless

Use headless mode for automated work. Screenshot evidence is unavailable.

```bash
docker run --detach --init --name ur10e \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  --shm-size=512m \
  -v "$PWD:/work" \
  -v "$PWD/.container/passwd:/etc/passwd:ro" \
  -v "$PWD/.container/group:/etc/group:ro" \
  ur10e:humble ros2 launch block_skills sim.launch.py gui:=false rviz:=false

docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks status --wait 150
```

## Operate the simulation

Inspect state and controllers:

```bash
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks status
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks list
docker exec ur10e /entrypoint.sh ros2 control list_controllers
```

Pick and place using block-centre coordinates in Gazebo's `world` frame:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks pick red_block 0.82 -0.28 0.675
```

Add a colored block at a random free location or randomize the layout:

```bash
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks add red
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks add yellow --name yellow_extra --seed 42
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks randomize --seed 42
```

Stack the default blocks in GUI mode. Each command performs physical checks
and saves screenshot evidence:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack blue_block red_block
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack green_block blue_block
```

Read a result by replacing `TASK_ID` with the returned task ID:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks result TASK_ID
```

Results are stored on the host under `artifacts/TASK_ID/result.json` and, when
requested, `artifacts/TASK_ID/scene.png`.

## ROS development shell

Open a shell with all ROS environments sourced:

```bash
docker exec -it ur10e /entrypoint.sh bash
```

Useful commands inside the container:

```bash
ros2 node list
ros2 topic list
ros2 action list
ros2 service list
ros2 topic echo /joint_states --once
ros2 service call /skills/status std_srvs/srv/Trigger '{}'
ros2 service call /blocks block_interfaces/srv/Blocks '{operation: list}'
ros2 service call /gazebo/get_entity_state gazebo_msgs/srv/GetEntityState \
  '{name: red_block, reference_frame: world}'
```

The entrypoint sources `/opt/ros/humble/setup.bash`,
`/opt/ifra/install/setup.bash` and `/work/install/setup.bash`. Use `exit` to
leave the shell without stopping the simulation.

## Manual MoveIt motion

In RViz, use planning group `ur10e_arm`. Set Start State to `<current>`, change
a joint in the Joints tab, then click Plan and Execute. The orange model is a
goal preview. If Goal State is still `<current>`, no visible motion is expected.
Confirm physical movement in Gazebo or `/joint_states`, and avoid manual motion
while a block skill is busy or holding a block.

## Tests

Run unit tests in the active container:

```bash
docker exec ur10e /entrypoint.sh bash -c \
  'cd /work && colcon test --base-paths src --event-handlers console_direct+ &&
   colcon test-result --verbose'
```

Run the physical integration check on a fresh default scene:

```bash
docker exec ur10e /entrypoint.sh ros2 run block_skills check
```

See [docs/verification.md](docs/verification.md) for verified cases and limits.

## Change map

| Change | File | Follow-up |
| --- | --- | --- |
| Blocks, colors, workspace, tolerances | `src/block_skills/config/blocks.json` | Restart simulation |
| Pick/place and verification | `src/block_skills/block_skills/server.py` | Restart; run relevant tests |
| CLI behavior | `src/block_skills/block_skills/cli.py` | Start a new CLI process |
| SDF/world geometry | `src/block_skills/block_skills/geometry.py` | Restart; run unit tests |
| Screenshot capture | `src/block_skills/block_skills/capture.py` | Restart; test in GUI |
| Launch and MoveIt setup | `src/block_skills/launch/sim.launch.py` | Restart simulation |
| ROS interfaces | `src/block_interfaces/` | Rebuild packages; restart |
| Dependencies or upstream code | `docker/`, `upstream/` | Rebuild image and packages |

The launch generates the world and RViz configuration at runtime. The IFRA
repositories supply the UR10e model, gripper, controllers and MoveIt assets.

## Logs and troubleshooting

```bash
docker logs --tail 200 ur10e
docker logs --follow ur10e
```

| Symptom | Check |
| --- | --- |
| Container name exists | `docker ps -a --filter name=ur10e` |
| Gazebo/RViz does not open | Check `DISPLAY`, `xauth`, `.xauth` and X11/XWayland access |
| Package not found | Rebuild `src` and run commands through `/entrypoint.sh` |
| Robot does not execute | Check controllers, Gazebo pause state, MoveIt logs and goal state |
| Skill rejects a request | Read `blocks status`, `code`, `message` and `holding_block` |
| Planning fails | Check reachability, collisions and current block poses |
| Screenshot fails | Use GUI mode and keep exactly one Gazebo window visible |
| State becomes stale | Unpause Gazebo and inspect `/joint_states` and `/clock` |

If an error or cancellation leaves `holding_block=true`, restart the simulation
before issuing another manipulation request.

## Stop and reset

```bash
docker stop --time 15 ur10e
docker rm ur10e
```

A fresh container restores the JSON startup layout. Host files under
`artifacts/` and `logs/` remain available.

## Upstream projects

This work reuses [IFRA-Cranfield ROS 2 Sim-to-Real Robot
Control](https://github.com/IFRA-Cranfield/ros2_SimRealRobotControl) and
[IFRA_LinkAttacher](https://github.com/IFRA-Cranfield/IFRA_LinkAttacher).
Robot assets retain their upstream licenses. See
[docs/inspection.md](docs/inspection.md) for compatibility notes.
