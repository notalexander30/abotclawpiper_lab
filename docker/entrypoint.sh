#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash
source /opt/ifra/install/setup.bash
export GAZEBO_PLUGIN_PATH="/opt/ifra/install/ros2_linkattacher/lib:/opt/ifra/install/gazebo_ros2_control/lib:${GAZEBO_PLUGIN_PATH:-}"
if [[ -f /work/install/setup.bash ]]; then source /work/install/setup.bash; fi
exec "$@"
