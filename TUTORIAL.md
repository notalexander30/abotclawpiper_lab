# UR10e Lab: Pick, Place and Stack

**Please complete the Checkpoint and Questions sections in this lab. Write your
answers and add the requested screenshots to your own copy of this page. If a
TA is present, ask them to check your result before continuing.**

**Name:**

**Student ID:**

In this lab, you will use an existing robotics framework to operate a UR10e
robot with a Robotiq gripper. You will download the robot framework from
GitHub, add a supplied skill package, and use the robot to move and stack
blocks. You do not need previous programming experience.

All terminal commands run on the Ubuntu computer unless stated otherwise.
Open a terminal using **Ctrl+Alt+T**. Copy only the commands inside each code
block. Keep the simulation running while completing the tasks.

## 1. Prepare the computer

Docker provides the software environment used by the robot. It contains ROS 2,
Gazebo and MoveIt, so everyone uses the same Ubuntu 22.04 environment.

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

Use an Ubuntu desktop with Internet access and at least 15 GB of free disk
space. `uname -s` should show `Linux`. `uname -m` shows the CPU type; the complete
lab has been verified on `x86_64`. The container supplies Ubuntu 22.04 and ROS 2
Humble, so you do not need to install ROS on the computer.

### 1.2 Install Git and desktop support

**Host terminal:**

```bash
sudo apt update
sudo apt install -y git ca-certificates curl xauth nano python3
```

Verify:

```bash
git --version
curl --version
command -v xauth
```

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

If Docker installation reports conflicting packages, follow the
[official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).

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

The `docker` group allows your account to control the Docker daemon.


## 2. Download the robot framework and add the skills

A robotics project usually combines existing packages with a smaller amount
of custom work. Here, IFRA provides the robot model, gripper, controllers and
MoveIt configuration. We add the table, blocks and reusable manipulation
skills in a separate package.

### 2.1 Download the required repositories

In the same terminal, enter:

```bash
cd "$HOME"
mkdir -p ur10e-skills-lab/{upstream,src,docker}
cd ur10e-skills-lab
```

Download the three required repositories. The `checkout` commands select the
versions used in this lab.

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

The repositories have different roles:

- `ros2_SimRealRobotControl`: UR10e, Robotiq gripper and motion configuration.
- `IFRA_LinkAttacher`: holds and releases a block during a simulated grasp.
- `gazebo_ros2_control`: connects the simulated joints to ROS controllers.

Keep these downloaded repositories unchanged. Put your additions in `src/`.

### 2.2 Add the supplied skill packages

The IFRA framework does not include this lab's colored-block tasks. Add the
provided files to your workspace. These commands download individual lesson
files; you do not clone the completed lab repository.

Enter:

```bash
LESSON=https://raw.githubusercontent.com/notalexander30/abotclawpiper_lab/94c5cab
mkdir -p src/block_interfaces/{action,msg,srv}
mkdir -p src/block_skills/{block_skills,config,launch,resource}

for FILE in CMakeLists.txt package.xml action/PickPlace.action msg/Block.msg srv/Blocks.srv; do
  curl -fL "$LESSON/src/block_interfaces/$FILE" -o "src/block_interfaces/$FILE" || break
done

for FILE in package.xml setup.py setup.cfg config/blocks.json launch/sim.launch.py block_skills/__init__.py block_skills/capture.py block_skills/check.py block_skills/cli.py block_skills/geometry.py block_skills/reports.py block_skills/server.py resource/block_skills; do
  curl -fL "$LESSON/src/block_skills/$FILE" -o "src/block_skills/$FILE" || break
done

curl -fL "$LESSON/docker/Dockerfile" -o docker/Dockerfile
curl -fL "$LESSON/docker/entrypoint.sh" -o docker/entrypoint.sh
chmod +x docker/entrypoint.sh
```

If a download reports an error, stop and repeat the failed download before
continuing.

You have added two ROS packages:

- `block_interfaces` defines the information sent to and returned by a skill.
- `block_skills` implements pose lookup, robot motion, stacking and results.

A skill is a reusable operation with a clear input and result. For example,
“stack blue on red” is one operation. Later, a coding agent can request this
operation through the same ROS interface.

### 2.3 Look at the scene configuration and build

Open the scene configuration:

```bash
nano src/block_skills/config/blocks.json
```

Find `blocks`, `colors`, `block_size` and `table`. These describe the starting
scene. The robot model itself comes from IFRA. The table and cubes are created
by the custom package.

For now, read the file without changing it. Press **Ctrl+X** to close nano.

Build the software environment:

```bash
docker build -t ur10e:humble -f docker/Dockerfile .
```

The first build downloads several gigabytes. Wait until it completes, then
build the two custom packages:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "$PWD:/work" \
  ur10e:humble bash -c \
  'colcon build --base-paths src --symlink-install --parallel-workers 2'
```

The summary should show both custom packages finished. A build makes the
packages available to ROS; it does not start the robot.

### 2.4 Prepare the desktop user

These files map the desktop user's UID and GID into Docker so generated files
remain owned by the student.

```bash
mkdir -p .container
printf 'root:x:0:0:root:/root:/bin/bash\nsim:x:%s:%s:Simulation:/tmp:/bin/bash\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n' \
  "$(id -u)" "$(id -g)" > .container/passwd
printf 'root:x:0:\nsim:x:%s:\nnogroup:x:65534:\n' \
  "$(id -g)" > .container/group
```


### Checkpoint and Questions 1

1. Which repository supplies the UR10e robot and gripper?
2. Why do we add our own skills in `src/` instead of changing IFRA's files?
3. In `blocks.json`, which setting controls the cube size?

**Answers:**

---

## 3. Launch and understand the simulation

Gazebo simulates the robot and physical objects. MoveIt plans the robot's
movements. RViz displays the robot model and the planned movements. ROS 2
allows these parts to exchange commands and state information.

### 3.1 Prepare X11 authentication

Run this from a terminal opened directly in the Ubuntu desktop session:

```bash
echo "$DISPLAY"
touch .xauth
xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | \
  xauth -f .xauth nmerge -
test -s .xauth && echo "GUI authentication ready"
```

Do not continue unless the last message appears.

### 3.2 Start the complete simulation

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


### 3.3 Observe Gazebo, RViz and MoveIt

In Gazebo, find the robot, gripper, table and three colored blocks. In RViz,
find the **MotionPlanning** display and expand it if needed. MoveIt runs in the
background; it does not have a separate application window.

Open a new terminal and enter:

```bash
cd "$HOME/ur10e-skills-lab"
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks list
```

The list shows each block's model name, color, position and orientation. The
positions come from the current Gazebo state. There is no camera or OpenCV
object detection in this lab.

### Checkpoint and Questions 2

**Task:** Take a screenshot showing Gazebo with the robot, table and three
blocks, and RViz with its MotionPlanning display. Use two screenshots if the
windows do not fit clearly on one screen.

1. What does Gazebo do?
2. What does MoveIt do, and what does RViz show?
3. Where does the block skill obtain the current block position?

**Answers:**

**Insert your screenshot(s) here.**

---

## 4. Choose a position and move a block

The robot needs a destination to place a block. In this task, choose that
position yourself using the scene and the available workspace.

### 4.1 Find a destination

List the current block positions again:

```bash
docker exec ur10e /entrypoint.sh ros2 run block_skills blocks list
```

Open the configuration in another terminal:

```bash
cd "$HOME/ur10e-skills-lab"
nano src/block_skills/config/blocks.json
```

Find `workspace`, `table` and `block_size`. Use these values to choose a free
position on the table:

- Choose x and y inside the configured workspace limits.
- Keep the destination clear of the other blocks. Use at least the configured
  `spacing` between block centres.
- Coordinates are in metres in Gazebo's `world` frame.
- z is the height of the **centre of the block**, not its bottom face.

Calculate the block's resting height using:

```text
block centre z = table centre z + table thickness / 2 + block size / 2
```

Close nano with **Ctrl+X**. Write down your destination before moving:

**Chosen x:**

**Chosen y:**

**Calculated z:**

### 4.2 Pick and place

Enter the following commands. When prompted, type the numbers you chose and
press Enter after each one:

```bash
read -r -p "Target x (metres): " TARGET_X
read -r -p "Target y (metres): " TARGET_Y
read -r -p "Block centre z (metres): " TARGET_Z

docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks pick red_block "$TARGET_X" "$TARGET_Y" "$TARGET_Z"
```

Observe the robot in Gazebo and the planned movement in RViz. The skill reads
the block's current pose, plans the motion, grasps and attaches the block,
moves it, releases it and checks the final pose.

Wait until the command finishes. A completed task reports `success: true` and
`verified: true`. If it fails, read the message and adjust your destination;
do not report a failed task as completed.

### Checkpoint and Questions 3

**Task:** Move the red block to your chosen position using the robot. Take a
screenshot of the result and include the x, y and z you used.

1. How did you choose a free destination?
2. Why is the block centre higher than the top surface of the table?
3. Which part of the system plans the robot's movement?

**Answers:**

**Insert your screenshot here.**

---

## 5. Final task: stack three blocks

A stack command describes a relationship between two objects. The skill looks
up the support block's latest pose and calculates the destination above it.
You do not have to type target coordinates for this operation.

Use the scene from the previous task. Confirm all three blocks are still
resting separately on the table before starting.

### 5.1 Stack blue on red

Enter:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack blue_block red_block
```

The first name is the block to pick up. The second is the block supporting it.
Wait for `success: true` and `verified: true` before continuing.

### 5.2 Stack green on blue

Enter:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack green_block blue_block
```

The completed stack should have this order:

```text
green
blue
red
─────── table
```

If `BLOCK_NOT_TOP` appears, another block is resting on the block you are
trying to pick up. Remove the top block first. This skill moves one block at
a time, so the order of operations matters.

### 5.3 Read the result

The command returns a task ID, a result file and a screenshot path. On the
computer, they are stored under:

```text
ur10e-skills-lab/artifacts/TASK_ID/scene.png
ur10e-skills-lab/artifacts/TASK_ID/result.json
```

Replace `TASK_ID` with the ID shown in your output. Open the workspace in the
file manager, enter `artifacts`, and open the folder with that ID.

The screenshot shows the scene for a person to review. The JSON result records
whether placement was verified and where the evidence was saved. A future
agent can read this result to report completion.

Repeat the final command:

```bash
docker exec ur10e /entrypoint.sh \
  ros2 run block_skills blocks stack green_block blue_block
```

If the arrangement still exists, the result should say `already_complete:
true`. The skill checks the stack without moving the robot again.

### Final Checkpoint and Questions

**Task:** Show a three-block stack with red at the bottom, blue in the middle
and green on top. Include the successful terminal result and a screenshot.

For an identifiable submission, open a text editor beside Gazebo and type
your name, student ID and “UR10e stacking task”. Capture both in a desktop
screenshot. Save it as `StudentID_final_stack.png`. Use a second screenshot if
needed to make the terminal result readable.

1. Why does `stack` work without you entering coordinates?
2. Why must blue be placed on red before green is placed on blue?
3. What does `verified: true` tell you? Is a screenshot alone enough to prove
   that the program verified the placement?
4. If a future AI agent requests “stack green on blue”, which existing skill
   could it call, and what result should it check before reporting success?

**Answers:**

**Insert your named final screenshot and result screenshot here.**

**Submission checklist:**

- [ ] Name and student ID filled in at the top of the page.
- [ ] Answers completed for each checkpoint.
- [ ] Gazebo and RViz screenshots included.
- [ ] Chosen placement coordinates and a successful move shown.
- [ ] Final three-block stack and successful result shown.
- [ ] Name and student ID visible in the final screenshot.

---

## 6. Optional task: add another colored block

Complete the three-block task before this activity. The configured stack limit
is three, so the extra block should remain on the table.

### 6.1 Create a small Python file

This example shows how a short program can reuse an existing skill instead of
implementing robot control again. No previous Python experience is required.

In a terminal on the Ubuntu computer, enter:

```bash
cd "$HOME/ur10e-skills-lab"
nano add_block.py
```

Paste this code into nano:

```python
import subprocess

# Change the color or model name for your own task.
color = "yellow"
model_name = "yellow_extra"

subprocess.run(
    ["ros2", "run", "block_skills", "blocks", "add",
     color, "--name", model_name],
    check=True,
)
```

Press **Ctrl+O**, then **Enter** to save. Press **Ctrl+X** to exit.

The file calls the existing `add` operation. That operation chooses a random
free position within the configured workspace. Its color must exist in
`blocks.json`; yellow is already available. Each model name must be unique.

Run the file inside the ROS container:

```bash
docker exec ur10e /entrypoint.sh python3 /work/add_block.py
```

The host workspace is mounted as `/work` in Docker, so the container can see
the Python file you just created.

### Optional Checkpoint and Questions

**Task:** Add a yellow block and take a screenshot showing it on the table
beside your completed stack.

1. Did adding the block require the robot to move?
2. Which line specifies the block color?
3. Where did the new block's position come from?

**Answers:**

**Insert your screenshot here.**

---

## 7. Stop the simulation

When your screenshots and answers are saved, enter:

```bash
docker stop --time 15 ur10e
docker rm ur10e
```

Your files remain in the workspace. Starting a new container with the launch
command in section 3 creates a fresh scene.

### If something goes wrong

- **Package not found:** Complete the custom package build and use
  `/entrypoint.sh` in the commands shown above.
- **Gazebo or RViz does not open:** Run from the Ubuntu desktop and repeat the
  X11 authentication step in section 3.1.
- **The robot does not move:** Wait for readiness and read the returned error.
  A goal preview in RViz alone does not execute a movement.
- **Invalid destination or planning failure:** Choose a free position inside
  the configured workspace. A position inside those limits can still be
  unsuitable for the robot's motion.
- **A block is still held after a failure:** Reset the simulation before
  trying another manipulation task.

To read the recent simulation messages:

```bash
docker logs --tail 100 ur10e
```

To reset, remove the container and repeat section 3.2:

```bash
docker rm -f ur10e
```
