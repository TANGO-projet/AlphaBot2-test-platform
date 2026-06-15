"""NEC-like IR remote decoder.

This module provides a background thread that decodes button presses from a
GPIO-connected IR receiver (active-low, 38 kHz).  It exposes the last decoded
key code and a human-readable name.
"""
from __future__ import annotations

import time
import threading

from hardware import GPIO, IS_RPI

# Common WaveShare IR remote mapping used in the original examples.
KEY_MAP = {
    0x18: "up",
    0x52: "down",
    0x08: "left",
    0x5A: "right",
    0x1C: "ok",
    0x15: "vol+",
    0x07: "vol-",
    0x45: "power",
    0x47: "menu",
    0x44: "test",
    0x40: "back",
    0x43: "play",
    0x09: "0",
    0x16: "1",
    0x19: "2",
    0x0D: "3",
    0x0C: "4",
    0x18: "5",
    0x5E: "6",
    0x08: "7",
    0x1C: "8",
    0x5A: "9",
}


class IRRemote:
    def __init__(self, pin: int = 17):
        self.pin = pin
        self.last_code: int | None = None
        self.last_name: str | None = None
        self.last_seen = 0.0
        self._running = True

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.pin, GPIO.IN)

    def _decode(self) -> int | str | None:
        if not IS_RPI:
            return None

        if GPIO.input(self.pin) != 0:
            return None

        count = 0
        while GPIO.input(self.pin) == 0 and count < 200:
            count += 1
            time.sleep(0.00006)
        if count < 10:
            return None

        count = 0
        while GPIO.input(self.pin) == 1 and count < 80:
            count += 1
            time.sleep(0.00006)

        idx = 0
        bit = 0
        data = [0, 0, 0, 0]
        for _ in range(32):
            count = 0
            while GPIO.input(self.pin) == 0 and count < 15:
                count += 1
                time.sleep(0.00006)
            count = 0
            while GPIO.input(self.pin) == 1 and count < 40:
                count += 1
                time.sleep(0.00006)
            if count > 7:
                data[idx] |= 1 << bit
            if bit == 7:
                bit = 0
                idx += 1
            else:
                bit += 1

        if data[0] + data[1] == 0xFF and data[2] + data[3] == 0xFF:
            return data[2]
        return "repeat"

    def _loop(self):
        while self._running:
            try:
                key = self._decode()
                if key is not None and key != "repeat":
                    self.last_code = key
                    self.last_name = KEY_MAP.get(key, f"0x{key:02X}")
                    self.last_seen = time.time()
            except Exception:
                pass
            time.sleep(0.005)

    def start(self, daemon: bool = True) -> threading.Thread:
        t = threading.Thread(target=self._loop, daemon=daemon)
        t.start()
        return t

    def stop(self):
        self._running = False

    def recent_key(self, timeout: float = 0.5) -> dict:
        """Return the most recent key if it was seen within *timeout* seconds."""
        if self.last_code is None or time.time() - self.last_seen > timeout:
            return {"code": None, "name": None}
        return {"code": self.last_code, "name": self.last_name}
