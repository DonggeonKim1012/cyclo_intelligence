#!/usr/bin/env bash
set -eo pipefail
mkdir -p /workspace/.web-relay
python3 /validation/web/relay.py > /workspace/.web-relay/relay.log 2>&1 &
relay_pid=$!
trap 'kill "$relay_pid" 2>/dev/null || true' EXIT
source /validation/cyclo_ws/install/setup.bash
export COLCON_WS=/validation/cyclo_ws
export PYTHONPATH="/opt/validation-venv/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export CYCLO_SUPERVISOR_API_REPO_MOUNT=/validation/cyclo_ws/src/cyclo_intelligence
export CYCLO_SUPERVISOR_API_CONTAINER_NAME=cyclo_clean_real_20261015
export CYCLO_BT_TREES_DIR=/workspace/bt/trees
export CYCLO_BT_EXAMPLE_TREES_DIR=/validation/cyclo_ws/install/orchestrator/share/orchestrator/bt/trees
export CYCLO_ROBOT_CONFIGS_DIR=/validation/cyclo_ws/install/shared/share/shared/robot_configs
# This deployment explicitly controls only the clean AI Worker. Docker socket
# access is host-privileged; do not expose this API to untrusted networks.
export CYCLO_NAVIGATION_CONTAINER=ai_worker_full_real_20261015
export CYCLO_NAVIGATION_BACKEND=process
export CYCLO_NAVIGATION_ROS_SETUP=/full/runtime-env.sh
export CYCLO_NAVIGATION_MAPS_DIR=/full/runtime-update/src/ai_worker/ffw_navigation/maps
export CYCLO_NAVIGATION_PARAMS_FILE=/full/runtime-update/src/ai_worker/ffw_navigation/config/navigation.yaml
export ROS_DOMAIN_ID=174 RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE='transport/shared_memory/enabled=false;scouting/multicast/enabled=false;connect/endpoints=["tcp/127.0.0.1:17447"]'
/opt/validation-venv/bin/python -m uvicorn supervisor_api.app:app \
  --app-dir /validation/cyclo_ws/src/cyclo_intelligence/docker \
  --host 127.0.0.1 --port 17710 > /workspace/.web-relay/supervisor.log 2>&1
