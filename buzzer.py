"""Simple active buzzer driver."""
from __future__ import annotations

from hardware import GPIO


class Buzzer:
    def __init__(self, pin: int = 4):
        self.pin = pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.pin, GPIO.OUT)
        self.off()

    def on(self):
        GPIO.output(self.pin, GPIO.HIGH)

    def off(self):
        GPIO.output(self.pin, GPIO.LOW)

    @property
    def state(self) -> bool:
        try:
            return GPIO.input(self.pin) == GPIO.HIGH
        except Exception:
            return False
