# Source in a fresh shell, separate from the native and camera OpenCV overlays.
if [[ -n "${VIRTUAL_ENV:-}" || "${AMENT_PREFIX_PATH:-}:${LD_LIBRARY_PATH:-}" == *femto_ros2_ws* ]]; then
    echo "Use a fresh system-Python shell without the Femto camera overlay." >&2
    return 1
fi
source /opt/ros/humble/setup.bash || return
export RTABMAP_ODOM_WS="${HOME}/projects/rtabmap_odom_ws"
export RTABMAP_ODOM_PREFIX="${RTABMAP_ODOM_WS}/deps/opt/ros/humble"
if [[ ! -x "${RTABMAP_ODOM_PREFIX}/lib/rtabmap_odom/rgbd_odometry" ]]; then
    echo "RTAB-Map dependencies are missing; see docs/rtabmap-odometry.md." >&2
    return 1
fi
export AMENT_PREFIX_PATH="${RTABMAP_ODOM_PREFIX}:${AMENT_PREFIX_PATH}"
export LD_LIBRARY_PATH="${RTABMAP_ODOM_PREFIX}/lib:${RTABMAP_ODOM_PREFIX}/lib/aarch64-linux-gnu:${RTABMAP_ODOM_WS}/deps/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH}"
export PYTHONPATH="${RTABMAP_ODOM_PREFIX}/local/lib/python3.10/dist-packages:${PYTHONPATH}"
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=43
