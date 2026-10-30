# UR10e Lab: Pick, Place and Stack

Build a robot simulation, change its scene, and use measured positions to move
and stack blocks. You will work with configuration data, reusable skills and
simple coordinate calculations.

Use an Ubuntu Linux desktop. Run commands in Terminal (**Ctrl+Alt+T**) and edit
files in VS Code. Allow about three hours for the activities; the first Docker
build can take additional time depending on the computer and download speed.

The complete simulation has been verified on Linux `x86_64` with X11/XWayland.
Use at least 15 GB of free disk space and an Internet connection. Docker
supplies Ubuntu 22.04 and ROS 2 Humble; a host ROS installation is not needed.
ARM and native Wayland operation have not been verified.

## 1. Create the workspace

### 1.1 Install the tools

On a fresh Ubuntu desktop, enter the following. If Docker already works, do
not reinstall it: install just `git curl xauth` and skip the Docker service
and group commands.

```bash
sudo apt update
sudo apt install -y git curl docker.io xauth
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Install VS Code if it is not already available:

```bash
sudo snap install code --classic
```

Log out and back in once to apply Docker group membership. Open Terminal:

```bash
docker version
```

**Expected:** `Client` and `Server` sections, each with a version number.

### 1.2 Create a new workspace and download the robot repositories

Create an empty workspace on **your own computer**:

```bash
cd "$HOME"
mkdir -p ur10e-skills-lab/{upstream,src,docker,scripts}
cd ur10e-skills-lab
code .
```

`upstream/` is an ordinary local folder created by this command. It is not a
folder you need to find in IFRA's repository, and it does not depend on files
from the instructor's computer. Each `git clone URL DESTINATION` downloads a
public repository into the named local destination. Run these commands only
once in a new workspace:

```bash
git clone https://github.com/IFRA-Cranfield/ros2_SimRealRobotControl.git upstream/ros2_SimRealRobotControl
git -C upstream/ros2_SimRealRobotControl checkout 9645e14a36cd7411871c9572275e6435ab41dac7

git clone https://github.com/IFRA-Cranfield/IFRA_LinkAttacher.git upstream/IFRA_LinkAttacher
git -C upstream/IFRA_LinkAttacher checkout b056289ba93ccb549db98926dcbb9679642d0c8d

git clone https://github.com/ros-controls/gazebo_ros2_control.git upstream/gazebo_ros2_control
git -C upstream/gazebo_ros2_control checkout 9a3736cc742e73fc86355ef4fdb63326376ca1db
```

**Expected:** VS Code shows three downloaded folders under `upstream/`.
The checkout commands select the versions used by this lab.
The “detached HEAD” message after checkout is expected. If a clone or checkout
fails, stop and resolve that error before building.

| Folder | Provides |
| --- | --- |
| `upstream/ros2_SimRealRobotControl` | UR10e, gripper and MoveIt configuration |
| `upstream/IFRA_LinkAttacher` | Simulated grasp and release |
| `upstream/gazebo_ros2_control` | Connection between controllers and simulated joints |
| `src/block_interfaces` | Task input and result definitions |
| `src/block_skills` | Scene, block operations and robot skills |
| `docker` | ROS 2 Humble software environment |

### 1.3 Add the supplied lab files

The robot files come from these public repositories:

- [IFRA robot framework](https://github.com/IFRA-Cranfield/ros2_SimRealRobotControl).
- [IFRA LinkAttacher](https://github.com/IFRA-Cranfield/IFRA_LinkAttacher).
- [Gazebo controller bridge](https://github.com/ros-controls/gazebo_ros2_control).

Download the custom skill packages and Docker files individually from the
[lab source](https://github.com/notalexander30/abotclawpiper_lab/tree/94c5cab).
This fixed revision contains the supplied files; it does not require cloning
the finished lab or copying anything from another computer.

Enter this whole block from `~/ur10e-skills-lab`:

```bash
bash <<'DOWNLOAD'
set -euo pipefail
LESSON=https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/94c5cab
mkdir -p src/block_interfaces/{action,msg,srv}
mkdir -p src/block_skills/{block_skills,config,launch,resource}
for FILE in CMakeLists.txt package.xml action/PickPlace.action msg/Block.msg srv/Blocks.srv; do
  curl --retry 3 -fsSL "$LESSON/src/block_interfaces/$FILE" -o "src/block_interfaces/$FILE"
done
for FILE in package.xml setup.py setup.cfg config/blocks.json launch/sim.launch.py block_skills/__init__.py block_skills/capture.py block_skills/check.py block_skills/cli.py block_skills/geometry.py block_skills/reports.py block_skills/server.py resource/block_skills; do
  curl --retry 3 -fsSL "$LESSON/src/block_skills/$FILE" -o "src/block_skills/$FILE"
done
for FILE in Dockerfile entrypoint.sh; do
  curl --retry 3 -fsSL "$LESSON/docker/$FILE" -o "docker/$FILE"
done
curl --retry 3 -fsSL "$LESSON/.dockerignore" -o .dockerignore
chmod +x docker/entrypoint.sh
DOWNLOAD
```

**Expected:** `src/block_interfaces`, `src/block_skills` and `docker` now
contain files. If a download fails, repeat this block before continuing.
The block stops on a failed download instead of silently skipping a file.

### 1.4 Add the desktop launcher

Create `scripts/lab.sh` in VS Code:

```bash
code scripts/lab.sh
```

Paste the following supplied code and save with **Ctrl+S**. It maps your own
workspace and desktop into Docker. You do not need to modify the code.

```bash
#!/usr/bin/env bash
# Linux desktop launcher for the UR10e lab. Run from the desktop session.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

container_name=${LAB_CONTAINER:-ur10e}

case "${1:-start}" in
  stop)
    docker stop --time 15 "$container_name"
    exit
    ;;
  restart)
    docker stop --time 15 "$container_name"
    docker rm "$container_name"
    ;;
  start) ;;
  *) echo 'Usage: bash scripts/lab.sh {start|restart|stop}' >&2; exit 2 ;;
esac

: "${DISPLAY:?Run this command from a terminal in the Linux desktop session.}"
mkdir -p .container
printf 'root:x:0:0:root:/root:/bin/bash\nsim:x:%s:%s:Simulation:/tmp:/bin/bash\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n' \
  "$(id -u)" "$(id -g)" > .container/passwd
printf 'root:x:0:\nsim:x:%s:\nnogroup:x:65534:\n' "$(id -g)" > .container/group
# Copy only the current display cookie, accepting the container's hostname.
umask 077
: > .xauth
xauth nlist "$DISPLAY" | sed 's/^..../ffff/' | xauth -f .xauth nmerge -
if [[ ! -s .xauth ]]; then
  echo 'Desktop display access is unavailable. Run from the logged-in desktop terminal.' >&2
  exit 1
fi

docker run --detach --init --name "$container_name" \
  --user "$(id -u):$(id -g)" -e HOME=/tmp --shm-size=512m \
  -v "$PWD:/work" \
  -v "$PWD/.container/passwd:/etc/passwd:ro" \
  -v "$PWD/.container/group:/etc/group:ro" \
  -e "DISPLAY=$DISPLAY" -e XAUTHORITY=/work/.xauth \
  -e LIBGL_ALWAYS_SOFTWARE=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
  ur10e:humble ros2 launch block_skills sim.launch.py \
  gui:=true rviz:=true config:=/work/src/block_skills/config/blocks.json

docker exec "$container_name" /entrypoint.sh ros2 run block_skills blocks status --wait 150
```

**Expected:** `scripts/lab.sh` is saved in your workspace. This file is created
here explicitly, so the launch step does not depend on an unpublished helper.

### 1.5 Build the environment

Run from `~/ur10e-skills-lab`:

```bash
docker build -t ur10e:humble -f docker/Dockerfile .
```

**Expected:** The image is saved as `ur10e:humble`. Wait for the build to finish.
Then build the two custom packages:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/work" ur10e:humble bash -c \
  'colcon build --base-paths src --symlink-install --parallel-workers 2'
```

**Expected:** A summary containing `2 packages finished`, with no failed packages.

### Checkpoint 1

**Screenshot:** The build summary and workspace folders.

1. Which repository provides the robot model?
2. What is the purpose of the custom `block_skills` package?

## 2. Start Gazebo and RViz

```bash
bash scripts/lab.sh start
```

The launcher connects the Linux desktop to the container and starts the robot,
controllers and skill server. It handles display access automatically.

**Expected:** Gazebo and RViz open, followed by:

```text
ready=True; busy=False; holding=none; fault=none
```

In **Gazebo**, locate the UR10e, gripper, table and three blocks. In **RViz**,
expand the **MotionPlanning** display and locate the robot model. MoveIt plans
the motion; Gazebo shows its simulated execution.

Open a second Terminal for the remaining commands:

```bash
cd "$HOME/ur10e-skills-lab"
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks list
```

**Expected:** JSON records for these initial block centres, approximately:

| Block | x (m) | y (m) | z (m) |
| --- | --- | --- | --- |
| `red_block` | 0.55 | -0.28 | 0.675 |
| `blue_block` | 0.70 | 0.00 | 0.675 |
| `green_block` | 0.55 | 0.28 | 0.675 |

The values are measured from the current simulation and may vary slightly.

### Checkpoint 2

**Screenshot:** Gazebo and RViz, with the block list visible if space allows.

1. What does RViz display, and what does Gazebo simulate?
2. Where do the block positions come from?

## 3. Find the skills and modify the scene

### 3.1 Follow a command through the code

Open these files in VS Code. Use **Ctrl+F** to find the named functions:

| File under `src/` | Find | Purpose |
| --- | --- | --- |
| `block_skills/block_skills/cli.py` | `parser`, `goal.support_block` | Reads `pick` or `stack` arguments and creates a request |
| `block_interfaces/action/PickPlace.action` | `support_block`, `target` | Defines the task inputs and returned result |
| `block_skills/block_skills/server.py` | `tool_pose`, `move_to`, `verify_placement` | Calculates the tool pose, requests motion and measures the outcome |
| `block_skills/block_skills/geometry.py` | `table_top`, `validate_position` | Calculates geometry and validates destinations |
| `block_skills/config/blocks.json` | `blocks`, `approach_height` | Supplies starting positions and motion parameters |

```text
Terminal command → cli.py → PickPlace action → server.py → MoveIt → robot
                                                ↑                   │
                                                └── measured state ─┘
```

### 3.2 Edit the JSON configuration

```bash
code src/block_skills/config/blocks.json
```

Replace only the `green_block` entry in the `blocks` list with:

```json
{"name": "green_block", "color": "green", "position": [0.65, 0.28, 0.675], "yaw": 0.0}
```

In `colors`, change the green entry to:

```json
"green": [0.1, 0.9, 0.4, 1.0]
```

Keep the surrounding commas and braces. The four colour values are red, green,
blue and opacity. Save with **Ctrl+S**.

Restart to load the changed scene. Restarting resets block positions:

```bash
bash scripts/lab.sh restart
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks list
```

**Expected:** Green has a new shade and its x coordinate is approximately
`0.65`. Its y and z stay at `0.28` and `0.675`. The launcher reads the source
JSON directly, so this change needs a restart but no rebuild.

### Checkpoint 3

**Screenshot:** Your edited JSON beside the changed scene.

1. Which values changed the block's appearance and location?
2. Why did editing JSON alone not move the block in the running scene?

## 4. Calculate a block and gripper location

Positions use the Gazebo `world` frame, in metres. These Cartesian calculations
set a desired pose; MoveIt solves the robot's joint inverse kinematics.

### 4.1 Calculate the block centre

From `blocks.json`, the table centre is `(0.70, 0.00, 0.60)`, the table thickness
is `0.10`, and the cube side length is `0.05`.

```text
Table surface z = 0.60 + 0.10 / 2 = 0.650 m
Block centre z  = 0.650 + 0.05 / 2 = 0.675 m
```

Choose a destination offset from the table centre, such as
`dx = 0.12 m` and `dy = -0.28 m`:

```text
Target x = table centre x + dx = 0.70 + 0.12 = 0.82 m
Target y = table centre y + dy = 0.00 - 0.28 = -0.28 m
Target z = 0.675 m
```

Use x within `0.38–0.95` and y within `−0.45–0.45`. Leave at least `0.16 m`
between the destination and other block centres. For two points:

```text
separation = sqrt((x2 - x1)^2 + (y2 - y1)^2)
```

### 4.2 Calculate the approach pose

For an upright block before grasping, `tool_pose` adds `grasp_offset` and
`approach_height` to the block centre. The defaults are `0.015` and `0.18`:

```text
Tool grasp z    = 0.675 + 0.015        = 0.690 m
Tool approach z = 0.675 + 0.015 + 0.18 = 0.870 m
```

Its x and y match the block centre for this initial vertical approach. The
function also assigns the tool orientation; after grasping, it uses the
measured block-to-tool transform.

**Exercise:** Change `approach_height` to `0.20` in `blocks.json`, calculate the
new approach height, save, and run `bash scripts/lab.sh restart`. Your answer
should be **0.890 m**. Leave the other motion parameters unchanged.

### 4.3 Execute the placement

Create a small script in VS Code:

```bash
code place_block.py
```

Paste and save:

```python
import json
import subprocess
from pathlib import Path

config = json.loads(Path("src/block_skills/config/blocks.json").read_text())
cx, cy, cz = config["table"]["center"]
thickness = config["table"]["size"][2]
block_size = config["block_size"]

dx, dy = 0.12, -0.28
x, y = cx + dx, cy + dy
z = cz + thickness / 2 + block_size / 2
approach_z = z + config["grasp_offset"] + config["approach_height"]

print(f"Target block centre: ({x:.3f}, {y:.3f}, {z:.3f})", flush=True)
print(f"Approach z for a block at this height: {approach_z:.3f} m", flush=True)
subprocess.run(
    ["ros2", "run", "block_skills", "blocks", "pick", "red_block",
     str(x), str(y), str(z)],
    check=True,
)
```

Run it inside the container:

```bash
docker exec ur10e /entrypoint.sh python3 /work/place_block.py
```

**Expected:** The calculation prints `(0.820, -0.280, 0.675)` and `0.890 m`.
The robot moves red to the destination. A successful result includes:

```json
{
  "success": true,
  "verified": true,
  "holding_block": false
}
```

It also prints a measured `position`, `task_id` and `report_file`. In-bounds
positions can still fail motion planning; read `message` and adjust the target.
If a failure leaves `holding_block` true, restart before another request.

### Checkpoint 4

**Screenshot:** Your calculated coordinates, terminal result and moved block.

1. Show the calculation for the block centre and approach height.
2. Which part of the system converts the requested tool pose into joint motion?

## 5. Measure, adjust and repeat

Replace `TASK_ID` with the ID returned by your placement:

```bash
code artifacts/TASK_ID/result.json
```

**Expected:** `target.position` is the requested location and
`final_pose.position` is the measured location. Calculate the position error:

```text
error = sqrt((actual_x - target_x)^2
           + (actual_y - target_y)^2
           + (actual_z - target_z)^2)
```

For a successful table placement, the error should be at most **0.02 m**.
The skill also verifies orientation and stability.

Read the current block list again. Change `dx` or `dy` in `place_block.py` to
choose your own second clear destination. Save and rerun the script. Compare
the requested and measured positions from both tasks.

```text
Read state → Calculate target → Run skill → Measure error → Adjust next target
```

### Checkpoint 5

**Screenshot:** Your second placement and its result.

1. Record the target, measured position and error for both attempts.
2. How did the live state influence your second target?

## 6. Stack three blocks

Keep the scene after the second placement. Place blue on red:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack blue_block red_block
```

**Expected:** Blue rests on red, with `"success": true` and `"verified": true`.
Wait for completion, then use the same structure to stack green on blue:

```text
ros2 run block_skills blocks stack MOVING_BLOCK SUPPORT_BLOCK
```

Run it through `docker exec ur10e /entrypoint.sh`, as above.

**Expected:** Green on blue on red. Each extra block adds one cube side length:

| Block | Centre height |
| --- | --- |
| Red | 0.675 m |
| Blue | 0.675 + 0.05 = 0.725 m |
| Green | 0.725 + 0.05 = 0.775 m |

Keep the final task ID and its `artifacts/TASK_ID/result.json` and `scene.png`.
Repeat your green-on-blue command once.

**Expected:** `"already_complete": true`, with no new robot movement. The
repeated request creates its own task ID; keep the original stacking result.

### Checkpoint 6

**Screenshot:** Your completed tower and successful result. Show your name,
student ID and final task ID in VS Code beside Gazebo.

1. How does the stack skill calculate the next block's centre height?
2. Why does the repeated request finish without moving the robot?

## 7. Submit and finish

Submit one Word document with the six checkpoint screenshots and answers.
Include your coordinate calculations and two placement results. Attach
`place_block.py`, your modified `blocks.json` and the final stack's `result.json`.
Use your own targets and results; the TA may ask you to explain a code change
or demonstrate another placement.

After saving your work:

```bash
bash scripts/lab.sh stop
```

**Expected:** `ur10e`. Your files remain in the workspace.

**Further work:** Connect these skills to ABot-Claw using the
[integration notes](docs/ABOTCLAW_INTEGRATION.md).
