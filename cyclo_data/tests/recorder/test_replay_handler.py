# Copyright 2025 ROBOTIS CO., LTD.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Author: Dongyun Kim

from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

import pytest
import numpy as np
import json


_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "cyclo_data"))


def _stub_module(name: str, **attrs) -> None:
    if name in sys.modules:
        module = sys.modules[name]
        for key, value in attrs.items():
            setattr(module, key, value)
        return

    parts = name.split(".")
    for idx in range(1, len(parts)):
        parent = ".".join(parts[:idx])
        sys.modules.setdefault(parent, ModuleType(parent))

    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


class _Dummy:
    def __init__(self, *args, **kwargs):
        pass


_stub_module("geometry_msgs.msg", Twist=_Dummy)
_stub_module("nav_msgs.msg", Odometry=_Dummy)
_stub_module("sensor_msgs.msg", JointState=_Dummy)
_stub_module("trajectory_msgs.msg", JointTrajectory=_Dummy)
_stub_module("rclpy.serialization", deserialize_message=lambda *args, **kwargs: None)
_stub_module(
    "rosbag2_py",
    SequentialReader=_Dummy,
    StorageOptions=_Dummy,
    ConverterOptions=_Dummy,
    StorageFilter=_Dummy,
)

from cyclo_data.recorder.replay_handler import ReplayDataHandler  # noqa: E402


def test_missing_bag_replay_response_keeps_3d_viewer_fields(tmp_path):
    result = ReplayDataHandler().get_replay_data(str(tmp_path / "missing"))

    assert result["success"] is False
    assert result["urdf_path"] == ""
    assert result["end_effector_links"] == []


def test_robot_semantic_layout_resolves_replay_urdf_path(tmp_path, monkeypatch):
    config_dir = tmp_path / "robot_configs"
    urdf_dir = config_dir / "urdf"
    urdf_dir.mkdir(parents=True)
    (urdf_dir / "test_bot.urdf").write_text("<robot name='test_bot' />\n")
    (config_dir / "test_bot_config.yaml").write_text(
        """
orchestrator:
  ros__parameters:
    test_bot:
      urdf_path: urdf/test_bot.urdf
      visualization:
        end_effector_links:
          - tool0
      observation:
        state:
          arm:
            topic: /state
            joint_names: [joint_1, joint_2]
      action:
        arm:
          topic: /action
          joint_names: [joint_1, joint_2]
""".lstrip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("ORCHESTRATOR_CONFIG_PATH", str(tmp_path / "unused"))
    monkeypatch.setenv("ROBOT_CLIENT_CONFIG_DIR", str(config_dir))

    layout = ReplayDataHandler()._load_robot_semantic_layout("test_bot")

    assert layout["urdf_path"] == str((urdf_dir / "test_bot.urdf").resolve())
    assert layout["end_effector_links"] == ["tool0"]
    assert layout["state"]["arm"]["topic"] == "/state"
    assert layout["action"]["arm"]["topic"] == "/action"


@pytest.mark.parametrize("segmented", [False, True])
def test_replays_raw_tactile_on_joint_clock(tmp_path, monkeypatch, segmented):
    from cyclo_data.recorder import replay_handler

    _stub_module("robotis_interfaces.msg", HandPressures=_Dummy)
    (tmp_path / "episode.mcap").touch()
    left = "/left_hand/finger_pressures"
    right = "/right_hand/finger_pressures"
    raw = [255, 0, 1, 2, 3, 4, 5, 6, 7]
    tactile = SimpleNamespace(sensors=[SimpleNamespace(
        sensor_name="finger_l_sensor1", pressure_names=["p1"],
        pressure_values=np.array(raw, dtype=np.uint8),
    )])
    joint = SimpleNamespace(name=["joint1"], position=[0.5])
    messages = [
        ("/state", joint, 10_000_000_000),
        (left, tactile, 10_100_000_000),
        (right, tactile, 10_200_000_000),
        (left, tactile, 20_100_000_000),
    ]

    class Reader:
        def open(self, *_args):
            self.rows = iter(messages)
            self.remaining = len(messages)

        def get_all_topics_and_types(self):
            return [SimpleNamespace(name=topic, type=kind) for topic, kind in [
                ("/state", "sensor_msgs/msg/JointState"),
                (left, "robotis_interfaces/msg/HandPressures"),
                (right, "robotis_interfaces/msg/HandPressures"),
            ]]

        def set_filter(self, _filter):
            pass

        def has_next(self):
            return self.remaining > 0

        def read_next(self):
            self.remaining -= 1
            return next(self.rows)

    monkeypatch.setattr(replay_handler, "SequentialReader", Reader)
    monkeypatch.setattr(replay_handler, "deserialize_message", lambda data, _kind: data)
    handler = ReplayDataHandler()
    monkeypatch.setattr(handler, "_replay_sample_bucket_seconds", lambda *_: 1 / 30)
    if segmented:
        monkeypatch.setattr(handler, "_build_segment_time_map", lambda *_: [
            {"wall_start_ns": 10_000_000_000, "wall_end_ns": 11_000_000_000,
             "replay_start_s": 0, "replay_end_s": 1},
            {"wall_start_ns": 20_000_000_000, "wall_end_ns": 21_000_000_000,
             "replay_start_s": 1, "replay_end_s": 2},
        ])

    result = handler.get_replay_data(str(tmp_path))

    assert result["success"], result["message"]
    assert result["joint_timestamps"] == [0]
    assert result["tactile_data"]["left"]["timestamps"] == pytest.approx(
        [0.1, 1.1 if segmented else 10.1]
    )
    assert result["tactile_data"]["right"]["timestamps"] == pytest.approx([0.2])
    sensor = result["tactile_data"]["left"]["messages"][0]["sensors"][0]
    assert sensor["pressure_values"] == raw
    assert sensor["sensor_name"] == "finger_l_sensor1"
    assert sensor["pressure_names"] == ["p1"]
    json.dumps(result["tactile_data"], allow_nan=False)
