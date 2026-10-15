# Context: the fresh deployment root described in README.md.
# Only dependencies are installed here; ROS packages/UI are built in a fresh bind mount.
FROM ros@sha256:066420e07f60aa18262f2479981def87ebcfcec42eefb0c0c57c4a46098348ca
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_EXTRA_INDEX_URL=""
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions python3-rosdep python3-vcstool \
    python3-pip python3-venv git build-essential cmake ffmpeg \
    ros-jazzy-rmw-zenoh-cpp ros-jazzy-map-msgs
COPY cyclo_ws/src /dependency-src
RUN (test -f /etc/ros/rosdep/sources.list.d/20-default.list || rosdep init) && \
    rosdep update --rosdistro jazzy && source /opt/ros/jazzy/setup.bash && \
    rosdep install --from-paths /dependency-src/cyclo_intelligence/orchestrator \
      /dependency-src/cyclo_intelligence/cyclo_data \
      /dependency-src/cyclo_intelligence/cyclo_data/recorder/rosbag_recorder \
      /dependency-src/cyclo_intelligence/interfaces /dependency-src/cyclo_intelligence/shared \
      /dependency-src/robotis_interfaces --ignore-src --rosdistro jazzy -y && \
    python3 -m venv --system-site-packages /opt/validation-venv && \
    /opt/validation-venv/bin/pip install --no-cache-dir \
      'numpy<2' torch==2.7.0 psutil matplotlib pandas huggingface_hub \
      mcap mcap-ros2-support pyarrow==24.0.0 \
      -r /dependency-src/cyclo_intelligence/docker/supervisor_api/requirements.txt
WORKDIR /workspace
ENTRYPOINT ["/bin/sleep"]
CMD ["infinity"]
