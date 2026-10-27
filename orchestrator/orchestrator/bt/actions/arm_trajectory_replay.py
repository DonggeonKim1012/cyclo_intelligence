"""Replay a Mission Canvas recording through the existing SH5 joint channels."""

import base64
import binascii
import json
import math
import time

from rclpy.callback_groups import ReentrantCallbackGroup
from std_srvs.srv import SetBool
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from orchestrator.bt.actions.joint_control import JointControl
from orchestrator.bt.bt_core import NodeStatus


GROUPS = (
    ('arm_left', tuple(f'arm_l_joint{i}' for i in range(1, 8))),
    ('arm_right', tuple(f'arm_r_joint{i}' for i in range(1, 8))),
    ('hand_left', tuple(f'finger_l_joint{i}' for i in range(1, 21))),
    ('hand_right', tuple(f'finger_r_joint{i}' for i in range(1, 21))),
)
JOINTS = tuple(name for _, names in GROUPS for name in names)
GROUP_START = {'arm_left': 0, 'arm_right': 7, 'hand_left': 14, 'hand_right': 34}
ARM_GROUPS = GROUPS[:2]
ARM_JOINTS = JOINTS[:14]


def decode_recording(value):
    try:
        if not isinstance(value, str) or len(value) > 700_000:
            raise ValueError('recording is empty or too large')
        data = json.loads(base64.b64decode(value, validate=True))
        if not isinstance(data, dict):
            raise ValueError('recording must be an object')
        samples = data['samples']
        if data.get('v') != 1 or data.get('robot_type') != 'ffw_sh5_rev1':
            raise ValueError('unsupported robot or recording version')
        if not isinstance(samples, list) or not 2 <= len(samples) <= 600:
            raise ValueError('recording requires 2–600 samples')
        previous = -1.
        for sample in samples:
            if (not isinstance(sample, list) or len(sample) != len(JOINTS) + 1
                    or any(type(number) not in (int, float) or not math.isfinite(number)
                           for number in sample)):
                raise ValueError('recording has an incomplete or invalid joint sample')
            if sample[0] <= previous or sample[0] > 30.:
                raise ValueError('recording timestamps must increase within 30 seconds')
            previous = sample[0]
        if samples[0][0] != 0 or previous < .1:
            raise ValueError('recording must begin at 0 and last at least 0.1 seconds')
        return samples
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError(f'ArmTrajectoryReplay: invalid recording: {exc}') from exc


def decode_pose_sequence(value):
    try:
        if not isinstance(value, str) or len(value) > 100_000:
            raise ValueError('pose sequence is empty or too large')
        data = json.loads(base64.b64decode(value, validate=True))
        if (not isinstance(data, dict) or data.get('v') != 1
                or data.get('robot_type') != 'ffw_sh5_rev1'
                or data.get('joint_names') != list(ARM_JOINTS)):
            raise ValueError('expected ordered SH5 arm joints')
        points = data.get('points')
        if not isinstance(points, list) or not 2 <= len(points) <= 20:
            raise ValueError('pose sequence needs 2–20 points')
        for point in points:
            if (not isinstance(point, list) or len(point) != len(ARM_JOINTS)
                    or any(type(value) not in (int, float) or not math.isfinite(value)
                           for value in point)):
                raise ValueError('pose point needs 14 finite arm positions')
        return points
    except (TypeError, ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError(f'ArmTrajectoryReplay: invalid pose sequence: {exc}') from exc


def compile_pose_sequence(start, targets, max_speed):
    """Continuous, monotone cubic tangents for the arm waypoints."""
    positions = [list(start), *targets]
    times = [0.]
    for previous, current in zip(positions, positions[1:]):
        distance = max(abs(a - b) for a, b in zip(previous, current))
        times.append(times[-1] + max(.7, 2.0 * distance / max_speed))
    if times[-1] > 120.:
        raise ValueError('pose sequence exceeds 120 seconds at the selected speed')
    velocities = [[0.] * len(ARM_JOINTS) for _ in positions]
    for index in range(1, len(positions) - 1):
        before = times[index] - times[index - 1]
        after = times[index + 1] - times[index]
        for joint in range(len(ARM_JOINTS)):
            incoming = (positions[index][joint] - positions[index - 1][joint]) / before
            outgoing = (positions[index + 1][joint] - positions[index][joint]) / after
            if incoming * outgoing <= 0:
                continue  # Stop at a reversal so the cubic cannot overshoot.
            weight_in = 2 * after + before
            weight_out = after + 2 * before
            tangent = ((weight_in + weight_out)
                       / (weight_in / incoming + weight_out / outgoing))
            velocities[index][joint] = math.copysign(min(abs(tangent), max_speed), tangent)
    samples = [[stamp, *point] for stamp, point in zip(times, positions)]
    return samples, velocities


class ArmTrajectoryReplay(JointControl):
    """Record in Design, then replay both arms and both 20-joint hands."""

    @classmethod
    def from_xml_params(cls, context, name, params):
        action = cls(context.node, recording=params.get('recording', ''),
                     pose_sequence=params.get('pose_sequence', ''),
                     pose_speed_rad_s=params.get('pose_speed_rad_s', .25),
                     start_tolerance_rad=params.get('start_tolerance_rad', .15),
                     topic_config=context.topic_config)
        action.name = name
        return action

    def __init__(self, node, recording: str = '', pose_sequence: str = '',
                 pose_speed_rad_s: float = .25, start_tolerance_rad: float = .15,
                 topic_config=None):
        if recording and pose_sequence:
            raise ValueError('ArmTrajectoryReplay: select a recording or a pose sequence')
        self.pose_targets = decode_pose_sequence(pose_sequence) if pose_sequence else None
        self._pose_mode = self.pose_targets is not None
        self.pose_speed_rad_s = float(pose_speed_rad_s)
        if not math.isfinite(self.pose_speed_rad_s) or not .05 <= self.pose_speed_rad_s <= .6:
            raise ValueError('ArmTrajectoryReplay pose_speed_rad_s must be 0.05–0.6')
        self.samples = [] if self._pose_mode else decode_recording(recording)
        self._point_velocities = []
        self.groups = ARM_GROUPS if self._pose_mode else GROUPS
        self.joints = ARM_JOINTS if self._pose_mode else JOINTS
        self.start_tolerance_rad = float(start_tolerance_rad)
        if not math.isfinite(self.start_tolerance_rad) or not .02 <= self.start_tolerance_rad <= .5:
            raise ValueError('ArmTrajectoryReplay start_tolerance_rad must be 0.02–0.5')
        ends = self.pose_targets[-1] if self._pose_mode else self.samples[-1][1:]
        positions = ';'.join(','.join(str(value) for value in ends[GROUP_START[group]:GROUP_START[group] + len(names)])
                             for group, names in self.groups)
        super().__init__(node, groups=','.join(group for group, _ in self.groups),
                         positions=positions, enable_head=False,
                         duration=2. if self._pose_mode else self.samples[-1][0] + .1,
                         topic_config=topic_config)
        self.name = 'ArmTrajectoryReplay'
        if tuple(name for channel in self._channels for name in channel['joint_names']) != self.joints:
            raise ValueError('ArmTrajectoryReplay: robot joint order differs from recording')
        self._timeout_ticks = int((self.duration + 10.) * self._control_rate)
        self._replay_elapsed = 0.
        self._replay_started = None
        self._paused_elapsed = 0.
        self._preflight_started = None
        self._owner_state = 'waiting'
        self._owner_futures = []
        self._terminal = None
        self._pause_clients = []
        self._resume_clients = []
        if not self._pose_mode:
            group = ReentrantCallbackGroup()
            self._pause_clients = [node.create_client(SetBool, f'/leader/hand_control/{side}/pause',
                                                      callback_group=group)
                                   for side in ('left', 'right')]
            self._resume_clients = [node.create_client(SetBool, f'/leader/hand_control/{side}/allow_resume',
                                                       callback_group=group)
                                    for side in ('left', 'right')]

    def _publish_channel(self, channel, positions=None, duration=None):
        if positions is not None:
            return super()._publish_channel(channel, positions=positions, duration=duration)
        start = GROUP_START[channel['group']]
        width = len(channel['joint_names'])
        trajectory = JointTrajectory()
        trajectory.joint_names = list(channel['joint_names'])
        elapsed = self._replay_elapsed
        if elapsed:
            measured = self._name_to_position()
            point = JointTrajectoryPoint()
            point.positions = [measured[name] for name in channel['joint_names']]
            if self._point_velocities:
                point.velocities = [0.] * width
            point.time_from_start.nanosec = 100_000_000
            trajectory.points.append(point)
        for index, sample in enumerate(self.samples):
            if elapsed and sample[0] <= elapsed:
                continue
            point = JointTrajectoryPoint()
            point.positions = sample[1 + start:1 + start + width]
            if self._point_velocities:
                point.velocities = self._point_velocities[index][start:start + width]
            at = max(.1, sample[0] - elapsed + .1)
            point.time_from_start.sec, point.time_from_start.nanosec = divmod(
                round(at * 1_000_000_000), 1_000_000_000)
            trajectory.points.append(point)
        if len(trajectory.points) == 1:
            point = JointTrajectoryPoint()
            point.positions = self.samples[-1][1 + start:1 + start + width]
            if self._point_velocities:
                point.velocities = [0.] * width
            point.time_from_start.nanosec = 200_000_000
            trajectory.points.append(point)
        channel['pub'].publish(trajectory)
        if self._replay_started is None:
            self._replay_started = time.monotonic()

    def _channel_reached(self, channel, name_to_position):
        if self._replay_started is None or self._replay_elapsed + time.monotonic() - self._replay_started < self.duration:
            return False
        return super()._channel_reached(channel, name_to_position)

    def pause(self):
        if self._thread is not None and self._result is None and self._replay_started is not None:
            self._paused_elapsed = min(self.samples[-1][0],
                                       self._replay_elapsed + time.monotonic() - self._replay_started)
        super().pause()

    def resume(self):
        if self._paused.is_set():
            self._replay_elapsed = self._paused_elapsed
            self._replay_started = time.monotonic()
        super().resume()

    def _finish(self, status):
        self._terminal = status
        self._owner_state = 'releasing'
        self._owner_started = time.monotonic()
        self._owner_futures = [client.call_async(SetBool.Request(data=True))
                               for client in self._resume_clients if client.service_is_ready()]

    def tick(self):
        if self._owner_state == 'waiting':
            now = time.monotonic()
            if self._preflight_started is None:
                self._preflight_started = now
            positions = self._name_to_position()
            if any(name not in positions or now - self._joint_received.get(name, 0) > .5 for name in self.joints):
                if now - self._preflight_started <= 2.:
                    return NodeStatus.RUNNING
                self.log_error('ArmTrajectoryReplay: fresh required joint feedback unavailable')
                return NodeStatus.FAILURE
            if not self._pose_mode and any(abs(positions[name] - target) > self.start_tolerance_rad
                                           for name, target in zip(self.joints, self.samples[0][1:])):
                self.log_error('ArmTrajectoryReplay: current pose is too far from recording start')
                return NodeStatus.FAILURE
            if self._pose_mode:
                self._owner_state = 'owned'
                return NodeStatus.RUNNING
            if not all(client.service_is_ready() for client in self._pause_clients + self._resume_clients):
                if now - self._preflight_started <= 2.:
                    return NodeStatus.RUNNING
                self.log_error('ArmTrajectoryReplay: leader hand control ownership unavailable')
                return NodeStatus.FAILURE
            self._owner_futures = [client.call_async(SetBool.Request(data=True)) for client in self._pause_clients]
            self._owner_state = 'pausing'
            self._owner_started = time.monotonic()
            return NodeStatus.RUNNING
        if self._owner_state == 'pausing':
            if not all(future.done() for future in self._owner_futures):
                if time.monotonic() - self._owner_started > 3.:
                    self.log_error('ArmTrajectoryReplay: leader hand control pause timed out')
                    self._finish(NodeStatus.FAILURE)
                return NodeStatus.RUNNING
            if any(future.exception() or not future.result().success for future in self._owner_futures):
                self.log_error('ArmTrajectoryReplay: leader hand control refused pause')
                self._finish(NodeStatus.FAILURE)
            else:
                self._owner_state = 'owned'
            return NodeStatus.RUNNING
        if self._owner_state == 'owned':
            if self._pose_mode and not self.samples:
                now = time.monotonic()
                positions = self._name_to_position()
                if any(name not in positions or not math.isfinite(positions[name])
                       or now - self._joint_received.get(name, 0) > .5
                       for name in self.joints):
                    self.log_error('ArmTrajectoryReplay: fresh arm feedback unavailable before pose sequence')
                    self._terminal = NodeStatus.FAILURE
                    self._owner_state = 'released'
                    return NodeStatus.FAILURE
                try:
                    self.samples, self._point_velocities = compile_pose_sequence(
                        [positions[name] for name in self.joints], self.pose_targets,
                        self.pose_speed_rad_s)
                except ValueError as exc:
                    self.log_error(f'ArmTrajectoryReplay: {exc}')
                    self._terminal = NodeStatus.FAILURE
                    self._owner_state = 'released'
                    return NodeStatus.FAILURE
                self.duration = self.samples[-1][0] + .1
                self._timeout_ticks = int((self.duration + 10.) * self._control_rate)
            status = super().tick()
            if status != NodeStatus.RUNNING:
                if self._pose_mode:
                    self._terminal = status
                    self._owner_state = 'released'
                    return status
                self._finish(status)
            return NodeStatus.RUNNING
        if self._owner_state == 'releasing':
            if not all(future.done() for future in self._owner_futures):
                if time.monotonic() - self._owner_started > 3.:
                    self.log_error('ArmTrajectoryReplay: leader teleop re-entry timed out')
                    self._owner_state = 'released'
                    return NodeStatus.FAILURE
                return NodeStatus.RUNNING
            self._owner_state = 'released'
            if len(self._owner_futures) != 2 or any(
                    future.exception() or not future.result().success
                    for future in self._owner_futures):
                self.log_error('ArmTrajectoryReplay: leader teleop re-entry could not be armed')
                return NodeStatus.FAILURE
            if self._terminal == NodeStatus.SUCCESS:
                label = 'Arm pose sequence' if self._pose_mode else 'Arm and hand trajectory replay'
                self.log_info(f'{label} complete; toggle leader teleop off/on to resume')
            return self._terminal
        return self._terminal or NodeStatus.FAILURE

    def reset(self):
        needs_release = not self._pose_mode and self._owner_state in ('pausing', 'owned', 'releasing')
        try:
            super().reset()
        finally:
            if needs_release:
                for client in self._resume_clients:
                    if client.service_is_ready():
                        client.call_async(SetBool.Request(data=True))
        self._replay_elapsed = 0.
        self._replay_started = None
        self._preflight_started = None
        self._owner_state = 'waiting'
        self._owner_futures = []
        self._terminal = None
        if self._pose_mode:
            self.samples = []
            self._point_velocities = []
