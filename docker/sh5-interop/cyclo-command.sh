#!/usr/bin/env bash
set -eo pipefail
if [[ " $* " != *' --show-args '* ]] && pgrep -f '^/usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch orchestrator cyclo_intelligence_bringup.launch.py' >/dev/null; then
  echo 'Cyclo Intelligence is already running in this container.'
  exit 0
fi
source /validation/cyclo_ws/install/setup.bash
export COLCON_WS=/validation/cyclo_ws
export PYTHONPATH="/opt/validation-venv/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export ROS_DOMAIN_ID=174 RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE='transport/shared_memory/enabled=false;scouting/multicast/enabled=false;connect/endpoints=["tcp/127.0.0.1:17447"]'
export CYCLO_BIND_ADDRESS=127.0.0.1 CYCLO_ROSBRIDGE_PORT=17790
export CYCLO_VIDEO_SERVER_PORT=17782 CYCLO_VIDEO_PUBLIC_PORT=7082
export CYCLO_WEB_VIDEO_SERVER_PORT=17785 CYCLO_CAMERA_PREVIEW_PORT=17786
exec flock -n -E 73 /workspace/cyclo.lock ros2 launch orchestrator cyclo_intelligence_bringup.launch.py "$@"
