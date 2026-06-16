"""Sensor drivers for the AlphaBot2 Raspberry Pi examples.

Includes:
  * Ultrasonic distance sensor (HC-SR04)
  * Infrared obstacle-avoidance sensors
  * TR sensor array for line following
"""
from __future__ import annotations

import time
import random
from typing import List, Tuple

from hardware import GPIO, IS_RPI


class UltrasonicRanger:
    """HC-SR04 ultrasonic distance sensor."""

    def __init__(self, trig: int = 22, echo: int = 27):
        self.TRIG = trig
        self.ECHO = echo
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.TRIG, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.ECHO, GPIO.IN)
        self._last_distance = 50.0

    def distance(self, timeout: float = 0.04) -> float:
        """Return distance in centimeters."""
        if not IS_RPI:
            # Simulate a slowly varying distance when running off-board.
            self._last_distance += random.uniform(-2, 2)
            self._last_distance = max(5.0, min(400.0, self._last_distance))
            return round(self._last_distance, 2)

        GPIO.output(self.TRIG, GPIO.HIGH)
        time.sleep(0.000015)
        GPIO.output(self.TRIG, GPIO.LOW)

        start = time.time()
        deadline = start + timeout
        while GPIO.input(self.ECHO) == 0:
            start = time.time()
            if start > deadline:
                return -1.0

        end = time.time()
        deadline = end + timeout
        while GPIO.input(self.ECHO) == 1:
            end = time.time()
            if end > deadline:
                return -1.0

        return round((end - start) * 34000 / 2, 2)


class InfraredObstacle:
    """Two IR obstacle sensors (active-low)."""

    def __init__(self, left_pin: int = 19, right_pin: int = 16):
        self.DL = left_pin
        self.DR = right_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.DL, GPIO.IN, GPIO.PUD_UP)
        GPIO.setup(self.DR, GPIO.IN, GPIO.PUD_UP)

    def read(self) -> dict:
        """Return {'left': bool, 'right': bool} where True means obstacle."""
        if not IS_RPI:
            return {
                "left": random.random() < 0.1,
                "right": random.random() < 0.1,
            }
        return {
            "left": GPIO.input(self.DL) == 0,
            "right": GPIO.input(self.DR) == 0,
        }


class TRSensor:
    """5-channel analog line-tracking sensor read through an SPI-like bit-bang.

    This implementation follows the original WaveShare example: the ADC is read
    with a one-sample delay, so sending address N returns the conversion for
    ADC channel N-1.  A dummy transaction at address 0 primes the converter,
    then the sensor channels are read in order.

    *channel_map* lists the ADC channels (0-based) for the physical sensors in
    left-to-right order.  The default ``[0, 1, 2, 3, 4]`` matches the original
    demo files.  If your board wires the sensors differently, change the map.
    """

    def __init__(self, num_sensors: int = 5, cs: int = 5, clock: int = 25,
                 address: int = 24, data_out: int = 23, button: int = 7,
                 channel_map: List[int] | None = None,
                 samples: int = 1, ema_alpha: float = 0.0,
                 on_line_threshold: int = 200, noise_threshold: int = 50):
        self.numSensors = num_sensors
        self.CS = cs
        self.Clock = clock
        self.Address = address
        self.DataOut = data_out
        self.Button = button

        # Default matches the original WaveShare demo: ADC channels 0..4.
        self.channel_map = channel_map or list(range(num_sensors))
        self._max_channel = max(self.channel_map)

        # Averaging / filtering options.
        self.samples = max(1, samples)
        self.ema_alpha = max(0.0, min(1.0, ema_alpha))
        self.on_line_threshold = on_line_threshold
        self.noise_threshold = noise_threshold
        # EMA state is stored per transaction sample (num_sensors + 1 values).
        self._ema = [None] * (num_sensors + 1)

        self.calibratedMin = [0] * self.numSensors
        self.calibratedMax = [1023] * self.numSensors
        self.last_value = 0

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.Clock, GPIO.OUT)
        GPIO.setup(self.Address, GPIO.OUT)
        GPIO.setup(self.CS, GPIO.OUT)
        GPIO.setup(self.DataOut, GPIO.IN, GPIO.PUD_UP)
        GPIO.setup(self.Button, GPIO.IN, GPIO.PUD_UP)

    def _read_addresses(self, addresses: List[int]) -> List[int]:
        """Low-level SPI-like read for a list of channel addresses.

        Returns the raw transaction values.  Due to the one-sample delay in the
        ADC, value[i] corresponds to the conversion requested by addresses[i-1].
        """
        n = len(addresses)
        accum = [0] * n

        for _ in range(self.samples):
            value = [0] * n
            for j, addr in enumerate(addresses):
                GPIO.output(self.CS, GPIO.LOW)
                for i in range(8):
                    if i < 4:
                        bit = (addr >> (3 - i)) & 0x01
                        GPIO.output(self.Address, GPIO.HIGH if bit else GPIO.LOW)
                    else:
                        GPIO.output(self.Address, GPIO.LOW)
                    value[j] <<= 1
                    if GPIO.input(self.DataOut):
                        value[j] |= 0x01
                    GPIO.output(self.Clock, GPIO.HIGH)
                    GPIO.output(self.Clock, GPIO.LOW)
                for _ in range(4):
                    value[j] <<= 1
                    if GPIO.input(self.DataOut):
                        value[j] |= 0x01
                    GPIO.output(self.Clock, GPIO.HIGH)
                    GPIO.output(self.Clock, GPIO.LOW)
                time.sleep(0.0001)
                GPIO.output(self.CS, GPIO.HIGH)

            for i in range(n):
                value[i] >>= 2
                accum[i] += value[i]

        result = [a // self.samples for a in accum]

        # Optional exponential moving average (low-pass filter).
        if self.ema_alpha > 0:
            for i in range(n):
                if self._ema[i] is None:
                    self._ema[i] = result[i]
                else:
                    self._ema[i] = int(
                        self.ema_alpha * result[i] + (1 - self.ema_alpha) * self._ema[i]
                    )
            return list(self._ema)
        return result

    def analog_read_all(self) -> List[int]:
        """Return ADC readings indexed by ADC channel number.

        Only the channels listed in *channel_map* are populated; others are 0.
        This is useful for telemetry/debugging.
        """
        if not IS_RPI:
            # Simulate a line under the middle sensor.
            base = [0] * (self._max_channel + 1)
            for ch in range(self._max_channel + 1):
                base[ch] = random.randint(50, 200)
            mid = self.numSensors // 2
            base[self.channel_map[mid]] = random.randint(850, 1023)
            return base

        # Send dummy (addr 0) followed by each mapped channel + 1 to account for
        # the one-sample delay in the ADC.
        addresses = [0] + [ch + 1 for ch in self.channel_map]
        raw = self._read_addresses(addresses)
        # raw[i+1] is the conversion for ADC channel channel_map[i].
        all_channels = [0] * (self._max_channel + 1)
        for i, ch in enumerate(self.channel_map):
            all_channels[ch] = raw[i + 1]
        return all_channels

    def analog_read(self) -> List[int]:
        """Read raw sensor values in physical left-to-right order."""
        all_channels = self.analog_read_all()
        return [all_channels[ch] for ch in self.channel_map]

    def calibrate(self) -> None:
        """Update calibration min/max by sampling the sensors."""
        max_sensor_values = [0] * self.numSensors
        min_sensor_values = [0] * self.numSensors

        for j in range(10):
            sensor_values = self.analog_read()
            for i in range(self.numSensors):
                if j == 0 or max_sensor_values[i] < sensor_values[i]:
                    max_sensor_values[i] = sensor_values[i]
                if j == 0 or min_sensor_values[i] > sensor_values[i]:
                    min_sensor_values[i] = sensor_values[i]

        for i in range(self.numSensors):
            if min_sensor_values[i] > self.calibratedMin[i]:
                self.calibratedMin[i] = min_sensor_values[i]
            if max_sensor_values[i] < self.calibratedMax[i]:
                self.calibratedMax[i] = max_sensor_values[i]

    def read_calibrated(self) -> List[int]:
        """Return values scaled to 0..1000 using stored calibration."""
        sensor_values = self.analog_read()
        for i in range(self.numSensors):
            denominator = self.calibratedMax[i] - self.calibratedMin[i]
            if denominator != 0:
                value = (sensor_values[i] - self.calibratedMin[i]) * 1000 // denominator
            else:
                value = 0
            value = max(0, min(1000, value))
            sensor_values[i] = value
        return sensor_values

    def read_line(self, white_line: bool = False) -> Tuple[int, List[int]]:
        """Return estimated line position and calibrated sensor values."""
        sensor_values = self.read_calibrated()
        avg = 0
        total = 0
        on_line = 0

        for i in range(self.numSensors):
            value = sensor_values[i]
            if white_line:
                value = 1000 - value
            if value > self.on_line_threshold:
                on_line = 1
            if value > self.noise_threshold:
                avg += value * (i * 1000)
                total += value

        if not on_line:
            if self.last_value < (self.numSensors - 1) * 1000 / 2:
                self.last_value = 0
            else:
                self.last_value = (self.numSensors - 1) * 1000
        else:
            self.last_value = avg // total

        return self.last_value, sensor_values

    def button_pressed(self) -> bool:
        """Return True if the on-board button is pressed (active-low)."""
        if not IS_RPI:
            return False
        return GPIO.input(self.Button) == 0
