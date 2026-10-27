"""Leader joystick gestures that are allowed to control recording."""

RECORD_TOGGLE_ACTION = 'record_toggle'
RECORD_CANCEL_ACTION = 'record_cancel'

_SH5_RECORDING_ACTION_BY_TRIGGER = {
    'right_long_time': RECORD_TOGGLE_ACTION,
    'left_long_time': RECORD_CANCEL_ACTION,
}
_DEFAULT_RECORDING_ACTION_BY_TRIGGER = {
    'right': RECORD_TOGGLE_ACTION,
    'left': RECORD_CANCEL_ACTION,
}

ARM_TOGGLE_TRIGGERS = frozenset({'right', 'left'})
SH5_RECORDING_PROFILES = frozenset({'lg2_mini_sh5_recording', 'a3_sh5'})


def get_joystick_recording_action(trigger: str, control_profile: str = ''):
    """Use long presses for explicit SH5 leaders; preserve legacy clicks otherwise."""
    if control_profile in SH5_RECORDING_PROFILES:
        mapping = _SH5_RECORDING_ACTION_BY_TRIGGER
    elif not control_profile:
        mapping = _DEFAULT_RECORDING_ACTION_BY_TRIGGER
    else:
        return None  # Unknown or stale opt-in profiles must not become legacy clicks.
    return mapping.get(str(trigger or '').strip())
