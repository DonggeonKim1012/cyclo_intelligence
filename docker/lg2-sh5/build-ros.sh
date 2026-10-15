#!/usr/bin/env bash
set -eo pipefail
cd /validation/cyclo_ws
for artifact in build install log; do
  if [ -e "$artifact" ]; then
    echo "Refusing to reuse /validation/cyclo_ws/$artifact; use a fresh deployment root." >&2
    exit 2
  fi
done
source /opt/ros/jazzy/setup.bash
export CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2
colcon build --paths src/cyclo_intelligence/orchestrator src/cyclo_intelligence/cyclo_data \
  src/cyclo_intelligence/cyclo_data/recorder/rosbag_recorder \
  src/cyclo_intelligence/interfaces src/cyclo_intelligence/shared src/robotis_interfaces \
  --parallel-workers 2 --event-handlers console_cohesion+ \
  --cmake-args -DCMAKE_BUILD_TYPE=Release
