# Three-hour beginner lab: UR10e pick, place and stacking

> **Audience:** Students using a new Ubuntu desktop computer with little or no
> Docker or ROS experience.
>
> **Outcome:** Build and run a UR10e with a Robotiq 2F-85 gripper in Gazebo and
> RViz, inspect block poses, execute pick-and-place skills, stack three colored
> blocks, and save a screenshot plus a JSON completion report.

This page is formatted so it can be pasted into Notion. Work from top to
bottom. Commands marked **Host terminal** run in the normal Ubuntu terminal.
Commands marked **Container terminal** run inside Docker.

No host ROS installation, Python virtual environment, camera or OpenCV is
required. Docker provides Ubuntu 22.04, ROS 2 Humble, Gazebo Classic, MoveIt 2
and the ROS dependencies.

## Lab schedule

| Time | Activity | Result |
| --- | --- | --- |
| 00:00–00:20 | Understand the system and inspect the new PC | Requirements confirmed |
| 00:20–00:45 | Install Git, Docker and GUI support | Docker test passes |
| 00:45–01:00 | Download the project and robot assets | Source tree complete |
| 01:00–01:40 | Build the Docker image | Humble/IFRA image built |
| 01:40–02:00 | Build and test custom packages | Workspace ready |
| 02:00–02:20 | Launch Gazebo and RViz | Robot and table visible |
| 02:20–02:40 | Inspect poses and use basic skills | One block moved |
| 02:40–02:55 | Stack three blocks | Stack verified |
| 02:55–03:00 | Read evidence and shut down | Results saved |

> **Timing note:** The first Docker build downloads several gigabytes. A slow
> connection or computer can push the lab beyond three hours. For a fixed
> three-hour class, the instructor should pre-download the source and Docker
> layers while still asking students to inspect every setup step.

## What is inside the simulation

```text
Ubuntu host
└── Docker container: Ubuntu 22.04 + ROS 2 Humble
    ├── Gazebo Classic: physics, UR10e, table and blocks
    ├── MoveIt 2: collision-aware motion planning
    ├── RViz: goal and trajectory visualization
    ├── ros2_control: arm and gripper controllers
    ├── IFRA_LinkAttacher: simulated grasp and release
    └── block_skills: pose lookup, pick/place, stack and verification
```

The project uses the original IFRA UR10e assets. The complete Xacro/URDF,
meshes, Robotiq model, controllers and MoveIt configuration are downloaded into
`upstream/ros2_SimRealRobotControl`. They are not replaced by a simplified
robot model.

The table belongs to the custom project. Its dimensions are configured in
`src/block_skills/config/blocks.json`; `geometry.py` generates the table top,
four legs, floor and block models when the launch file creates the Gazebo
world. Students therefore receive the robot and table after completing the
source-download step below.

---

# 1. Prepare a new Ubuntu PC — 45 minutes

## 1.1 Check the computer

Open a terminal with **Ctrl+Alt+T**.

**Host terminal:**

```bash
cat /etc/os-release
uname -m
df -h .
free -h
echo "$DISPLAY"
```

Continue when:

- The architecture is `x86_64`.
- At least 15 GB of disk space is available.
- The computer has Internet access.
- `DISPLAY` contains a value such as `:0` or `:1` for the GUI exercises.

The environment was tested on a computer with about 14 GiB RAM. Lower-memory
machines may run slowly; start in headless mode if the GUI cannot run reliably.

## 1.2 Install Git and desktop support

**Host terminal:**

```bash
sudo apt update
sudo apt install -y git ca-certificates curl xauth
```

Verify:

```bash
git --version
curl --version
command -v xauth
```

Git's official Linux guidance recommends using the distribution package
manager on Debian/Ubuntu. See [Git installation for
Linux](https://git-scm.com/install/linux.html).

## 1.3 Install Docker Engine

First check whether Docker already works:

```bash
docker version
docker info
```

If both commands show a working client and server, continue to section 1.4.
Do not reinstall a working Docker setup.

For a fresh supported Ubuntu installation, add Docker's official repository:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
```

These commands follow Docker's current [official Ubuntu installation
guide](https://docs.docker.com/engine/install/ubuntu/). If the computer already
contains `docker.io`, Podman compatibility packages, a separate `containerd`,
or another Docker installation, use the conflict-removal instructions in that
official guide before continuing.

## 1.4 Allow your user to run Docker

**Host terminal:**

```bash
sudo groupadd --force docker
sudo usermod -aG docker "$USER"
```

Log out of the Ubuntu desktop completely and log back in. Opening only a new
terminal may not refresh group membership. Then verify without `sudo`:

```bash
docker version
docker run --rm hello-world
```

> Membership in the `docker` group grants root-level access through the Docker
> daemon. This is documented in Docker's [Linux post-installation
> guide](https://docs.docker.com/engine/install/linux-postinstall/). Use it only
> on accounts that should have that access.

### Checkpoint 1

- [ ] `git --version` works.
- [ ] `docker version` shows both Client and Server.
- [ ] `docker run --rm hello-world` succeeds without `sudo`.
- [ ] `echo "$DISPLAY"` is nonempty for GUI work.

---

# 2. Download the project and UR10e assets — 15 minutes

## 2.1 Get the custom project

**Option A — clone the GitHub repository:**

```bash
cd "$HOME"
PROJECT_REPOSITORY_URL="https://github.com/notalexander30/abotclawpiper_lab.git"
git clone "$PROJECT_REPOSITORY_URL" abotclaw-piper
cd abotclaw-piper
```

**Option B — extract a supplied project archive:**

```bash
cd "$HOME"
mkdir -p abotclaw-piper
tar -xzf /path/to/abotclaw-piper.tar.gz -C abotclaw-piper --strip-components=1
cd abotclaw-piper
```

Confirm the custom source exists:

```bash
test -f docker/Dockerfile
test -f src/block_skills/config/blocks.json
test -f src/block_skills/block_skills/geometry.py
test -f src/block_interfaces/action/PickPlace.action
echo "Custom project files found"
```

## 2.2 Download the complete UR10e and simulator dependencies

The project repository intentionally keeps third-party source separate. Clone
the pinned revisions into `upstream/`:

```bash
mkdir -p upstream

git clone https://github.com/IFRA-Cranfield/ros2_SimRealRobotControl.git \
  upstream/ros2_SimRealRobotControl
git -C upstream/ros2_SimRealRobotControl checkout \
  9645e14a36cd7411871c9572275e6435ab41dac7

git clone https://github.com/IFRA-Cranfield/IFRA_LinkAttacher.git \
  upstream/IFRA_LinkAttacher
git -C upstream/IFRA_LinkAttacher checkout \
  b056289ba93ccb549db98926dcbb9679642d0c8d

git clone https://github.com/ros-controls/gazebo_ros2_control.git \
  upstream/gazebo_ros2_control
git -C upstream/gazebo_ros2_control checkout \
  9a3736cc742e73fc86355ef4fdb63326376ca1db
```

Confirm that the UR10e Xacro, table configuration and world generator exist:

```bash
test -f upstream/ros2_SimRealRobotControl/packages/ros2srrc_ur10e/urdf/ur10e_robotiq_2f85.urdf.xacro
test -f src/block_skills/config/blocks.json
test -f src/block_skills/block_skills/geometry.py
echo "UR10e assets and generated table source found"
```

If the UR10e check fails, locate the model without guessing:

```bash
find upstream/ros2_SimRealRobotControl -iname '*ur10e*' | head -30
```

The exact commits are also recorded in `repositories.json`. Keep upstream files
unchanged; add project-specific behavior under `src/`.

### Checkpoint 2

- [ ] `docker/Dockerfile` exists.
- [ ] `src/block_skills/config/blocks.json` defines the table and blocks.
- [ ] The IFRA checkout contains the UR10e Xacro/URDF and mesh assets.
- [ ] All three upstream repositories are on the commits in `repositories.json`.

---

# 3. Build the environment — 60 minutes

## 3.1 Build Ubuntu 22.04, ROS 2 Humble and IFRA packages

Stay in the project root.

**Host terminal:**

```bash
docker build -t ur10e:humble -f docker/Dockerfile .
```

This stage installs ROS 2 Humble, Gazebo Classic, MoveIt 2, controllers and
graphics libraries, then builds the selected IFRA and link-attacher packages.
Do not interrupt the first build because individual dependency stages can take
several minutes.

Verify the image:

```bash
docker image inspect ur10e:humble >/dev/null
docker run --rm ur10e:humble bash -c \
  'source /opt/ros/humble/setup.bash && ros2 --help >/dev/null && echo "ROS 2 Humble ready"'
```

## 3.2 Build the custom ROS packages

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

The build must create `install/setup.bash`, and the test summary must show no
failures:

```bash
test -f install/setup.bash && echo "Custom workspace ready"
```

## 3.3 Prepare the container user files

These files map the desktop user's UID and GID into Docker so generated files
remain owned by the student.

```bash
mkdir -p .container
printf 'root:x:0:0:root:/root:/bin/bash\nsim:x:%s:%s:Simulation:/tmp:/bin/bash\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n' \
  "$(id -u)" "$(id -g)" > .container/passwd
printf 'root:x:0:\nsim:x:%s:\nnogroup:x:65534:\n' \
  "$(id -g)" > .container/group
```

### Checkpoint 3

- [ ] Docker image `ur10e:humble` exists.
- [ ] `install/setup.bash` exists.
- [ ] Colcon tests report no failures.
- [ ] `.container/passwd` and `.container/group` exist.

---

# 4. Launch Gazebo and RViz — 20 minutes

## 4.1 Prepare X11 authentication

Run this from a terminal opened directly in the Ubuntu desktop session:

```bash
echo "$DISPLAY"
touch .xauth
xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | \
  xauth -f .xauth nmerge -
test -s .xauth && echo "GUI authentication ready"
```

Do not continue unless the last message appears.

## 4.2 Start the complete simulation

Check for an old container:

```bash
docker ps -a --filter name=ur10e
```

If one exists, reset it:

```bash
docker rm -f ur10e
```

Start Gazebo, RViz, MoveIt, controllers and the skill server:

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

Two windows should appear:

- **Gazebo:** the physical UR10e, Robotiq gripper, generated table and blocks.
- **RViz:** the MoveIt planning scene, goal preview and planned trajectory.

Wait for the complete environment:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks status --wait 150
```

Expected output:

```text
ready=True; busy=False; holding=none; fault=none
```

## 4.3 Inspect the robot and world

```bash
docker exec ur10e /entrypoint.sh ros2 control list_controllers
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks list
```

Confirm the joint-state broadcaster, arm controller and six gripper controllers
are active. The block list should contain `red_block`, `blue_block` and
`green_block` with their latest Gazebo poses.

> RViz visualizes planning. Gazebo simulates physical execution. Moving an
> orange goal preview in RViz does not move the Gazebo robot until a trajectory
> is planned and executed.

### Checkpoint 4

- [ ] Gazebo shows the UR10e, gripper, table and three colored blocks.
- [ ] RViz shows the robot and MotionPlanning panel.
- [ ] Readiness reports no fault or held block.
- [ ] All required controllers are active.

---

# 5. Learn the block skills — 20 minutes

Every public coordinate is a block-centre position in metres in Gazebo's
`world` frame. The table top is z = 0.65 m. A 0.05 m cube resting on it has
centre z = 0.675 m.

## 5.1 List poses and status

```bash
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks status
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks list
```

## 5.2 Pick and place using the robot

Move red to a free table position:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks pick red_block 0.82 -0.28 0.675
```

The skill retrieves the latest Gazebo pose, plans collision-aware motion,
opens the gripper, approaches, grasps, attaches, lifts, transports, lowers,
detaches, retreats and verifies the measured final pose. Wait for the command
to finish before sending another request.

## 5.3 Other available commands

| Command | Purpose | Robot moves? |
| --- | --- | --- |
| `status` | Read readiness, busy, held-block and fault state | No |
| `list` | Retrieve current registered block poses | No |
| `pick` | Pick one block and place it at coordinates | Yes |
| `stack` | Pick one top block and place it on a support block | Yes |
| `add` | Spawn a colored block at a random free location | No |
| `spawn` | Spawn a colored block at explicit coordinates | No |
| `move` | Reposition a block directly through Gazebo | No |
| `randomize` | Randomize registered block locations | No |
| `result` | Read a saved task report | No |

Display CLI help:

```bash
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks --help
```

Examples:

```bash
# Add a new colored cube at a random free location
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks add yellow --name yellow_extra --seed 42

# Move a block directly without robot manipulation
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks move green_block 0.45 0.35 0.675

# Randomize the registered blocks repeatably
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks randomize --seed 42
```

`move` and `randomize` are scene-management operations. Use `pick` when the
UR10e must physically perform the task.

---

# 6. Stack three blocks — 15 minutes

Stacking works best from the fresh default scene. If section 5 changed the
scene, restart before continuing:

```bash
docker rm -f ur10e
```

Repeat sections 4.1 and 4.2, then wait for readiness.

## 6.1 Stack blue on red

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack blue_block red_block
```

Continue only when the result contains:

```json
"success": true,
"verified": true
```

## 6.2 Stack green on blue

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack green_block blue_block
```

The final arrangement is:

```text
green_block
blue_block
red_block
─────────── table
```

No target coordinates are required for `stack`. The server queries the latest
support pose from `/gazebo/get_entity_state` and calculates:

```text
target x   = support x
target y   = support y
target z   = support z + block size
target yaw = support yaw
```

It still uses coordinates internally; the student supplies the semantic
relationship “green on blue.” The server also validates the support chain,
maximum stack height, upright orientation, stability and whether the moving
block is free on top.

> If `BLOCK_NOT_TOP` appears, another block is resting on the requested moving
> block. This skill moves one free block at a time; it does not lift a complete
> sub-stack. Restart for the prescribed red–blue–green order.

---

# 7. Understand screenshot and JSON evidence — 5 minutes

Each successful GUI stack requests screenshot evidence by default. The output
contains a 32-character `task_id`, for example:

```json
{
  "success": true,
  "task_id": "TASK_ID",
  "verified": true,
  "already_complete": false,
  "evidence_files": ["/work/artifacts/TASK_ID/scene.png"],
  "report_file": "/work/artifacts/TASK_ID/result.json"
}
```

On the host, the files are:

```text
artifacts/TASK_ID/scene.png
artifacts/TASK_ID/result.json
```

Read the report, replacing `TASK_ID` with the returned value:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks result TASK_ID
```

The screenshot is visual evidence for a person or report. It does not perform
object detection. The JSON is structured evidence for software or a future AI
agent: it records success, physical verification, final pose, task ID, evidence
paths and whether the arrangement already existed.

Repeat the final request:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack green_block blue_block
```

A correct existing stack should return `already_complete: true`, verify it
without moving the robot, and save fresh evidence.

### Final student checkpoint

- [ ] Three blocks are visibly stacked in Gazebo.
- [ ] The final action reports `success: true` and `verified: true`.
- [ ] `scene.png` opens and shows the final stack.
- [ ] `result.json` has the same task ID as its artifact folder.
- [ ] A repeated request reports `already_complete: true`.

Save the final screenshot, JSON report and terminal output for submission.

---

# 8. Troubleshooting and shutdown

## Common problems

| Problem | Check |
| --- | --- |
| Docker permission denied | Log out/in after joining `docker`; run `docker info` |
| Container name already exists | Run `docker ps -a`; reset with `docker rm -f ur10e` |
| Package not found | Confirm the custom build created `install/setup.bash`; use `/entrypoint.sh` |
| Gazebo or RViz does not open | Check `DISPLAY`, `xauth`, `.xauth`, and run from the desktop session |
| Status never becomes ready | Read `docker logs --tail 200 ur10e` |
| Plan/Execute does not move | Choose a goal different from `<current>` and check active controllers |
| `BLOCK_NOT_TOP` | Another block rests on the moving block; move the top block or restart |
| `STACK_LIMIT` | The configured maximum is three blocks |
| Screenshot evidence fails | Use GUI mode and keep exactly one Gazebo window visible |
| `holding_block: true` | Restart before sending another manipulation request |

Read live launch output:

```bash
docker logs --tail 200 ur10e
docker logs --follow ur10e
```

Press **Ctrl+C** to stop following logs; the detached simulation continues.

## Stop and reset

```bash
docker stop --time 15 ur10e
docker rm ur10e
```

Removing the container resets the simulated scene next time. It does not remove
source files, Docker image layers, custom builds or `artifacts/` on the host.

## What students should be able to explain

1. Why Docker is different from a Python virtual environment or ROS sourcing.
2. Where the original UR10e model comes from and why its assets stay pinned.
3. How the table is generated from the custom JSON configuration.
4. Why `stack` does not need user-provided coordinates.
5. The difference between Gazebo physical state and RViz visualization.
6. Why screenshot evidence and JSON verification serve different purposes.
7. Why a support block cannot be picked while another block rests on it.

For code development and complete operational commands, return to
[README.md](README.md). Historical verification evidence and known limitations
are recorded in [docs/verification.md](docs/verification.md).
