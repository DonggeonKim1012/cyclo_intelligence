#!/usr/bin/env python3
#
# Copyright 2026 ROBOTIS CO., LTD.
#
# Licensed under the Apache License, Version 2.0

"""Inference output-mode helpers shared by UI and BT command dispatch."""

from __future__ import annotations


SIMULATION_MODE = "simulation"
ROBOT_MODE = "robot"

_ROBOT_MODE_VALUES = {
    ROBOT_MODE,
    "robot_mode",
    "publish",
    "publish_to_robot",
}

_ROBOT_MODE_TAGS = {
    "inference_mode:robot",
    "publish_to_robot:true",
}
_SIMULATION_MODE_TAGS = {
    "inference_mode:simulation",
    "publish_to_robot:false",
}


def normalize_inference_mode(value) -> str:
    mode = str(value or "").strip().lower()
    if mode in _ROBOT_MODE_VALUES:
        return ROBOT_MODE
    return SIMULATION_MODE


def publish_to_robot_override_from_task_info(task_info):
    """Return an explicit output-mode override, or ``None`` when absent.

    RESUME callers created before ``TaskInfo.inference_mode`` was added may
    send no mode; their caller can interpret ``None`` as the already-loaded
    mode. A new START instead interprets ``None`` as safe Simulation.
    Backward-compatible mode tags are also accepted. Invalid or conflicting
    explicit values are rejected instead of falling through to a potentially
    unsafe cached Robot mode.
    """
    mode = str(getattr(task_info, "inference_mode", "") or "").strip().lower()
    override = None
    if mode in _ROBOT_MODE_VALUES:
        override = True
    elif mode == SIMULATION_MODE:
        override = False
    elif mode:
        raise ValueError(
            f"Invalid inference_mode {mode!r}; expected 'simulation' or 'robot'"
        )

    tags = getattr(task_info, "tags", []) or []
    for raw_tag in tags:
        tag = str(raw_tag or "").strip().lower()
        if not tag:
            continue
        if tag in _ROBOT_MODE_TAGS:
            tag_override = True
        elif tag in _SIMULATION_MODE_TAGS:
            tag_override = False
        elif tag.startswith("inference_mode:") or tag.startswith(
            "publish_to_robot:"
        ):
            raise ValueError(
                f"Invalid inference mode tag {tag!r}; expected robot/simulation"
            )
        else:
            continue

        if override is not None and override != tag_override:
            raise ValueError(
                "Conflicting inference modes in TaskInfo field and tags"
            )
        override = tag_override

    return override


def inference_mode_from_task_info(task_info) -> str:
    """Return robot/simulation from TaskInfo fields and tags."""
    mode = getattr(task_info, "inference_mode", "")
    if mode:
        return normalize_inference_mode(mode)

    tags = getattr(task_info, "tags", []) or []
    for tag in tags:
        normalized = str(tag or "").strip().lower()
        if normalized in {"inference_mode:robot", "publish_to_robot:true"}:
            return ROBOT_MODE
        if normalized in {"inference_mode:simulation", "publish_to_robot:false"}:
            return SIMULATION_MODE

    return ROBOT_MODE if bool(getattr(task_info, "publish_to_robot", False)) else SIMULATION_MODE


def publish_to_robot_from_task_info(task_info) -> bool:
    """Return true only when a command explicitly asks for robot publish."""
    return inference_mode_from_task_info(task_info) == ROBOT_MODE
