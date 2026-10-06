#!/usr/bin/env python3
"""Smoke checks for the GR00T N1.7 ARM64 test container."""

import argparse
import importlib
import os
from pathlib import Path


def print_module(name: str) -> None:
    module = importlib.import_module(name)
    version = getattr(module, "__version__", "unknown")
    path = getattr(module, "__file__", "built-in")
    print(f"{name}: version={version} path={path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--synthetic-inference", action="store_true",
        help="Run one non-actuating prediction using checkpoint-shaped synthetic inputs.",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Optional local or HuggingFace model path to load with Gr00tPolicy.",
    )
    parser.add_argument(
        "--embodiment-tag",
        default="new_embodiment",
        help="Embodiment tag to use when --model-path is provided.",
    )
    parser.add_argument(
        "--robot-type", choices=("ffw_sg2_rev1", "ffw_sh5_rev1"),
        help="Validate the checkpoint against the robot selected in Cyclo, without subscriptions.",
    )
    args = parser.parse_args()
    if args.robot_type and not args.model_path:
        parser.error("--robot-type requires --model-path")

    print(f"GROOT_TRT_ENABLED={os.environ.get('GROOT_TRT_ENABLED')}")
    print(f"cwd={Path.cwd()}")

    for name in (
        "torch",
        "torchvision",
        "transformers",
        "flash_attn",
        "triton",
        "torchcodec",
        "cv2",
        "tensorrt",
        "zenoh",
        "gr00t",
    ):
        print_module(name)

    import torch

    print(f"cuda_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"cuda_device={torch.cuda.get_device_name(0)}")

    import scripts.deployment.export_onnx_n1d7 as export_n1d7

    print(f"export_onnx_n1d7={export_n1d7.__file__}")

    from gr00t.data.embodiment_tags import EmbodimentTag
    from gr00t.policy.gr00t_policy import Gr00tPolicy

    if args.model_path:
        from runtime.inference_engine import GR00TInference

        print(f"loading_model={args.model_path}")
        policy = Gr00tPolicy(
            embodiment_tag=EmbodimentTag.resolve(args.embodiment_tag),
            model_path=args.model_path,
            device="cuda" if torch.cuda.is_available() else "cpu",
            **GR00TInference.checkpoint_policy_kwargs(args.model_path),
        )
        print(f"loaded_policy={type(policy).__name__}")
        print(f"modality_keys={list(policy.modality_configs.keys())}")
        engine = GR00TInference()
        engine.policy = policy
        engine.init_policy_info()
        if args.robot_type:
            print(f"robot_profile={engine.validate_robot_profile(args.robot_type)}")
        if args.synthetic_inference:
            import numpy as np

            observation = engine.build_synthetic_observation("Pick and hold two items")
            action, _ = policy.get_action(observation)
            chunk = engine.postprocess_action(action)
            if not chunk.get("success") or not np.isfinite(chunk["action_chunk"]).all():
                raise RuntimeError(f"Invalid synthetic prediction: {chunk}")
            print(f"prediction_shape=({chunk['chunk_size']}, {chunk['action_dim']})")
    elif args.synthetic_inference:
        parser.error("--synthetic-inference requires --model-path")


if __name__ == "__main__":
    main()
