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


def get_joystick_recording_action(trigger: str, control_profile: str = ''):
    """Keep legacy clicks unless the LG2 mini + SH5 profile is advertised."""
    if control_profile == 'lg2_mini_sh5_recording':
        mapping = _SH5_RECORDING_ACTION_BY_TRIGGER
    elif not control_profile:
        mapping = _DEFAULT_RECORDING_ACTION_BY_TRIGGER
    else:
        return None  # Unknown or stale opt-in profiles must not become legacy clicks.
    return mapping.get(str(trigger or '').strip())
