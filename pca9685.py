"""PCA9685 16-channel PWM/Servo driver for the AlphaBot2 pan/tilt servos.

This is a modernised Python 3 version of the original WaveShare PCA9685.py.
"""
from __future__ import annotations

import time
import math

from hardware import SMBus


class PCA9685:
    """Drive a PCA9685 PWM controller over I2C."""

    __SUBADR1 = 0x02
    __SUBADR2 = 0x03
    __SUBADR3 = 0x04
    __MODE1 = 0x00
    __PRESCALE = 0xFE
    __LED0_ON_L = 0x06
    __LED0_ON_H = 0x07
    __LED0_OFF_L = 0x08
    __LED0_OFF_H = 0x09
    __ALLLED_ON_L = 0xFA
    __ALLLED_ON_H = 0xFB
    __ALLLED_OFF_L = 0xFC
    __ALLLED_OFF_H = 0xFD

    def __init__(self, address: int = 0x40, bus: int = 1, debug: bool = False):
        self.bus = SMBus(bus)
        self.address = address
        self.debug = debug
        self.write(self.__MODE1, 0x00)

    def write(self, reg: int, value: int) -> None:
        self.bus.write_byte_data(self.address, reg, value)
        if self.debug:
            print(f"I2C: Write 0x{value:02X} to register 0x{reg:02X}")

    def read(self, reg: int) -> int:
        value = self.bus.read_byte_data(self.address, reg)
        if self.debug:
            print(
                f"I2C: Device 0x{self.address:02X} returned 0x{value & 0xFF:02X} "
                f"from reg 0x{reg:02X}"
            )
        return value

    def set_pwm_freq(self, freq: int) -> None:
        """Set the PWM frequency in Hz."""
        prescaleval = 25000000.0  # 25MHz
        prescaleval /= 4096.0     # 12-bit
        prescaleval /= float(freq)
        prescaleval -= 1.0
        prescale = math.floor(prescaleval + 0.5)

        oldmode = self.read(self.__MODE1)
        newmode = (oldmode & 0x7F) | 0x10  # sleep
        self.write(self.__MODE1, newmode)
        self.write(self.__PRESCALE, int(prescale))
        self.write(self.__MODE1, oldmode)
        time.sleep(0.005)
        self.write(self.__MODE1, oldmode | 0x80)

    def set_pwm(self, channel: int, on: int, off: int) -> None:
        """Set a single PWM channel."""
        self.write(self.__LED0_ON_L + 4 * channel, on & 0xFF)
        self.write(self.__LED0_ON_H + 4 * channel, on >> 8)
        self.write(self.__LED0_OFF_L + 4 * channel, off & 0xFF)
        self.write(self.__LED0_OFF_H + 4 * channel, off >> 8)

    def set_servo_pulse(self, channel: int, pulse_us: int) -> None:
        """Set a servo pulse width in microseconds (50 Hz PWM assumed)."""
        pulse = int(pulse_us * 4096 / 20000)
        self.set_pwm(channel, 0, pulse)


class PanTilt:
    """Convenience wrapper for two servos on channels 0 (pan) and 1 (tilt)."""

    MIN_PULSE = 500
    MAX_PULSE = 2500
    CENTER_PULSE = 1500

    def __init__(self, pca: PCA9685 | None = None, pan_channel: int = 0,
                 tilt_channel: int = 1):
        self.pca = pca or PCA9685(0x40)
        self.pca.set_pwm_freq(50)
        self.pan_channel = pan_channel
        self.tilt_channel = tilt_channel

        self.pan = self.CENTER_PULSE
        self.tilt = self.CENTER_PULSE
        self.pan_step = 0
        self.tilt_step = 0

        self.pca.set_servo_pulse(self.pan_channel, self.pan)
        self.pca.set_servo_pulse(self.tilt_channel, self.tilt)

    def center(self):
        self.pan = self.CENTER_PULSE
        self.tilt = self.CENTER_PULSE
        self.pan_step = 0
        self.tilt_step = 0
        self._apply()

    def _apply(self):
        self.pan = max(self.MIN_PULSE, min(self.MAX_PULSE, int(self.pan)))
        self.tilt = max(self.MIN_PULSE, min(self.MAX_PULSE, int(self.tilt)))
        self.pca.set_servo_pulse(self.pan_channel, self.pan)
        self.pca.set_servo_pulse(self.tilt_channel, self.tilt)

    def set_pan(self, pulse: int):
        self.pan = pulse
        self.pan_step = 0
        self._apply()

    def set_tilt(self, pulse: int):
        self.tilt = pulse
        self.tilt_step = 0
        self._apply()

    def update(self):
        """Call periodically to apply smooth step motion."""
        if self.pan_step:
            self.pan += self.pan_step
            if self.pan >= self.MAX_PULSE:
                self.pan = self.MAX_PULSE
            if self.pan <= self.MIN_PULSE:
                self.pan = self.MIN_PULSE
            self.pca.set_servo_pulse(self.pan_channel, int(self.pan))

        if self.tilt_step:
            self.tilt += self.tilt_step
            if self.tilt >= self.MAX_PULSE:
                self.tilt = self.MAX_PULSE
            if self.tilt <= self.MIN_PULSE:
                self.tilt = self.MIN_PULSE
            self.pca.set_servo_pulse(self.tilt_channel, int(self.tilt))

    def move(self, direction: str):
        """Start continuous movement in one of up/down/left/right."""
        if direction == "up":
            self.tilt_step = -5
        elif direction == "down":
            self.tilt_step = 5
        elif direction == "left":
            self.pan_step = 5
        elif direction == "right":
            self.pan_step = -5
        elif direction == "stop":
            self.pan_step = 0
            self.tilt_step = 0
