"""Camera support for the AlphaBot2 webapp.

Tries modern Raspberry Pi libraries first, then OpenCV, and finally falls back
to a generated test pattern so the UI works everywhere.
"""
from __future__ import annotations

import time
import threading
from typing import Generator

try:
    import numpy as np
    HAVE_NUMPY = True
except Exception:
    HAVE_NUMPY = False
    np = None  # type: ignore

# Try OpenCV first; it is the most common camera backend on both desktop and Pi.
try:
    import cv2
    HAVE_CV2 = True
except Exception:
    HAVE_CV2 = False

# Try picamera2 (modern Raspberry Pi OS).  We prefer it when available because
# it integrates better with the official Pi camera modules.
try:
    from picamera2 import Picamera2
    HAVE_PICAMERA2 = True
except Exception:
    HAVE_PICAMERA2 = False


class Camera:
    """Threaded camera capture with MJPEG streaming support."""

    DEFAULT_WIDTH = 640
    DEFAULT_HEIGHT = 480
    FPS = 24

    def __init__(self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT):
        self.width = width
        self.height = height
        self._frame: bytes | None = None
        self._lock = threading.Lock()
        self._running = True
        self._source = "mock"
        self._capture = None
        self._picam = None
        self.error: str | None = None

        # 1) Try picamera2 first on Raspberry Pi.
        if HAVE_PICAMERA2:
            try:
                self._picam = Picamera2()
                cfg = self._picam.create_video_configuration(
                    main={"size": (width, height), "format": "RGB888"}
                )
                self._picam.configure(cfg)
                self._picam.start()
                # Verify we can actually grab a frame.
                self._picam.capture_array()
                self._source = "picamera2"
                time.sleep(0.2)
            except Exception as exc:
                self.error = f"picamera2 failed: {exc}"
                print(f"[Camera] {self.error}")
                try:
                    if self._picam:
                        self._picam.stop()
                except Exception:
                    pass
                self._picam = None

        # 2) Fall back to OpenCV (USB webcam / desktop / Pi without picamera2).
        if self._source == "mock" and HAVE_CV2:
            try:
                # On the Pi, V4L2 backend is usually index 0.
                self._capture = cv2.VideoCapture(0)
                self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                self._capture.set(cv2.CAP_PROP_FPS, self.FPS)
                ok, _ = self._capture.read()
                if self._capture.isOpened() and ok:
                    self._source = "opencv"
                    self.error = None
                else:
                    raise RuntimeError("OpenCV camera index 0 is not returning frames")
            except Exception as exc:
                self.error = (self.error or "") + f"; OpenCV failed: {exc}".lstrip("; ")
                print(f"[Camera] {self.error}")
                if self._capture:
                    self._capture.release()
                self._capture = None

        if self._source == "mock":
            print("[Camera] Using mock test pattern.")

        # Start capture thread.
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Capture loop
    # ------------------------------------------------------------------

    def _capture_loop(self):
        while self._running:
            try:
                if self._source == "picamera2":
                    self._grab_picamera2()
                elif self._source == "opencv":
                    self._grab_opencv()
                else:
                    self._grab_mock()
            except Exception as exc:
                print(f"[Camera] capture error: {exc}")
                self._grab_mock()
            time.sleep(1.0 / self.FPS)

    def _encode_jpeg(self, array) -> bytes:
        if HAVE_CV2:
            _, buf = cv2.imencode(".jpg", array)
            return buf.tobytes()
        return self._test_pattern()

    def _grab_picamera2(self):
        arr = self._picam.capture_array()
        # picamera2 returns RGB; OpenCV's imencode expects BGR.
        if arr.shape[2] == 3 and HAVE_CV2:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        with self._lock:
            self._frame = self._encode_jpeg(arr)

    def _grab_opencv(self):
        ok, frame = self._capture.read()
        if not ok:
            self._grab_mock()
            return
        frame = cv2.resize(frame, (self.width, self.height))
        with self._lock:
            self._frame = self._encode_jpeg(frame)

    def _grab_mock(self):
        with self._lock:
            self._frame = self._test_pattern()

    # Tiny valid 1x1 grey JPEG used when neither OpenCV nor NumPy is available.
    _GREY_JPEG = bytes.fromhex(
        "ffd8ffe000104a46494600010101006000600000ffdb004300"
        "08060607060508070707090908080a0c140d0c0b0b0c191213"
        "0f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30"
        "312d34393b3e3e3e252b4f463b3d353d3e3bffc0000b080001"
        "00010101011100ffc4001f0000010501010101010100000000"
        "000000000102030405060708090a0bffc400b5100002010303"
        "020403050504040000017d0102030004110512213141061351"
        "6107227114328191a1082342b1c11552d1f0d2433472a125b1"
        "c23533627440082c2d2e243510627334f1257639a3d385e3f3"
        "4934a4b4c4d4e4f465758595a5b5c5d5e5f566768696a6b6c6d"
        "6e6f6778797a7b7c7d7e7f48595a5b5c5d5e5f55666768696a6b"
        "6c6d6e6f5768696a6b6c6d6e6f505152535455565758595a5b5c"
        "5d5e5f60ffc4001f0100030101010101010101010000000000"
        "000102030405060708090a0bffc400b5110002010204040304"
        "07050404000102770001020311040521310612415107617113"
        "22325281a11442b1c1d1e2333462728290a162435445b3f1ffda"
        "0008010100003f00bf805f14f6d5555555555555557ffd9"
    )

    def _test_pattern(self) -> bytes:
        """Generate a simple moving-colour-bars test pattern."""
        if not HAVE_CV2 or not HAVE_NUMPY:
            return self._GREY_JPEG
        t = time.time()
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        bar_width = self.width // 8
        for i in range(8):
            hue = int((i * 32 + t * 30) % 180)
            color = cv2.cvtColor(np.uint8([[[hue, 255, 255]]]), cv2.COLOR_HSV2BGR)[0][0]
            x1 = i * bar_width
            x2 = self.width if i == 7 else (i + 1) * bar_width
            img[:, x1:x2] = color
        cv2.putText(
            img,
            "AlphaBot2 Camera - No hardware detected",
            (20, self.height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._frame

    def mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yield multipart JPEG chunks for Flask streaming."""
        while self._running:
            frame = self.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                b"\r\n" + frame + b"\r\n"
            )
            time.sleep(1.0 / self.FPS)

    @property
    def source(self) -> str:
        return self._source

    @property
    def is_available(self) -> bool:
        return self._source != "mock" or self._frame is not None

    def stop(self):
        self._running = False
        try:
            if self._picam:
                self._picam.stop()
        except Exception:
            pass
        try:
            if self._capture:
                self._capture.release()
        except Exception:
            pass
