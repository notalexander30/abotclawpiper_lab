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
