"""WS2812 RGB LED control for the AlphaBot2 tail LEDs."""
from __future__ import annotations

import time
import threading

from hardware import NeoPixel, Color, wheel, clamp, IS_RPI


class RGBLeds:
    """Control the 4 WS2812 RGB LEDs on the AlphaBot2."""

    def __init__(
        self,
        count: int = 4,
        pin: int = 18,
        brightness: int = 255,
        dma: int = 10,
    ):
        self.count = count
        self._rgb = 0xFFFFFF
        self._mode = "static"  # static | breath | flash | rainbow | off
        self._brightness = clamp(brightness, 0, 255)
        self._running = True
        self._lock = threading.Lock()
        self._breath_x = 0
        self._flash_index = 0
        self._rainbow_offset = 0

        self.strip = NeoPixel(
            count,
            pin,
            800000,
            dma,
            False,
            self._brightness,
            0,
        )
        try:
            self.strip.begin()
        except Exception:
            pass
        self.clear()

    # ------------------------------------------------------------------
    # Colour helpers
    # ------------------------------------------------------------------

    @staticmethod
    def from_rgb(r: int, g: int, b: int) -> int:
        return ((clamp(r, 0, 255) << 16) |
                (clamp(g, 0, 255) << 8) |
                clamp(b, 0, 255))

    @staticmethod
    def to_rgb(value: int) -> tuple:
        return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def set_color(self, r: int, g: int, b: int):
        with self._lock:
            self._rgb = self.from_rgb(r, g, b)
            if self._mode == "off":
                self._mode = "static"

    def set_hex(self, hex_color: int):
        with self._lock:
            self._rgb = hex_color & 0xFFFFFF
            if self._mode == "off":
                self._mode = "static"

    def set_mode(self, mode: str):
        mode = mode.lower()
        if mode not in ("static", "breath", "flash", "rainbow", "off"):
            mode = "static"
        with self._lock:
            self._mode = mode
            self._breath_x = 0
            self._flash_index = 0
            self._rainbow_offset = 0

    def set_brightness(self, value: int):
        value = clamp(value, 0, 255)
        with self._lock:
            self._brightness = value
            try:
                self.strip.setBrightness(value)
            except Exception:
                pass

    def clear(self):
        with self._lock:
            self._mode = "off"
        self._show_all(Color(0, 0, 0))

    # ------------------------------------------------------------------
    # Internal show helpers
    # ------------------------------------------------------------------

    def _show_all(self, color):
        for i in range(self.count):
            self.strip.setPixelColor(i, color)
        try:
            self.strip.show()
        except Exception:
            pass

    def _tick(self):
        with self._lock:
            mode = self._mode
            rgb = self._rgb

        if mode == "off":
            self._show_all(Color(0, 0, 0))
            time.sleep(0.05)
            return

        if mode == "static":
            r, g, b = self.to_rgb(rgb)
            self._show_all(Color(r, g, b))
            time.sleep(0.05)
            return

        if mode == "breath":
            # Parabola 0..1 over x = 0..200
            x = self._breath_x
            f = (-1 / 10000.0) * x * x + (1 / 50.0) * x
            r, g, b = self.to_rgb(rgb)
            r = int(r * f)
            g = int(g * f)
            b = int(b * f)
            self._show_all(Color(r, g, b))
            self._breath_x = (x + 1) % 200
            time.sleep(0.02)
            return

        if mode == "flash":
            flash_times = [0.3, 0.2, 0.1, 0.05, 0.05, 0.1, 0.2, 0.5, 0.2]
            r, g, b = self.to_rgb(rgb)
            self._show_all(Color(r, g, b))
            time.sleep(flash_times[self._flash_index])
            self._show_all(Color(0, 0, 0))
            time.sleep(flash_times[self._flash_index])
            self._flash_index = (self._flash_index + 1) % len(flash_times)
            return

        if mode == "rainbow":
            offset = self._rainbow_offset
            for i in range(self.count):
                c = wheel((int(i * 256 / self.count) + offset) & 0xFF)
                self.strip.setPixelColor(i, c)
            try:
                self.strip.show()
            except Exception:
                pass
            self._rainbow_offset = (offset + 1) & 0xFF
            time.sleep(0.02)
            return

    def start_loop(self, daemon: bool = True) -> threading.Thread:
        def loop():
            while self._running:
                try:
                    self._tick()
                except Exception as exc:
                    print(f"RGB loop error: {exc}")
                    time.sleep(0.1)

        t = threading.Thread(target=loop, daemon=daemon)
        t.start()
        return t

    def stop(self):
        self._running = False
        self.clear()
