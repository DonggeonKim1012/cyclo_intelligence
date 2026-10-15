#!/usr/bin/env bash
set -eo pipefail
mkdir -p /workspace/.web-relay
python3 /validation/cyclo_ws/src/cyclo_intelligence/docker/lg2-sh5/relay.py > /workspace/.web-relay/relay.log 2>&1 &
relay_pid=$!
trap 'kill "$relay_pid" 2>/dev/null || true' EXIT
source /validation/cyclo_ws/install/setup.bash
export COLCON_WS=/validation/cyclo_ws
export PYTHONPATH="/opt/validation-venv/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export CYCLO_SUPERVISOR_API_REPO_MOUNT=/validation/cyclo_ws/src/cyclo_intelligence
export CYCLO_SUPERVISOR_API_CONTAINER_NAME=cyclo_lg2_sh5
export CYCLO_BT_TREES_DIR=/workspace/bt/trees
export CYCLO_BT_EXAMPLE_TREES_DIR=/validation/cyclo_ws/install/orchestrator/share/orchestrator/bt/trees
export CYCLO_ROBOT_CONFIGS_DIR=/validation/cyclo_ws/install/shared/share/shared/robot_configs
# No Docker socket or s6: no authority to start/stop other containers/services.
/opt/validation-venv/bin/python -m uvicorn supervisor_api.app:app \
  --app-dir /validation/cyclo_ws/src/cyclo_intelligence/docker \
  --host 127.0.0.1 --port 7100 > /workspace/.web-relay/supervisor.log 2>&1
