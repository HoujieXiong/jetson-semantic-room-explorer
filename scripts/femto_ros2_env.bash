# Source this file before running the locally built ROS camera or its checks.
source /opt/ros/humble/setup.bash || return
export FEMTO_ROS2_WS="${HOME}/projects/femto_ros2_ws"
if [[ ! -x "${FEMTO_ROS2_WS}/install/orbbec_camera/lib/orbbec_camera/orbbec_camera_node" ]]; then
    echo "Build the Femto ROS workspace first; see docs/camera-ros2.md" >&2
    return 1
fi
source "${FEMTO_ROS2_WS}/install/local_setup.bash" || return
# The six extracted Debian packages have no workspace-level setup script.
export AMENT_PREFIX_PATH="${FEMTO_ROS2_WS}/deps/opt/ros/humble:${AMENT_PREFIX_PATH}"
export LD_LIBRARY_PATH="${FEMTO_ROS2_WS}/deps/opt/ros/humble/lib:${LD_LIBRARY_PATH}"
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=42
