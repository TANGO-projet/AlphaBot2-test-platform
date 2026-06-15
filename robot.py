"""AlphaBot2 motor driver.

Consolidates the motor control logic from the original WaveShare examples
(AlphaBot2.py / AlphaBot.py) into a single, reusable class.
"""
from __future__ import annotations

import atexit

from hardware import GPIO


class AlphaBot2:
    """Two-motor differential-drive robot controller.

    Parameters are BCM pin numbers.  Defaults match the WaveShare AlphaBot2
    Raspberry Pi examples.
    """

    def __init__(
        self,
        ain1: int = 12,
        ain2: int = 13,
        ena: int = 6,
        bin1: int = 20,
        bin2: int = 21,
        enb: int = 26,
    ):
        self.AIN1 = ain1
        self.AIN2 = ain2
        self.BIN1 = bin1
        self.BIN2 = bin2
        self.ENA = ena
        self.ENB = enb
        self.PA = 50
        self.PB = 50

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in (self.AIN1, self.AIN2, self.BIN1, self.BIN2, self.ENA, self.ENB):
            GPIO.setup(pin, GPIO.OUT)

        self.PWMA = GPIO.PWM(self.ENA, 500)
        self.PWMB = GPIO.PWM(self.ENB, 500)
        self.PWMA.start(self.PA)
        self.PWMB.start(self.PB)
        self.stop()

        atexit.register(self.cleanup)

    # ------------------------------------------------------------------
    # Basic motion
    # ------------------------------------------------------------------

    def stop(self):
        self.PWMA.ChangeDutyCycle(0)
        self.PWMB.ChangeDutyCycle(0)
        GPIO.output(self.AIN1, GPIO.LOW)
        GPIO.output(self.AIN2, GPIO.LOW)
        GPIO.output(self.BIN1, GPIO.LOW)
        GPIO.output(self.BIN2, GPIO.LOW)

    def forward(self):
        self.PWMA.ChangeDutyCycle(self.PA)
        self.PWMB.ChangeDutyCycle(self.PB)
        GPIO.output(self.AIN1, GPIO.LOW)
        GPIO.output(self.AIN2, GPIO.HIGH)
        GPIO.output(self.BIN1, GPIO.LOW)
        GPIO.output(self.BIN2, GPIO.HIGH)

    def backward(self):
        self.PWMA.ChangeDutyCycle(self.PA)
        self.PWMB.ChangeDutyCycle(self.PB)
        GPIO.output(self.AIN1, GPIO.HIGH)
        GPIO.output(self.AIN2, GPIO.LOW)
        GPIO.output(self.BIN1, GPIO.HIGH)
        GPIO.output(self.BIN2, GPIO.LOW)

    def left(self):
        self.PWMA.ChangeDutyCycle(30)
        self.PWMB.ChangeDutyCycle(30)
        GPIO.output(self.AIN1, GPIO.HIGH)
        GPIO.output(self.AIN2, GPIO.LOW)
        GPIO.output(self.BIN1, GPIO.LOW)
        GPIO.output(self.BIN2, GPIO.HIGH)

    def right(self):
        self.PWMA.ChangeDutyCycle(30)
        self.PWMB.ChangeDutyCycle(30)
        GPIO.output(self.AIN1, GPIO.LOW)
        GPIO.output(self.AIN2, GPIO.HIGH)
        GPIO.output(self.BIN1, GPIO.HIGH)
        GPIO.output(self.BIN2, GPIO.LOW)

    def set_speed(self, value: int):
        """Set both motors to the same PWM duty cycle (0-100)."""
        value = max(0, min(100, int(value)))
        self.set_pwma(value)
        self.set_pwmb(value)

    def set_pwma(self, value: int):
        self.PA = max(0, min(100, int(value)))
        self.PWMA.ChangeDutyCycle(self.PA)

    def set_pwmb(self, value: int):
        self.PB = max(0, min(100, int(value)))
        self.PWMB.ChangeDutyCycle(self.PB)

    def set_motor(self, left: int, right: int):
        """Direct per-motor control with signed speed (-100..100)."""
        right = max(-100, min(100, int(right)))
        left = max(-100, min(100, int(left)))

        if right >= 0:
            GPIO.output(self.AIN1, GPIO.HIGH)
            GPIO.output(self.AIN2, GPIO.LOW)
            self.PWMA.ChangeDutyCycle(right)
        else:
            GPIO.output(self.AIN1, GPIO.LOW)
            GPIO.output(self.AIN2, GPIO.HIGH)
            self.PWMA.ChangeDutyCycle(-right)

        if left >= 0:
            GPIO.output(self.BIN1, GPIO.HIGH)
            GPIO.output(self.BIN2, GPIO.LOW)
            self.PWMB.ChangeDutyCycle(left)
        else:
            GPIO.output(self.BIN1, GPIO.LOW)
            GPIO.output(self.BIN2, GPIO.HIGH)
            self.PWMB.ChangeDutyCycle(-left)

    def cleanup(self):
        try:
            self.stop()
        except Exception:
            pass
        try:
            self.PWMA.stop()
            self.PWMB.stop()
        except Exception:
            pass


# Convenience alias used in some original examples.
AlphaBot = AlphaBot2
