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
from unittest.mock import Mock
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
    def _set_dimensions(self, engine, widths, tactile=False):
        state = {**widths, **({"tactile_left": 45, "tactile_right": 45} if tactile else {})}
        engine.policy.processor.state_action_processor = types.SimpleNamespace(
            norm_params={"new_embodiment": {
                "state": {key: {"dim": value} for key, value in state.items()},
                "action": {key: {"dim": value} for key, value in widths.items()},
            }}
        )

    def _module(self):
        spec = importlib.util.spec_from_file_location("groot_sh5_test", INFERENCE_ENGINE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_cycle_reset_retains_weights_and_reconnects_observations(self):
        module = self._module()
        engine = module.GR00TInference()
        engine.policy = types.SimpleNamespace(reset=Mock())
        policy = engine.policy
        old_robot = Mock()
        new_robot = Mock()
        new_robot.wait_for_ready.return_value = True
        engine.robot = old_robot
        engine._loaded_robot_type = "ffw_sh5_rev1"
        engine._loaded_acceleration_mode = "tensorrt_dit"
        engine._loaded_acceleration_engine_path = "/model/dit.engine"
        engine.policy_info["action"] = list(engine.SH5_JOINT_KEYS)
        engine.robot_info["action_keys"] = engine.SH5_JOINT_KEYS
        def reconnect(robot_type):
            self.assertEqual(robot_type, "ffw_sh5_rev1")
            self.assertIsNone(engine.robot)
            old_robot.close.assert_called_once()
            policy.reset.assert_called_once()
            engine.robot = new_robot
        engine.init_robot_info = reconnect
        result = engine.reset_cycle()
        self.assertTrue(result["success"], result)
        self.assertIs(engine.policy, policy)
        self.assertEqual(engine._loaded_acceleration_mode, "tensorrt_dit")
        self.assertEqual(engine._loaded_acceleration_engine_path, "/model/dit.engine")
        self.assertEqual(result["action_keys"], list(engine.SH5_JOINT_KEYS.values()))
        new_robot.wait_for_ready.assert_called_once_with(timeout=10.0)

    def test_cycle_reset_failure_blocks_inference(self):
        module = self._module()
        engine = module.GR00TInference()
        self.assertFalse(engine.reset_cycle()["success"])
        engine.policy = types.SimpleNamespace(reset=Mock())
        engine.robot = Mock()
        engine._loaded_robot_type = "ffw_sh5_rev1"
        new_robot = Mock()
        new_robot.wait_for_ready.return_value = False
        engine.init_robot_info = lambda robot_type: setattr(engine, "robot", new_robot)
        result = engine.reset_cycle()
        self.assertFalse(result["success"])
        self.assertIn("did not become ready", result["message"])
        self.assertFalse(engine.is_ready)
        new_robot.close.assert_called_once()
        self.assertIsNone(engine._loaded_robot_type)

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
        self._set_dimensions(engine, dict(zip(engine.SH5_JOINT_KEYS, (7, 7, 20, 20))), tactile=True)
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
        self._set_dimensions(engine, {"arm_left": 8})
        engine.policy_info = {"video": [], "state": ["arm_left"], "action": ["arm_left"], "language": []}
        engine.init_robot_info("ffw_sg2_rev1")
        self.assertEqual(captured, {})
        self.assertEqual(engine.command_action_keys(), ["arm_left"])

    def test_profile_rejects_wrong_robot_and_wrong_dimensions(self):
        module = self._module()
        for tactile in (False, True):
            engine = module.GR00TInference()
            engine.policy = types.SimpleNamespace(processor=types.SimpleNamespace(use_tactile=tactile))
            widths = dict(zip(engine.SH5_JOINT_KEYS, (7, 7, 20, 20)))
            self._set_dimensions(engine, widths, tactile)
            engine.policy_info["action"] = list(widths)
            engine.policy_info["state"] = list(widths) + (["tactile_left", "tactile_right"] if tactile else [])
            self.assertEqual(engine.validate_robot_profile("ffw_sh5_rev1"), "sh5_tactile" if tactile else "sh5")
            with self.assertRaises(ValueError):
                engine.validate_robot_profile("ffw_sg2_rev1")
            params = engine.policy.processor.state_action_processor.norm_params["new_embodiment"]
            params["action"]["left_hand"]["dim"] = 19
            with self.assertRaisesRegex(ValueError, "expected 20"):
                engine.validate_robot_profile("ffw_sh5_rev1")

    def test_sg2_profile_accepts_22_dimensions_and_rejects_sh5(self):
        module = self._module()
        engine = module.GR00TInference()
        engine.policy = types.SimpleNamespace(processor=types.SimpleNamespace(use_tactile=False))
        widths = {"arm_left": 8, "arm_right": 8, "head": 2, "lift": 1, "odometry": 3}
        self._set_dimensions(engine, widths)
        engine.policy_info["action"] = list(widths)
        engine.policy_info["state"] = list(widths)
        self.assertEqual(engine.validate_robot_profile("ffw_sg2_rev1"), "sg2")
        with self.assertRaises(ValueError):
            engine.validate_robot_profile("ffw_sh5_rev1")

    def test_tactile_checkpoint_allows_dit_acceleration(self):
        module = self._module()
        captured = {}
        module.Gr00tPolicy = lambda **kwargs: captured.update(kwargs) or object()
        engine = module.GR00TInference()
        engine._sync_hf_token_for_gated_backbones = lambda: None
        engine.init_policy_info = lambda: None
        engine.init_robot_info = lambda robot: setattr(engine, "robot", types.SimpleNamespace(wait_for_ready=lambda **kw: True))
        calls = []
        engine._enable_dit_tensorrt = lambda **kw: calls.append(kw) or True
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "config.json").write_text('{"use_tactile": true}')
            result = engine.load_policy(types.SimpleNamespace(
                model_path=directory, robot_type="ffw_sh5_rev1", acceleration_mode="tensorrt_dit"))
        self.assertTrue(result["success"], result)
        self.assertTrue(captured["use_tactile"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(engine._loaded_acceleration_mode, "tensorrt_dit")

    def test_trt_preparation_uses_checkpoint_tactile_setting_and_selected_robot(self):
        from unittest.mock import Mock

        runtime = self._module()
        _install_stub("runtime")
        _install_stub("runtime.inference_engine", GR00TInference=runtime.GR00TInference,
                      build_trt_engine=Mock())
        spec = importlib.util.spec_from_file_location(
            "groot_trt_prepare_test", INFERENCE_ENGINE.with_name("prepare_trt_engine.py"))
        prep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prep)
        for tactile, robot in ((False, "ffw_sg2_rev1"), (True, "ffw_sh5_rev1")):
            with tempfile.TemporaryDirectory() as directory:
                (Path(directory) / "config.json").write_text(json.dumps({"use_tactile": tactile}))
                args = types.SimpleNamespace(model_path=directory, engine_path="", force=False,
                                             robot_type=robot, task_instruction="pick", workspace_mb=4096)
                prep._parse_args = lambda: args
                inference = Mock()
                inference.checkpoint_policy_kwargs.side_effect = runtime.GR00TInference.checkpoint_policy_kwargs
                inference.build_synthetic_observation.return_value = {"state": {}}
                prep.GR00TInference = lambda: inference
                prep.Gr00tPolicy = Mock()
                def build(policy, observation, path, **kwargs):
                    Path(path).write_bytes(b"test-engine")
                prep.build_trt_engine = build
                self.assertEqual(prep.main(), 0)
                inference.validate_robot_profile.assert_called_once_with(robot)
                self.assertEqual(prep.Gr00tPolicy.call_args.kwargs.get("use_tactile", False), tactile)

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
