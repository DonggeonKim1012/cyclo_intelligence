#!/usr/bin/env python3
"""Tests for the GR00T Engine-process factory contract."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import time
import numpy as np
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
INFERENCE_ENGINE = ROOT / "cyclo_brain/policy/groot/runtime/inference_engine.py"


def _install_stub(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class GR00TEngineFactoryTests(unittest.TestCase):
    def _module(self):
        spec = importlib.util.spec_from_file_location("groot_sh5_test", INFERENCE_ENGINE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_checkpoint_tactile_detection(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"use_tactile": True}))
            self.assertEqual(module.GR00TInference.checkpoint_policy_kwargs(directory), {"use_tactile": True})
            config.write_text("{}")
            self.assertEqual(module.GR00TInference.checkpoint_policy_kwargs(directory), {})
            config.write_text('{"use_tactile": "false"}')
            with self.assertRaises(ValueError):
                module.GR00TInference.checkpoint_policy_kwargs(directory)

    def test_load_passes_tactile_flag_and_returns_controller_keys(self):
        module = self._module()
        captured = {}
        module.Gr00tPolicy = lambda **kwargs: captured.update(kwargs) or object()
        engine = module.GR00TInference()
        engine._sync_hf_token_for_gated_backbones = lambda: None
        engine.init_policy_info = lambda: None
        engine.policy_info["action"] = ["left_arm", "right_arm", "left_hand", "right_hand"]
        def init_robot(_robot_type):
            engine.robot_info["action_keys"] = engine.SH5_JOINT_KEYS
            engine.robot = types.SimpleNamespace(wait_for_ready=lambda **kwargs: True)
        engine.init_robot_info = init_robot
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "config.json").write_text('{"use_tactile": true}')
            result = engine.load_policy(types.SimpleNamespace(model_path=directory, robot_type="ffw_sh5_rev1"))
        self.assertTrue(result["success"], result)
        self.assertTrue(captured["use_tactile"])
        self.assertEqual(result["action_keys"], ["arm_left", "arm_right", "hand_left", "hand_right"])

    def test_sh5_mapping_raw_pressures_and_action_order(self):
        import yaml

        module = self._module()
        section = yaml.safe_load((ROOT / "shared/shared/robot_configs/ffw_sh5_rev1_config.yaml").read_text())["orchestrator"]["ros__parameters"]["ffw_sh5_rev1"]
        captured = {}
        groups = {f"follower_{key}": value for key, value in section["action"].items() if key != "mobile"}
        samples = {
            f"tactile_{side}_hand_pressure": {
                "taxels": (np.arange(45, dtype=np.float32) + offset).reshape(5, 3, 3),
                "received_monotonic": time.monotonic(),
            }
            for side, offset in (("left", 0), ("right", 100))
        }

        def robot_factory(robot_type, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                _config={"cameras": {key: {} for key in kwargs["requested_camera_names"]},
                         "joint_groups": groups, "sensors": {key: {} for key in samples}},
                _action_groups=section["action"], camera_names=kwargs["requested_camera_names"],
                joint_group_names=list(groups), get_sensor=samples.get,
            )

        module.RobotClient = robot_factory
        module.resolve_camera_feature_sources = lambda keys, available: {key: key for key in keys}
        engine = module.GR00TInference()
        engine.policy = types.SimpleNamespace(processor=types.SimpleNamespace(
            use_tactile=True, tactile_state_keys=["tactile_left", "tactile_right"], tactile_input_shape=(2, 5, 9)))
        keys = ["left_arm", "right_arm", "left_hand", "right_hand"]
        engine.policy_info = {"video": ["cam_left_head"], "state": keys + ["tactile_left", "tactile_right"],
                              "action": keys, "language": ["annotation.human.task_description"]}
        engine.init_robot_info("ffw_sh5_rev1")
        self.assertTrue(captured["enable_tactile"])
        self.assertTrue(captured["strict_sh5_tactile"])
        self.assertEqual(engine.command_action_keys(), ["arm_left", "arm_right", "hand_left", "hand_right"])
        joints = {key: np.arange(len(value["joint_names"]), dtype=np.float32) for key, value in groups.items()}
        images = {"cam_left_head": np.zeros((360, 640, 3), dtype=np.uint8)}
        obs = engine.preprocess(images, joints, "pick")
        np.testing.assert_array_equal(obs["state"]["tactile_right"][0, 0], np.arange(45) + 100)
        self.assertEqual(obs["state"]["left_hand"].shape, (1, 1, 20))
        actions = {key: np.full((1, 40, width), i, dtype=np.float32)
                   for i, (key, width) in enumerate(zip(keys, [7, 7, 20, 20]))}
        chunk = engine.postprocess_action(actions)
        self.assertEqual((chunk["chunk_size"], chunk["action_dim"]), (40, 54))
        np.testing.assert_array_equal(chunk["action_chunk"].reshape(40, 54)[0], np.repeat(range(4), [7, 7, 20, 20]))
        samples["tactile_left_hand_pressure"]["received_monotonic"] = time.monotonic() - 10
        self.assertFalse(engine.preprocess(images, joints, "pick")["success"])
        samples.pop("tactile_left_hand_pressure")
        self.assertFalse(engine.preprocess(images, joints, "pick")["success"])
        actions.pop("left_hand")
        self.assertFalse(engine.postprocess_action(actions)["success"])

    def test_legacy_robot_does_not_enable_tactile(self):
        module = self._module()
        captured = {}
        def robot_factory(robot_type, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(_config={"cameras": {}, "sensors": {}},
                                         camera_names=[], joint_group_names=["follower_arm_left"])
        module.RobotClient = robot_factory
        engine = module.GR00TInference()
        engine.policy = types.SimpleNamespace(processor=types.SimpleNamespace())
        engine.policy_info = {"video": [], "state": ["arm_left"], "action": ["arm_left"], "language": []}
        engine.init_robot_info("ffw_sg2_rev1")
        self.assertEqual(captured, {})
        self.assertEqual(engine.command_action_keys(), ["arm_left"])

    def setUp(self):
        self._saved_modules = dict(sys.modules)

        _install_stub(
            "cv2",
            ROTATE_90_CLOCKWISE=0,
            ROTATE_180=1,
            ROTATE_90_COUNTERCLOCKWISE=2,
        )
        _install_stub("torch", inference_mode=lambda: None)
        _install_stub("gr00t")
        _install_stub("gr00t.model")
        _install_stub("gr00t.data")
        _install_stub(
            "gr00t.data.embodiment_tags",
            EmbodimentTag=types.SimpleNamespace(NEW_EMBODIMENT="new_embodiment"),
        )
        _install_stub("gr00t.policy")
        _install_stub("gr00t.policy.gr00t_policy", Gr00tPolicy=object)
        _install_stub("robot_client", RobotClient=object)
        _install_stub(
            "robot_client.camera_mapping",
            resolve_camera_feature_sources=lambda *_args, **_kwargs: {},
        )
        _install_stub("scripts")
        _install_stub("scripts.deployment")
        _install_stub(
            "scripts.deployment.standalone_inference_script",
            replace_dit_with_tensorrt=lambda *_args, **_kwargs: None,
        )
        _install_stub(
            "scripts.deployment.export_onnx_n1d7",
            DiTInputCapture=object,
            export_dit_to_onnx=lambda *_args, **_kwargs: None,
        )

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self._saved_modules)

    def test_runtime_module_exposes_create_engine_factory(self):
        spec = importlib.util.spec_from_file_location(
            "groot_runtime_inference_engine_under_test",
            INFERENCE_ENGINE,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        engine = module.create_engine()

        self.assertIsInstance(engine, module.GR00TInference)

    def test_acceleration_request_resolves_model_local_engine_path(self):
        spec = importlib.util.spec_from_file_location(
            "groot_runtime_inference_engine_under_test",
            INFERENCE_ENGINE,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        engine = module.create_engine()

        mode, engine_path, strict = engine._resolve_acceleration_request(
            types.SimpleNamespace(
                acceleration_mode="tensorrt",
                acceleration_engine_path="custom.trt",
            ),
            "/models/policy",
        )

        self.assertEqual(mode, "tensorrt_dit")
        self.assertEqual(engine_path, "/models/policy/custom.trt")
        self.assertTrue(strict)

    def test_synthetic_observation_uses_model_schema(self):
        spec = importlib.util.spec_from_file_location(
            "groot_runtime_inference_engine_under_test",
            INFERENCE_ENGINE,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        def modality(keys, deltas):
            return types.SimpleNamespace(
                modality_keys=keys,
                delta_indices=deltas,
            )

        state_action_processor = types.SimpleNamespace(
            norm_params={
                "new_embodiment": {
                    "state": {
                        "arm": {
                            "dim": np.array(2),
                            "mean": np.array([0.25, -0.5], dtype=np.float32),
                        }
                    }
                }
            }
        )
        processor = types.SimpleNamespace(
            image_target_size=[12, 16],
            processor=types.SimpleNamespace(
                image_processor=types.SimpleNamespace(
                    image_mean=[0.5, 0.5, 0.5],
                )
            ),
            state_action_processor=state_action_processor,
        )
        policy = types.SimpleNamespace(
            embodiment_tag=types.SimpleNamespace(value="new_embodiment"),
            processor=processor,
            modality_configs={
                "video": modality(["cam"], [0, 1]),
                "state": modality(["arm"], [0]),
                "action": modality(["arm"], [0, 1, 2]),
                "language": modality(["task"], [0]),
            },
        )

        engine = module.create_engine()
        engine.policy = policy
        engine.init_policy_info()

        observation = engine.build_synthetic_observation("pick")

        self.assertEqual(observation["video"]["cam"].shape, (1, 2, 12, 16, 3))
        self.assertEqual(observation["video"]["cam"].dtype, np.uint8)
        self.assertEqual(observation["state"]["arm"].shape, (1, 1, 2))
        np.testing.assert_allclose(
            observation["state"]["arm"][0, 0],
            np.array([0.25, -0.5], dtype=np.float32),
        )
        self.assertEqual(observation["language"]["task"], [["pick"]])


if __name__ == "__main__":
    unittest.main()
