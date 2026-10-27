source /etc/bash.bashrc
source /validation/cyclo_ws/install/setup.bash
export COLCON_WS=/validation/cyclo_ws
export PYTHONPATH="/opt/validation-venv/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export ROS_DOMAIN_ID=174 RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE='transport/shared_memory/enabled=false;scouting/multicast/enabled=false;connect/endpoints=["tcp/127.0.0.1:17447"]'
cd "$HOME/ros2_ws" || return
cyclo_intelligence() { bash /validation/web/cyclo-command.sh "$@"; }
PS1='\u@cyclo:\w\$ '
