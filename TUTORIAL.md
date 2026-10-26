# 🤖 Three-hour beginner lab: UR10e pick, place and stacking

> 👩‍🎓 **Audience:** Students using a new Ubuntu desktop computer with little or
> no Docker or ROS experience.

> ⏱️ **Duration:** Three hours. Allow extra download time on a slow connection.

> 🎯 **Outcome:** Build and run a UR10e with a Robotiq 2F-85 gripper in Gazebo
> and RViz, inspect block poses, execute pick-and-place skills, stack three
> colored blocks, and save a screenshot plus a JSON completion report.

## 📋 How to use this page in Notion

1. Open this file in GitHub's normal rendered view.
2. Copy from the title above to the end of the page.
3. Paste into a new empty Notion page.
4. Keep **Paste and match style** disabled so headings, checkboxes, quotes and
   code blocks retain their formatting.
5. Work from top to bottom. Tick each checkpoint only after its command passes.

Commands marked **Host terminal** run in the normal Ubuntu terminal. Commands
marked **Container terminal** run inside Docker.

No host ROS installation, Python virtual environment, camera or OpenCV is
required. Docker provides Ubuntu 22.04, ROS 2 Humble, Gazebo Classic, MoveIt 2
and the ROS dependencies.

## 🗓️ Lab schedule

- **00:00–00:20 — Understand the system and inspect the PC**
  Result: requirements confirmed.
- **00:20–00:45 — Install Git, Docker and GUI support**
  Result: Docker test passes.
- **00:45–01:15 — Create a workspace, clone robot assets and add skills**
  Result: source tree complete.
- **01:15–01:45 — Build the Docker image**
  Result: Ubuntu 22.04, ROS 2 Humble and IFRA image built.
- **01:45–02:00 — Build and test custom packages**
  Result: custom workspace ready.
- **02:00–02:20 — Launch Gazebo and RViz**
  Result: robot and table visible.
- **02:20–02:40 — Inspect poses and use basic skills**
  Result: one block moved by the robot.
- **02:40–02:55 — Stack three blocks**
  Result: stack physically verified.
- **02:55–03:00 — Read evidence and shut down**
  Result: screenshot and JSON result saved.

> **Timing note:** The first Docker build downloads several gigabytes. A slow
> connection or computer can push the lab beyond three hours. For a fixed
> three-hour class, the instructor should pre-download the source and Docker
> layers while still asking students to inspect every setup step.

## 🧱 What is inside the simulation

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
workspace setup below.

---

## 1. Prepare a new Ubuntu PC — 45 minutes

### 1.1 Check the computer

Open a terminal with **Ctrl+Alt+T**.

**Host terminal:**

```bash
cat /etc/os-release
uname -s
uname -m
df -h .
free -h
echo "$DISPLAY"
```

Continue when:

- `uname -s` reports `Linux`.
- `/etc/os-release` identifies an Ubuntu desktop installation.
- Record the CPU result from `uname -m`: `x86_64` means Intel/AMD 64-bit and
  `aarch64` means ARM 64-bit. Linux is the operating system, not the CPU type.
- At least 15 GB of disk space is available.
- The computer has Internet access.
- `DISPLAY` contains a value such as `:0` or `:1` for the GUI exercises.

The complete lab was verified on a Linux `x86_64` host with about 14 GiB RAM.
The pinned ROS Docker base publishes both `amd64` and `arm64/v8` images, but the
complete UR10e/MoveIt/Gazebo stack has not been verified on ARM. Lower-memory
machines may run slowly; start in headless mode if the GUI cannot run reliably.

### 1.2 Install Git and desktop support

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

### 1.3 Install Docker Engine

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

### 1.4 Allow your user to run Docker

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

### ✅ Checkpoint 1

- [ ] `git --version` works.
- [ ] `docker version` shows both Client and Server.
- [ ] `docker run --rm hello-world` succeeds without `sudo`.
- [ ] `echo "$DISPLAY"` is nonempty for GUI work.

---

## 2. Create the workspace and add the skills — 30 minutes

Students do **not** clone the finished `abotclawpiper_lab` repository in this
lab. Start with an empty directory, clone the robot projects that the
simulation needs, and then add the custom ROS 2 skill packages. This makes the
boundary between reused IFRA code and student-added code visible.

### 2.1 Create an empty lab workspace

**Host terminal:**

```bash
cd "$HOME"
mkdir -p ur10e-skills-lab/{upstream,src,docker}
cd ur10e-skills-lab
```

The intended layout is:

```text
ur10e-skills-lab/
├── upstream/                 # pinned third-party repositories; do not edit
├── src/
│   ├── block_interfaces/     # typed ROS action, service and message
│   └── block_skills/         # Gazebo, MoveIt and stacking behavior
└── docker/                   # reproducible Ubuntu/ROS environment
```

### 2.2 Clone the required robot and simulator repositories

Clone the pinned revisions into `upstream/`. The first repository supplies the
UR10e, Robotiq gripper, controllers and MoveIt configuration. The second
supplies simulated attach/detach services. The third provides the Humble
Gazebo controller plugin required by the IFRA simulation.

```bash
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

Confirm the important upstream files instead of assuming the clone worked:

```bash
test -f upstream/ros2_SimRealRobotControl/packages/ros2srrc_ur10e/urdf/ur10e_robotiq_2f85.urdf.xacro
test -d upstream/IFRA_LinkAttacher
test -d upstream/gazebo_ros2_control/gazebo_ros2_control
echo "Pinned robot dependencies found"
```

If the UR10e check fails, locate the model without guessing:

```bash
find upstream/ros2_SimRealRobotControl -iname '*ur10e*' | head -30
```

Check that every checkout is on the expected commit:

```bash
git -C upstream/ros2_SimRealRobotControl rev-parse HEAD
git -C upstream/IFRA_LinkAttacher rev-parse HEAD
git -C upstream/gazebo_ros2_control rev-parse HEAD
```

Expected values, in the same order:

```text
9645e14a36cd7411871c9572275e6435ab41dac7
b056289ba93ccb549db98926dcbb9679642d0c8d
9a3736cc742e73fc86355ef4fdb63326376ca1db
```

Keep these repositories unchanged. All new behavior belongs under `src/`.

### 2.3 Add the typed ROS 2 interface package

Create the package layout:

```bash
mkdir -p src/block_interfaces/{action,msg,srv}
```

`PickPlace.action` is the main skill contract. A caller gives either a target
pose or the name of a support block. Feedback describes the current stage, and
the result carries machine-readable verification and evidence fields.

```bash
curl -fL https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/main/src/block_interfaces/action/PickPlace.action \
  -o src/block_interfaces/action/PickPlace.action
curl -fL https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/main/src/block_interfaces/msg/Block.msg \
  -o src/block_interfaces/msg/Block.msg
curl -fL https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/main/src/block_interfaces/srv/Blocks.srv \
  -o src/block_interfaces/srv/Blocks.srv
curl -fL https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/main/src/block_interfaces/CMakeLists.txt \
  -o src/block_interfaces/CMakeLists.txt
curl -fL https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/main/src/block_interfaces/package.xml \
  -o src/block_interfaces/package.xml
```

Read the action before continuing:

```bash
cat src/block_interfaces/action/PickPlace.action
```

The two `---` separators divide goal, result and feedback. This typed action is
what a future agent adapter should call; the agent does not need permission to
run arbitrary shell commands or joint trajectories.

### 2.4 Add the reusable `block_skills` package

Create the Python package directories:

```bash
mkdir -p src/block_skills/{block_skills,config,launch,resource,test}
touch src/block_skills/block_skills/__init__.py
touch src/block_skills/resource/block_skills
```

Download the individual skill implementation files into the package. This is
not a clone of the completed lab repository: the files are added explicitly to
the blank workspace so students can inspect what each layer contributes.

```bash
RAW=https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/main/src/block_skills

for FILE in capture.py check.py cli.py geometry.py reports.py server.py; do
  curl -fL "$RAW/block_skills/$FILE" -o "src/block_skills/block_skills/$FILE"
done

curl -fL "$RAW/config/blocks.json" -o src/block_skills/config/blocks.json
curl -fL "$RAW/launch/sim.launch.py" -o src/block_skills/launch/sim.launch.py
curl -fL "$RAW/package.xml" -o src/block_skills/package.xml
curl -fL "$RAW/setup.py" -o src/block_skills/setup.py
curl -fL "$RAW/setup.cfg" -o src/block_skills/setup.cfg

for FILE in test_geometry.py test_node.py test_reports.py; do
  curl -fL "$RAW/test/$FILE" -o "src/block_skills/test/$FILE"
done
```

These modules have separate jobs:

- **`geometry.py` — Scene geometry**
  Generates the table, floor and colored cube SDF. It also calculates poses
  and stack relationships.
- **`server.py` — Skill execution**
  Queries Gazebo state, validates requests, plans MoveIt motions,
  attaches/detaches blocks and verifies results.
- **`cli.py` — Student commands**
  Converts commands such as `pick`, `stack` and `add` into typed ROS requests.
- **`capture.py` — Visual evidence**
  Saves a Gazebo screenshot after physical verification.
- **`reports.py` — Machine-readable evidence**
  Writes and reads structured JSON task results.
- **`check.py` — Readiness**
  Waits for Gazebo, MoveIt, controllers and the skill server.
- **`sim.launch.py` — Complete launch**
  Starts IFRA's UR10e/Robotiq simulation and the custom skill server.

Inspect where the public commands and ROS endpoints are registered:

```bash
rg -n "add_parser|ActionServer|create_service|create_client" \
  src/block_skills/block_skills
```

If `rg` is unavailable, install it with `sudo apt install -y ripgrep` or use:

```bash
grep -RniE "add_parser|ActionServer|create_service|create_client" \
  src/block_skills/block_skills
```

### 2.5 Understand how a skill is added

A complete skill crosses four layers. Use `stack` as the example:

1. `PickPlace.action` defines typed input, feedback and results.
2. `cli.py` registers the `stack BLOCK SUPPORT` command and sends an action
   goal with `stack=true` and the support model name.
3. `server.py` exposes `/skills/pick_place`, looks up both live Gazebo poses,
   calculates the target above the support, and executes the motion phases.
4. `server.py` reads the final Gazebo pose, verifies the support relationship,
   then `reports.py` records the result and `capture.py` requests a screenshot.

Trace that path in the actual source:

```bash
rg -n "stack|/skills/pick_place|def execute|save_report|capture" \
  src/block_interfaces src/block_skills
```

When adding another predefined skill later, follow the same pattern:

1. Add only the new typed goal/result fields that callers need.
2. Add one allowlisted CLI or agent operation with validated arguments.
3. Implement the server behavior from reusable pose, planning, gripper and
   verification helpers.
4. Return feedback during long operations and a stable error code on failure.
5. Verify simulator state after execution; a completed MoveIt trajectory alone
   does not prove that the block reached its target.
6. Add tests for geometry, validation and result serialization before exposing
   the operation to an AI agent.

This is the skill boundary ABot-Claw will use later. Natural language should
select one of these typed, allowlisted operations; it should not generate
unrestricted ROS or shell commands.

### 2.6 Add the Docker environment

The Docker files pin Ubuntu 22.04 and ROS 2 Humble, install MoveIt/Gazebo, and
build only the required upstream packages. Add them individually:

```bash
RAW_ROOT=https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/main
curl -fL "$RAW_ROOT/docker/Dockerfile" -o docker/Dockerfile
curl -fL "$RAW_ROOT/docker/entrypoint.sh" -o docker/entrypoint.sh
chmod +x docker/entrypoint.sh
```

Read the image recipe and identify the three `COPY upstream/...` statements:

```bash
cat docker/Dockerfile
```

### 2.7 Validate the source tree

```bash
test -f docker/Dockerfile
test -f src/block_interfaces/action/PickPlace.action
test -f src/block_skills/config/blocks.json
test -f src/block_skills/block_skills/server.py
test -f src/block_skills/launch/sim.launch.py
python3 -m json.tool src/block_skills/config/blocks.json >/dev/null
python3 -m compileall -q src/block_skills
echo "Custom skill source is ready"
```

Open `src/block_skills/config/blocks.json`. The file maps model names to
colors, defines the three starting poses, sets the cube size and defines the
table geometry. Gazebo remains the live pose source after spawning; this JSON
is configuration, not a substitute for current simulator state.

### ✅ Checkpoint 2

- [ ] `docker/Dockerfile` exists.
- [ ] `src/block_skills/config/blocks.json` defines the table and blocks.
- [ ] `src/block_interfaces/action/PickPlace.action` has goal, result and feedback sections.
- [ ] The IFRA checkout contains the UR10e Xacro/URDF and mesh assets.
- [ ] All three upstream repositories are on the pinned commits shown above.
- [ ] Students can explain which module implements ROS commands, motion execution and verification.

---

## 3. Build the environment — 45 minutes

### 3.1 Build Ubuntu 22.04, ROS 2 Humble and IFRA packages

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

### 3.2 Build the custom ROS packages

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

### 3.3 Prepare the container user files

These files map the desktop user's UID and GID into Docker so generated files
remain owned by the student.

```bash
mkdir -p .container
printf 'root:x:0:0:root:/root:/bin/bash\nsim:x:%s:%s:Simulation:/tmp:/bin/bash\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n' \
  "$(id -u)" "$(id -g)" > .container/passwd
printf 'root:x:0:\nsim:x:%s:\nnogroup:x:65534:\n' \
  "$(id -g)" > .container/group
```

### ✅ Checkpoint 3

- [ ] Docker image `ur10e:humble` exists.
- [ ] `install/setup.bash` exists.
- [ ] Colcon tests report no failures.
- [ ] `.container/passwd` and `.container/group` exist.

---

## 4. Launch Gazebo and RViz — 20 minutes

### 4.1 Prepare X11 authentication

Run this from a terminal opened directly in the Ubuntu desktop session:

```bash
echo "$DISPLAY"
touch .xauth
xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | \
  xauth -f .xauth nmerge -
test -s .xauth && echo "GUI authentication ready"
```

Do not continue unless the last message appears.

### 4.2 Start the complete simulation

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

### 4.3 Inspect the robot and world

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

### ✅ Checkpoint 4

- [ ] Gazebo shows the UR10e, gripper, table and three colored blocks.
- [ ] RViz shows the robot and MotionPlanning panel.
- [ ] Readiness reports no fault or held block.
- [ ] All required controllers are active.

---

## 5. Learn the block skills — 20 minutes

Every public coordinate is a block-centre position in metres in Gazebo's
`world` frame. The table top is z = 0.65 m. A 0.05 m cube resting on it has
centre z = 0.675 m.

### 5.1 List poses and status

```bash
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks status
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks list
```

### 5.2 Pick and place using the robot

Move red to a free table position:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks pick red_block 0.82 -0.28 0.675
```

The skill retrieves the latest Gazebo pose, plans collision-aware motion,
opens the gripper, approaches, grasps, attaches, lifts, transports, lowers,
detaches, retreats and verifies the measured final pose. Wait for the command
to finish before sending another request.

### 5.3 Other available commands

**Skills that move the robot**

- `pick` — Pick one block and place it at explicit coordinates.
- `stack` — Pick one free top block and place it on a support block.

**Scene and information commands that do not move the robot**

- `status` — Read readiness, busy, held-block and fault state.
- `list` — Retrieve registered blocks and their latest Gazebo poses.
- `add` — Spawn a colored block at a random free location.
- `spawn` — Spawn a colored block at explicit coordinates.
- `move` — Reposition a block directly through Gazebo.
- `randomize` — Randomize registered block locations.
- `result` — Read a saved task report.

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

## 6. Stack three blocks — 15 minutes

Stacking works best from the fresh default scene. If section 5 changed the
scene, restart before continuing:

```bash
docker rm -f ur10e
```

Repeat sections 4.1 and 4.2, then wait for readiness.

### 6.1 Stack blue on red

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack blue_block red_block
```

Continue only when the result contains:

```json
"success": true,
"verified": true
```

### 6.2 Stack green on blue

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

## 7. Understand screenshot and JSON evidence — 5 minutes

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

### ✅ Final student checkpoint

- [ ] Three blocks are visibly stacked in Gazebo.
- [ ] The final action reports `success: true` and `verified: true`.
- [ ] `scene.png` opens and shows the final stack.
- [ ] `result.json` has the same task ID as its artifact folder.
- [ ] A repeated request reports `already_complete: true`.

Save the final screenshot, JSON report and terminal output for submission.

---

## 8. Troubleshooting and shutdown

### Common problems

- **Docker permission denied**
  Log out and back in after joining the `docker` group, then run `docker info`.
- **Container name already exists**
  Run `docker ps -a`, then reset it with `docker rm -f ur10e`.
- **Package not found**
  Confirm the custom build created `install/setup.bash` and invoke ROS through
  `/entrypoint.sh`.
- **Gazebo or RViz does not open**
  Check `DISPLAY`, `xauth` and `.xauth`. Run from a terminal opened in the
  desktop session.
- **Status never becomes ready**
  Read `docker logs --tail 200 ur10e`.
- **Plan/Execute does not move**
  Choose a goal different from `<current>` and check that controllers are
  active.
- **`BLOCK_NOT_TOP`**
  Another block rests on the moving block. Move the top block or restart.
- **`STACK_LIMIT`**
  The configured maximum is three blocks.
- **Screenshot evidence fails**
  Use GUI mode and keep exactly one Gazebo window visible.
- **`holding_block: true`**
  Restart before sending another manipulation request.

Read live launch output:

```bash
docker logs --tail 200 ur10e
docker logs --follow ur10e
```

Press **Ctrl+C** to stop following logs; the detached simulation continues.

### Stop and reset

```bash
docker stop --time 15 ur10e
docker rm ur10e
```

Removing the container resets the simulated scene next time. It does not remove
source files, Docker image layers, custom builds or `artifacts/` on the host.

### What students should be able to explain

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
