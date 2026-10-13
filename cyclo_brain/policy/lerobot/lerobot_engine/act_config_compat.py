#!/usr/bin/env python3
# Copyright 2026 ROBOTIS CO., LTD.
# Licensed under the Apache License, Version 2.0
"""Load ordinary ACT checkpoints containing unused training metadata."""
from __future__ import annotations
import copy
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
import torch
from lerobot.configs import PreTrainedConfig
from lerobot.policies.act.modeling_act import ACTPolicy
TACTILE_HIDDEN_DIM_FIELD = "tactile_expert_hidden_dim"
TACTILE_TRAINING_ONLY_FIELDS = frozenset(
    {
        "tactile_optimizer_lr",
        "tactile_pos_embed_init_std",
        "tactile_noise_std",
        "tactile_dropout_prob",
        "supervise_terminal_hold",
        "scheduler_warmup_steps",
        "scheduler_decay_steps",
        "scheduler_decay_lr",
        "diagnostic_log_freq",
    }
)


def _load_act_config_compat(
    config_payload: Mapping[str, Any],
    device: torch.device,
) -> tuple[PreTrainedConfig, int | None]:
    """Parse ACT config while tolerating the internal tactile metadata field."""
    payload = copy.deepcopy(dict(config_payload))
    raw_hidden_dim = payload.pop(TACTILE_HIDDEN_DIM_FIELD, None)
    hidden_dim = int(raw_hidden_dim) if raw_hidden_dim is not None else None
    for field in TACTILE_TRAINING_ONLY_FIELDS:
        payload.pop(field, None)
    # Ordinary ACT checkpoints may contain unused training metadata.
    payload["type"] = "act"

    with tempfile.TemporaryDirectory(prefix="cyclo-act-config-") as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text(json.dumps(payload))
        config = PreTrainedConfig.from_pretrained(tmp)

    config.device = str(device)

    # Every backbone tensor is restored from model.safetensors. Avoid an
    # unnecessary ImageNet download during offline robot inference.
    config.pretrained_backbone_weights = None
    return config, hidden_dim


def load_standard_act_with_legacy_tactile_metadata(
    model_path: str | Path,
    config_payload: Mapping[str, Any],
    device: torch.device,
) -> ACTPolicy:
    """Load ordinary ACT saved with an unused tactile config field.

    Some training runs serialized ``tactile_expert_hidden_dim`` even when the
    dataset exposed no tactile input.  The checkpoint itself is ordinary ACT;
    remove only that unsupported metadata field before strict weight loading.
    """
    config, _ = _load_act_config_compat(config_payload, device)
    return ACTPolicy.from_pretrained(
        model_path,
        config=config,
        strict=True,
    )
