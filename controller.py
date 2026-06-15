"""High-level robot controller and autonomous behaviours."""
from __future__ import annotations

import time
import threading
from enum import Enum
from typing import Callable

from hardware import start_background_loop, IS_RPI
from robot import AlphaBot2
from pca9685 import PanTilt
from sensors import UltrasonicRanger, InfraredObstacle, TRSensor
from leds import RGBLeds
from buzzer import Buzzer
from ir_remote import IRRemote


class DemoMode(Enum):
    IDLE = "idle"
    LINE_FOLLOW = "line_follow"
    ULTRASONIC_AVOID = "ultrasonic_avoid"
    INFRARED_AVOID = "infrared_avoid"


class RobotController:
    """Single entry point that owns every AlphaBot2 subsystem."""

    def __init__(self):
        self.robot = AlphaBot2()
        self.pan_tilt = PanTilt()
        self.ultrasonic = UltrasonicRanger()
        self.ir_obstacle = InfraredObstacle()
        self.tr_sensor = TRSensor()
        self.leds = RGBLeds()
        self.buzzer = Buzzer()
        self.ir_remote = IRRemote()

        self.demo_mode = DemoMode.IDLE
        self._demo_lock = threading.Lock()
        self._stop_requested = False

        # Latest telemetry shared with the webapp.
        self.telemetry = {
            "distance": 0.0,
            "ir_obstacle": {"left": False, "right": False},
            "tr_sensor": {"position": 0, "values": [0] * 5},
            "ir_remote": {"code": None, "name": None},
            "demo": self.demo_mode.value,
            "motor_speed": 50,
        }
        self._telemetry_lock = threading.Lock()

        self._start_background_tasks()

    def _start_background_tasks(self):
        # 50 Hz servo updater
        start_background_loop(0.02, self.pan_tilt.update, daemon=True)
        # RGB animator
        self.leds.start_loop(daemon=True)
        # IR decoder
        self.ir_remote.start(daemon=True)
        # Sensor telemetry reader
        start_background_loop(0.1, self._read_telemetry, daemon=True)
        # Autonomous demo runner
        start_background_loop(0.05, self._run_demo_step, daemon=True)

    def _read_telemetry(self):
        distance = self.ultrasonic.distance()
        ir = self.ir_obstacle.read()
        position, values = self.tr_sensor.read_line()
        remote = self.ir_remote.recent_key(timeout=0.5)
        with self._telemetry_lock:
            self.telemetry.update({
                "distance": distance,
                "ir_obstacle": ir,
                "tr_sensor": {"position": position, "values": values},
                "ir_remote": remote,
                "demo": self.demo_mode.value,
                "motor_speed": self.robot.PA,
            })

    def get_telemetry(self) -> dict:
        with self._telemetry_lock:
            return dict(self.telemetry)

    # ------------------------------------------------------------------
    # Motion commands
    # ------------------------------------------------------------------

    def move(self, direction: str):
        """Execute a single motion command (forward, backward, left, right, stop)."""
        with self._demo_lock:
            if self.demo_mode != DemoMode.IDLE:
                self.demo_mode = DemoMode.IDLE
        method = getattr(self.robot, direction, None)
        if callable(method):
            method()

    def set_speed(self, speed: int):
        self.robot.set_speed(speed)

    def set_motor(self, left: int, right: int):
        self.robot.set_motor(left, right)

    def pan_tilt_move(self, direction: str):
        self.pan_tilt.move(direction)

    def pan_tilt_center(self):
        self.pan_tilt.center()

    # ------------------------------------------------------------------
    # Demo modes
    # ------------------------------------------------------------------

    def set_demo(self, mode: str):
        with self._demo_lock:
            self.demo_mode = DemoMode(mode)
            if self.demo_mode == DemoMode.IDLE:
                self.robot.stop()

    def _run_demo_step(self):
        with self._demo_lock:
            mode = self.demo_mode

        if mode == DemoMode.IDLE:
            return

        if mode == DemoMode.ULTRASONIC_AVOID:
            self._ultrasonic_avoid_step()
        elif mode == DemoMode.INFRARED_AVOID:
            self._infrared_avoid_step()
        elif mode == DemoMode.LINE_FOLLOW:
            self._line_follow_step()

    # ------------------------------------------------------------------
    # Individual demo implementations (ported from original examples)
    # ------------------------------------------------------------------

    def _ultrasonic_avoid_step(self):
        dist = self.ultrasonic.distance()
        if dist < 0 or dist > 400:
            dist = 400
        if dist <= 20:
            self.robot.right()
        else:
            self.robot.forward()

    def _infrared_avoid_step(self):
        status = self.ir_obstacle.read()
        if status["left"] or status["right"]:
            self.robot.left()
            time.sleep(0.05)
            self.robot.stop()
        else:
            self.robot.forward()

    def _line_follow_step(self):
        maximum = 35
        if not hasattr(self, "_line_integral"):
            self._line_integral = 0
            self._line_last_proportional = 0

        position, sensors = self.tr_sensor.read_line()

        # All sensors see black/dark -> stop (end of line)
        if all(v > 900 for v in sensors):
            self.robot.set_pwma(0)
            self.robot.set_pwmb(0)
            return

        proportional = position - 2000
        derivative = proportional - self._line_last_proportional
        self._line_integral += proportional
        self._line_last_proportional = proportional

        power_difference = (proportional / 30) + (self._line_integral / 10000) + (derivative * 2)
        power_difference = max(-maximum, min(maximum, power_difference))

        if power_difference < 0:
            self.robot.set_pwma(maximum + power_difference)
            self.robot.set_pwmb(maximum)
        else:
            self.robot.set_pwma(maximum)
            self.robot.set_pwmb(maximum - power_difference)

    # ------------------------------------------------------------------
    # Calibration helper
    # ------------------------------------------------------------------

    def calibrate_line_sensor(self, spin_callback: Callable | None = None):
        """Spin the robot and calibrate the line sensor."""
        for i in range(100):
            if i < 25 or i >= 75:
                self.robot.right()
                self.robot.set_pwma(30)
                self.robot.set_pwmb(30)
            else:
                self.robot.left()
                self.robot.set_pwma(30)
                self.robot.set_pwmb(30)
            self.tr_sensor.calibrate()
            if spin_callback:
                spin_callback(i)
        self.robot.stop()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self):
        self._stop_requested = True
        self.set_demo("idle")
        self.robot.stop()
        self.leds.stop()
        self.ir_remote.stop()
