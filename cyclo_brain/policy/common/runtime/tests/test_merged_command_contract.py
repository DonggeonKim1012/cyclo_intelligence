"""Keep local cycle/model commands distinct from upstream BT supervision."""
import ast
from pathlib import Path
import re
from main_runtime import service_handler as handler

ROOT = Path(__file__).resolve().parents[5]


def test_policy_command_numbers_do_not_alias_local_operations():
    assert (handler.CMD_RESET_CYCLE, handler.CMD_SWITCH_POLICY,
            handler.CMD_PRELOAD_POLICY, handler.CMD_CLEAR_PRELOAD,
            handler.CMD_SWITCH_PRELOADED) == (7, 8, 9, 10, 11)
    assert (handler.CMD_CAPABILITIES, handler.CMD_FAULT_STOP) == (12, 13)
    source = ROOT / 'orchestrator/orchestrator/bt/inference_supervisor.py'
    assignment = next(n for n in ast.parse(source.read_text()).body
                      if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple))
    values = dict(zip([n.id for n in assignment.targets[0].elts], ast.literal_eval(assignment.value)))
    assert values['CAPABILITIES'] == handler.CMD_CAPABILITIES
    assert values['FAULT_STOP'] == handler.CMD_FAULT_STOP


def test_load_only_does_not_replace_prepare_next_cycle():
    schema = (ROOT / 'interfaces/srv/SendCommand.srv').read_text()
    constants = {name: int(value) for name, value in re.findall(r'^uint8\s+(\w+)\s*=\s*(\d+)', schema, re.M)}
    assert constants['PREPARE_NEXT_CYCLE'] == 25
    assert constants['LOAD_INFERENCE'] == 30
    assert len(constants.values()) == len(set(constants.values()))
