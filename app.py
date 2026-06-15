"""Flask web application for the AlphaBot2 test platform."""
from __future__ import annotations

import json
import atexit
import sys

from flask import Flask, Response, render_template, jsonify, request

from controller import RobotController
from camera import Camera
from hardware import IS_RPI, GPIO_AVAILABLE, NEOPIXEL_AVAILABLE

app = Flask(__name__)
robot = RobotController()
camera = Camera()

print(
    f"[AlphaBot2] Platform: {'Raspberry Pi' if IS_RPI else 'PC/mock'} | "
    f"GPIO: {'real' if GPIO_AVAILABLE else 'mock'} | "
    f"NeoPixel: {'real' if NEOPIXEL_AVAILABLE else 'mock'} | "
    f"Camera: {camera.source}",
    file=sys.stderr,
)


@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Motor / motion
# ---------------------------------------------------------------------------

@app.route("/api/move", methods=["POST"])
def api_move():
    data = request.get_json(force=True, silent=True) or {}
    direction = data.get("direction", "stop")
    robot.move(direction)
    return jsonify({"status": "ok", "direction": direction})


@app.route("/api/speed", methods=["POST"])
def api_speed():
    data = request.get_json(force=True, silent=True) or {}
    speed = int(data.get("speed", 50))
    robot.set_speed(speed)
    return jsonify({"status": "ok", "speed": speed})


@app.route("/api/motor", methods=["POST"])
def api_motor():
    data = request.get_json(force=True, silent=True) or {}
    left = int(data.get("left", 0))
    right = int(data.get("right", 0))
    robot.set_motor(left, right)
    return jsonify({"status": "ok", "left": left, "right": right})


# ---------------------------------------------------------------------------
# Servo
# ---------------------------------------------------------------------------

@app.route("/api/servo", methods=["POST"])
def api_servo():
    data = request.get_json(force=True, silent=True) or {}
    direction = data.get("direction")
    if direction in ("up", "down", "left", "right", "stop"):
        robot.pan_tilt_move(direction)
        return jsonify({"status": "ok", "direction": direction})
    if direction == "center":
        robot.pan_tilt_center()
        return jsonify({"status": "ok", "direction": "center"})
    pan = data.get("pan")
    tilt = data.get("tilt")
    if pan is not None:
        robot.pan_tilt.set_pan(int(pan))
    if tilt is not None:
        robot.pan_tilt.set_tilt(int(tilt))
    return jsonify({
        "status": "ok",
        "pan": robot.pan_tilt.pan,
        "tilt": robot.pan_tilt.tilt,
    })


# ---------------------------------------------------------------------------
# RGB LEDs
# ---------------------------------------------------------------------------

@app.route("/api/rgb", methods=["POST"])
def api_rgb():
    data = request.get_json(force=True, silent=True) or {}
    r = int(data.get("r", 255))
    g = int(data.get("g", 255))
    b = int(data.get("b", 255))
    robot.leds.set_color(r, g, b)
    return jsonify({"status": "ok", "r": r, "g": g, "b": b})


@app.route("/api/rgb/mode", methods=["POST"])
def api_rgb_mode():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("mode", "static")
    robot.leds.set_mode(mode)
    return jsonify({"status": "ok", "mode": mode})


@app.route("/api/rgb/brightness", methods=["POST"])
def api_rgb_brightness():
    data = request.get_json(force=True, silent=True) or {}
    value = int(data.get("brightness", 255))
    robot.leds.set_brightness(value)
    return jsonify({"status": "ok", "brightness": value})


# ---------------------------------------------------------------------------
# Buzzer
# ---------------------------------------------------------------------------

@app.route("/api/buzzer", methods=["POST"])
def api_buzzer():
    data = request.get_json(force=True, silent=True) or {}
    state = data.get("state")
    if state == "on":
        robot.buzzer.on()
    elif state == "off":
        robot.buzzer.off()
    return jsonify({"status": "ok", "state": robot.buzzer.state})


# ---------------------------------------------------------------------------
# Demos
# ---------------------------------------------------------------------------

@app.route("/api/demo", methods=["POST"])
def api_demo():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("mode", "idle")
    robot.set_demo(mode)
    return jsonify({"status": "ok", "mode": mode})


@app.route("/api/calibrate", methods=["POST"])
def api_calibrate():
    def progress(i):
        pass
    robot.calibrate_line_sensor(spin_callback=progress)
    return jsonify({
        "status": "ok",
        "min": robot.tr_sensor.calibratedMin,
        "max": robot.tr_sensor.calibratedMax,
    })


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

@app.route("/api/telemetry")
def api_telemetry():
    return jsonify(robot.get_telemetry())


@app.route("/api/video")
def api_video():
    """MJPEG video stream."""
    return Response(
        camera.mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/api/camera/info")
def api_camera_info():
    return jsonify({
        "available": camera.is_available,
        "source": camera.source,
        "width": camera.width,
        "height": camera.height,
    })


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@atexit.register
def _shutdown():
    try:
        robot.shutdown()
    except Exception:
        pass
    try:
        camera.stop()
    except Exception:
        pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AlphaBot2 web test platform")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=5000, help="Listen port")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
