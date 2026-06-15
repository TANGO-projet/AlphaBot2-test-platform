"""Hardware abstraction layer for the AlphaBot2 webapp.

This module tries to import the real Raspberry Pi libraries (RPi.GPIO,
rpi_ws281x, smbus).  If any of them is missing or the platform is not a
Raspberry Pi, a lightweight mock implementation is used instead so the
webapp can be developed and tested on a regular Linux/Windows/macOS
machine.
"""
from __future__ import annotations

import os
import sys
import time
import math
import random
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _is_raspberry_pi() -> bool:
    """Best-effort detection of a Raspberry Pi board."""
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read()
            return "Raspberry Pi" in model
    except Exception:
        pass
    try:
        with open("/proc/cpuinfo", "r") as f:
            return any("BCM" in line.upper() for line in f)
    except Exception:
        pass
    return False

IS_RPI = _is_raspberry_pi()

# ---------------------------------------------------------------------------
# GPIO abstraction
# ---------------------------------------------------------------------------

try:
    import RPi.GPIO as _GPIO
    GPIO = _GPIO
except Exception:
    # Mock GPIO implementation
    class _MockGPIO:
        BCM = "BCM"
        BOARD = "BOARD"
        OUT = "OUT"
        IN = "IN"
        HIGH = 1
        LOW = 0
        PUD_UP = "PUD_UP"
        PUD_DOWN = "PUD_DOWN"

        def __init__(self):
            self._mode = None
            self._pins: dict[int, dict] = {}
            self._callbacks: dict[int, List[Callable]] = {}

        def setmode(self, mode):
            self._mode = mode

        def setwarnings(self, flag):
            pass

        def setup(self, pin, mode, pull_up_down=None, initial=None):
            value = 0
            if initial is not None:
                value = 1 if initial else 0
            self._pins[pin] = {"mode": mode, "value": value, "pud": pull_up_down}

        def output(self, pin, value):
            if pin in self._pins:
                self._pins[pin]["value"] = value

        def input(self, pin):
            if pin not in self._pins:
                return 0
            # Pull-up pins read HIGH by default in mock unless explicitly driven
            if self._pins[pin].get("pud") == self.PUD_UP:
                return 0 if self._pins[pin].get("driven") else 1
            return self._pins[pin]["value"]

        def cleanup(self):
            self._pins.clear()

        def add_event_detect(self, pin, edge, callback=None, bouncetime=None):
            self._callbacks.setdefault(pin, []).append(callback)

        def remove_event_detect(self, pin):
            self._callbacks.pop(pin, None)

        class PWM:
            def __init__(self, pin, frequency):
                self._pin = pin
                self._frequency = frequency
                self._dc = 0

            def start(self, dc):
                self._dc = dc

            def ChangeDutyCycle(self, dc):
                self._dc = dc

            def stop(self):
                self._dc = 0

    GPIO = _MockGPIO()

# ---------------------------------------------------------------------------
# SMBus / PCA9685 abstraction
# ---------------------------------------------------------------------------

try:
    import smbus
except Exception:
    smbus = None  # type: ignore


class MockSMBus:
    """A minimal mock SMBus that stores register writes in memory."""

    def __init__(self, bus: int):
        self._bus = bus
        self._regs: dict[int, dict[int, int]] = {}

    def write_byte_data(self, addr: int, reg: int, value: int) -> None:
        self._regs.setdefault(addr, {})[reg] = value & 0xFF

    def read_byte_data(self, addr: int, reg: int) -> int:
        return self._regs.get(addr, {}).get(reg, 0)

    def write_i2c_block_data(self, addr: int, reg: int, data: List[int]) -> None:
        for i, v in enumerate(data):
            self.write_byte_data(addr, reg + i, v)

    def read_i2c_block_data(self, addr: int, reg: int, length: int) -> List[int]:
        return [self.read_byte_data(addr, reg + i) for i in range(length)]


class SMBus:
    """Thin wrapper so we can fall back to a mock bus on non-Pi machines."""

    def __init__(self, bus: int):
        if smbus is not None:
            self._bus = smbus.SMBus(bus)
        else:
            self._bus = MockSMBus(bus)

    def write_byte_data(self, addr: int, reg: int, value: int) -> None:
        self._bus.write_byte_data(addr, reg, value)

    def read_byte_data(self, addr: int, reg: int) -> int:
        return self._bus.read_byte_data(addr, reg)


# ---------------------------------------------------------------------------
# WS2812 / NeoPixel abstraction
# ---------------------------------------------------------------------------

try:
    from rpi_ws281x import Adafruit_NeoPixel as _Adafruit_NeoPixel, Color as _Color
    NeoPixel = _Adafruit_NeoPixel
    Color = _Color
except Exception:
    @dataclass
    class _MockColor:
        r: int
        g: int
        b: int

    def _Color(r, g, b):
        return _MockColor(r & 0xFF, g & 0xFF, b & 0xFF)

    class _MockNeoPixel:
        def __init__(self, num, pin, freq_hz=800000, dma=10, invert=False,
                     brightness=255, pwm_channel=0, strip_type=None):
            self.num = num
            self.pin = pin
            self._pixels = [_Color(0, 0, 0) for _ in range(num)]
            self._brightness = max(0, min(255, brightness))

        def begin(self):
            pass

        def show(self):
            pass

        def setPixelColor(self, n, color):
            if 0 <= n < len(self._pixels):
                self._pixels[n] = color

        def getPixelColor(self, n):
            return self._pixels[n]

        def numPixels(self):
            return len(self._pixels)

        def setBrightness(self, brightness):
            self._brightness = max(0, min(255, brightness))

    NeoPixel = _MockNeoPixel
    Color = _Color if "_Color" in dir() else _Color  # type: ignore

# Re-export Color so downstream modules can import it from here.
Color = Color  # noqa: PLW0127


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def wheel(pos: int):
    """Rainbow colour across 0-255 positions."""
    pos &= 0xFF
    if pos < 85:
        return Color(pos * 3, 255 - pos * 3, 0)
    if pos < 170:
        pos -= 85
        return Color(255 - pos * 3, 0, pos * 3)
    pos -= 170
    return Color(0, pos * 3, 255 - pos * 3)


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Periodic background helpers
# ---------------------------------------------------------------------------

def start_background_loop(interval: float, callback: Callable, daemon: bool = True):
    """Start a background thread that calls *callback* every *interval* seconds."""
    def loop():
        while True:
            try:
                callback()
            except Exception as exc:
                print(f"Background loop error: {exc}", file=sys.stderr)
            time.sleep(interval)

    t = threading.Thread(target=loop, daemon=daemon)
    t.start()
    return t
