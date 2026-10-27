"""Move the base by a measured distance in a Mapping teleop key direction."""

import math
import rclpy
import threading
import time

from action_msgs.msg import GoalStatusArray
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import DurabilityPolicy, QoSProfile

from orchestrator.bt.actions.base_action import BaseAction
from orchestrator.bt.bt_core import NodeStatus


class BaseMove(BaseAction):
    """W/S forward/back, Q/E left/right, A/D counterclockwise/clockwise."""

    def __init__(self, node, direction: str = 'W', distance_m: float = 0.2,
                 angle_deg: float = 30.0, speed_mps: float = 0.15,
                 angular_speed_rps: float = 0.35, timeout_s: float = 20.0,
                 odom_topic: str = '/odom', cmd_vel_topic: str = '/cmd_vel'):
        super().__init__(node, name='BaseMove')
        self.direction = str(direction).upper().strip()
        self.distance_m = float(distance_m)
        self.angle_deg = float(angle_deg)
        self.speed_mps = float(speed_mps)
        self.angular_speed_rps = float(angular_speed_rps)
        self.timeout_s = float(timeout_s)
        if self.direction not in 'WSQEAD' or len(self.direction) != 1:
            raise ValueError('BaseMove direction must be W, S, Q, E, A, or D')
        for value, minimum, maximum, label in (
            (self.distance_m, .01, 2., 'distance_m'),
            (self.angle_deg, 1., 180., 'angle_deg'),
            (self.speed_mps, .03, .4, 'speed_mps'),
            (self.angular_speed_rps, .05, .8, 'angular_speed_rps'),
            (self.timeout_s, 2., 120., 'timeout_s'),
        ):
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f'BaseMove {label} must be in [{minimum}, {maximum}]')
        if not str(odom_topic).strip() or not str(cmd_vel_topic).strip():
            raise ValueError('BaseMove requires odom_topic and cmd_vel_topic')
        self._lock = threading.RLock()
        self._group = ReentrantCallbackGroup()
        self._odom = None
        self._odom_at = 0.
        self._nav_active = False
        self._origin = None
        self._previous = None
        self._frame_id = None
        self._started = None
        self._paused_at = None
        self._settled_samples = 0
        self._last_settled_stamp = None
        self._finished = None
        self._pub = node.create_publisher(Twist, cmd_vel_topic, 10)
        self._odom_topic = odom_topic
        self._transport_node = None
        self._start_transport()

    def _start_transport(self):
        # Receive feedback independently of the behavior tree tick executor.
        self._transport_node = rclpy.create_node(
            f'base_move_io_{id(self):x}', context=self.node.context,
            use_global_arguments=False)
        self._transport_executor = SingleThreadedExecutor(context=self.node.context)
        self._odom_sub = self._transport_node.create_subscription(
            Odometry, self._odom_topic, self._on_odom, QoSProfile(depth=10),
            callback_group=self._group)
        self._nav_sub = self._transport_node.create_subscription(
            GoalStatusArray, '/navigate_to_pose/_action/status', self._on_nav,
            QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL),
            callback_group=self._group)
        self._transport_executor.add_node(self._transport_node)
        self._transport_thread = threading.Thread(
            target=self._transport_executor.spin, daemon=True)
        self._transport_thread.start()

    def _on_odom(self, msg):
        with self._lock:
            self._odom, self._odom_at = msg, time.monotonic()

    def _on_nav(self, msg):
        with self._lock:
            self._nav_active = any(status.status in (1, 2, 3)
                                   for status in msg.status_list)

    @staticmethod
    def _pose(msg):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y),
                         1 - 2 * (q.y * q.y + q.z * q.z))
        if not all(math.isfinite(value) for value in (p.x, p.y, yaw)):
            raise ValueError('BaseMove received invalid odometry pose')
        return p.x, p.y, yaw

    def _publish(self, x=0., y=0., yaw=0.):
        msg = Twist()
        msg.linear.x, msg.linear.y, msg.angular.z = x, y, yaw
        self._pub.publish(msg)

    def _fail(self, reason):
        self._publish()
        self._finished = NodeStatus.FAILURE
        self.log_error(reason)
        return self._finished

    def tick(self):
        if self._transport_node is None:
            self._start_transport()
        with self._lock:
            if self._finished is not None:
                return self._finished
            if self._paused_at is not None:
                return NodeStatus.RUNNING
            now = time.monotonic()
            if self._started is None:
                self._started = now
            if self._nav_active:
                return self._fail('Navigation goal active during BaseMove')
            if now - self._started > self.timeout_s:
                return self._fail('BaseMove timed out before reaching its target')
            if self._odom is None or now - self._odom_at > .5:
                self._publish()
                if now - self._started > 2.:
                    detail = ('no odometry received' if self._odom is None else
                              f'last receipt {now - self._odom_at:.2f}s ago')
                    return self._fail(f'BaseMove odometry unavailable or stale ({detail})')
                return NodeStatus.RUNNING

            try:
                current = self._pose(self._odom)
            except ValueError as exc:
                return self._fail(str(exc))
            if self._origin is None:
                self._origin = current
                self._frame_id = self._odom.header.frame_id
            if self._odom.header.frame_id != self._frame_id:
                return self._fail('BaseMove odometry frame changed')
            if self._previous is not None:
                jump = math.hypot(current[0] - self._previous[0],
                                  current[1] - self._previous[1])
                if jump > .1:
                    return self._fail(f'BaseMove odometry jumped {jump:.3f} m')
            self._previous = current
            x0, y0, yaw0 = self._origin
            dx, dy = current[0] - x0, current[1] - y0
            forward = dx * math.cos(yaw0) + dy * math.sin(yaw0)
            left = -dx * math.sin(yaw0) + dy * math.cos(yaw0)
            heading = math.atan2(math.sin(current[2] - yaw0),
                                 math.cos(current[2] - yaw0))
            if self.direction in 'WSQE':
                axis = forward if self.direction in 'WS' else left
                off_axis = left if self.direction in 'WS' else forward
                sign = 1 if self.direction in 'WQ' else -1
                if abs(off_axis) > .1 or abs(heading) > .25:
                    return self._fail('BaseMove deviated from the requested straight path')
                remaining = self.distance_m - sign * axis
                target_reached = remaining <= .01
                speed_limit = self.speed_mps if self.direction in 'WS' else self.speed_mps / 2
                velocity = min(speed_limit, max(.03, remaining * 1.5))
                command = (sign * velocity, 0., 0.) if self.direction in 'WS' else (0., sign * velocity, 0.)
                measured_speed = math.hypot(self._odom.twist.twist.linear.x,
                                            self._odom.twist.twist.linear.y)
                stationary = measured_speed < .02
            else:
                sign = 1 if self.direction == 'A' else -1
                remaining = math.radians(self.angle_deg) - sign * heading
                target_reached = remaining <= math.radians(2.)
                velocity = min(self.angular_speed_rps, max(.05, remaining * 1.5))
                command = (0., 0., sign * velocity)
                stationary = abs(self._odom.twist.twist.angular.z) < .03
            if target_reached:
                self._publish()
                stamp = self._odom_at
                if stationary and stamp != self._last_settled_stamp:
                    self._settled_samples += 1
                    self._last_settled_stamp = stamp
                elif not stationary:
                    self._settled_samples = 0
                if self._settled_samples >= 3:
                    self._finished = NodeStatus.SUCCESS
                    return self._finished
            else:
                self._settled_samples = 0
                self._publish(*command)
            return NodeStatus.RUNNING

    def pause(self):
        with self._lock:
            if self._finished is None and self._started is not None:
                self._paused_at = time.monotonic()
                self._publish()

    def resume(self):
        with self._lock:
            if self._paused_at is not None:
                self._started += time.monotonic() - self._paused_at
                self._paused_at = None

    def reset(self):
        with self._lock:
            self._publish()
        if self._transport_node is not None:
            self._transport_executor.shutdown(timeout_sec=3.)
            self._transport_thread.join(timeout=3.)
            if self._transport_thread.is_alive():
                raise RuntimeError('BaseMove odometry executor did not stop')
            self._transport_node.destroy_node()
            self._transport_node = None
        with self._lock:
            self._origin = self._previous = self._frame_id = None
            self._started = self._paused_at = None
            self._odom = None
            self._odom_at = 0.
            self._settled_samples = 0
            self._last_settled_stamp = None
            self._finished = None
            super().reset()
