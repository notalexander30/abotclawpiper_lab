FROM ros:humble-ros-base-jammy@sha256:566b87e6dfc48392189a9c32e594e84060fa9948de93b04e536f39475a1f6963
SHELL ["/bin/bash", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git python3-colcon-common-extensions python3-pytest \
    python3-numpy python3-yaml ros-humble-xacro \
    ros-humble-moveit ros-humble-ros2-control ros-humble-ros2-controllers \
    ros-humble-gazebo-ros-pkgs ros-humble-gazebo-dev \
    ros-humble-rmw-cyclonedds-cpp ros-humble-rviz2 \
    ros-humble-robot-state-publisher libgl1-mesa-dri mesa-utils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/ifra
COPY upstream/ros2_SimRealRobotControl /opt/ifra/src/ros2_SimRealRobotControl
COPY upstream/IFRA_LinkAttacher /opt/ifra/src/IFRA_LinkAttacher
COPY upstream/gazebo_ros2_control/gazebo_ros2_control /opt/ifra/src/gazebo_ros2_control
RUN source /opt/ros/humble/setup.bash && \
    colcon build --parallel-workers 2 --packages-select \
      ros2srrc_robots ros2srrc_endeffectors ros2srrc_ur10e ros2srrc_moveit \
      linkattacher_msgs ros2_linkattacher gazebo_ros2_control \
      --cmake-args -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV ROS_DOMAIN_ID=42
ENV GAZEBO_MODEL_DATABASE_URI=""
ENV QT_X11_NO_MITSHM=1
COPY docker/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
WORKDIR /work
CMD ["bash"]
