# AlphaBot2 Test Platform

A modern Python 3 web application that brings together all the original WaveShare AlphaBot2 Raspberry Pi examples into one place.

## What it replaces

The original `AlphaBot2-Demo/RaspberryPi/AlphaBot2/` folder contained several standalone scripts and small web servers written for Python 2 / old versions of `bottle`. This project ports and unifies them:

| Original example | Webapp feature |
| ---------------- | -------------- |
| `AlphaBot2.py` | Motor driver (`robot.py`) |
| `PCA9685.py` | Pan/tilt servo control |
| `Ultrasonic_Ranging.py` | Live distance telemetry |
| `Ultrasonic_Obstacle_Avoidance.py` | Autonomous "Ultrasonic Avoid" demo |
| `Infrared_Obstacle_Avoidance.py` | Autonomous "Infrared Avoid" demo |
| `Line_Follow.py` | Autonomous "Line Follow" demo + calibration |
| `TRSensors.py` | Line sensor telemetry |
| `ws2812.py` / `Web-RGB` | RGB LED static / breath / flash / rainbow modes |
| `Joystick.py` | Web D-pad + speed slider |
| `IRremote.py` | IR remote key display |
| `Web-Control`, `App-Control`, `Bluetooth-Control` | Unified Flask web UI |
| mjpg-streamer camera stream | Built-in MJPEG camera stream (`/api/video`) |

## Features

* Single Flask server (replaces `bottle`, `SocketServer`, and the multiple small apps).
* Responsive web UI with:
  * D-pad motor control and speed slider
  * Pan/tilt servo control
  * RGB LED colour picker + animation modes
  * Live sensor telemetry (ultrasonic, IR obstacle, line sensor, IR remote)
  * One-click autonomous demos
  * Line-sensor calibration
  * Buzzer toggle
* Works on a real Raspberry Pi **and** on a normal PC for UI development/testing.
* Mock hardware layer automatically activates when `RPi.GPIO`, `smbus`, or `rpi_ws281x` are unavailable.

## Hardware requirements (real robot)

* Raspberry Pi with Raspberry Pi OS
* AlphaBot2 robot kit
* I2C enabled (for PCA9685 servo driver)
* SPI disabled / GPIO free for the TR sensor bit-bang pins
* Optional: HC-SR04 ultrasonic module, IR obstacle modules, WS2812 LEDs, IR receiver, active buzzer, Raspberry Pi camera or USB webcam

## Installation

On the Raspberry Pi:

```bash
# System dependencies
sudo apt update
sudo apt install python3-pip python3-venv python3-smbus i2c-tools

# Camera (choose the one matching your setup)
# - Official Raspberry Pi camera module:
sudo apt install -y python3-picamera2 libcap-dev
# - Or USB webcam support via OpenCV:
pip install opencv-python-headless numpy

# App dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Optional but recommended for NeoPixels
pip install rpi_ws281x RPi.GPIO

pip install opencv-python-headless numpy  # optional camera backend
```

## Permissions on Raspberry Pi

Real GPIO/NeoPixel/I2C hardware needs appropriate permissions. If you see `Can't open /dev/mem: Permission denied` or a segmentation fault, your user does not have hardware access.

### Quick fix

Run with `sudo` (simplest, but not recommended long-term):

```bash
sudo $(which python) run.py --host 0.0.0.0 --port 5000
```

When using `sudo`, put environment variables **after** `sudo` so they are preserved:

```bash
sudo ALPHABOT_CAMERA_BACKEND=picamera2 $(which python) run.py --host 0.0.0.0 --port 5000
```

### Recommended fix

Add your user to the `gpio` and `i2c` groups, then log out and back in (or reboot):

```bash
sudo usermod -a -G gpio,i2c $USER
```

Notes:
* `RPi.GPIO` and `rpi_ws281x` (WS2812 LEDs) use `/dev/gpiomem`, which the `gpio` group can access.
* Pan/tilt servos use I2C (`/dev/i2c-1`), which the `i2c` group can access.
* If you still see `/dev/mem` errors from `rpi_ws281x`, run with `sudo`.

### Force mock mode

To test the web UI without touching real hardware, run:

```bash
ALPHABOT_MOCK=1 python run.py --host 0.0.0.0 --port 5000
```

## Running

```bash
source venv/bin/activate
python run.py
```

Then open `http://<pi-ip>:5000` in a browser.

You can also specify host/port:

```bash
python run.py --host 0.0.0.0 --port 8080
```

## Camera troubleshooting

If the web UI shows `Source: mock`, the camera backend failed. The error message under the stream will tell you why.

### Official Raspberry Pi camera module

Make sure the camera interface is enabled:

```bash
sudo raspi-config
# Interface Options → Camera → Yes
```

Install picamera2 (Bookworm / Bullseye):

```bash
sudo apt install -y python3-picamera2
```

**Important:** `python3-picamera2` is installed as a system package. If you run the app inside a virtualenv, that venv must be able to see system packages. Either recreate it with system site-packages:

```bash
rm -rf venv
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python-headless numpy
```

Or test picamera2 with the system Python:

```bash
python3 -c "from picamera2 import Picamera2; p=Picamera2(); p.start(); p.capture_array(); print('OK')"
```

### USB webcam

If you use a USB webcam, install OpenCV:

```bash
pip install opencv-python-headless numpy
```

The app will automatically try camera indices 0-3. You can force a specific index:

```bash
ALPHABOT_CAMERA_INDEX=1 python run.py --host 0.0.0.0 --port 5000
```

### Force a specific backend

```bash
# Force picamera2
ALPHABOT_CAMERA_BACKEND=picamera2 python run.py

# Force OpenCV with a specific index
ALPHABOT_CAMERA_BACKEND=opencv ALPHABOT_CAMERA_INDEX=0 python run.py

# Force mock/test pattern
ALPHABOT_CAMERA_BACKEND=mock python run.py
```

## Line sensor (TRSensor) troubleshooting

The telemetry panel shows the active ADC channel map (`TR channels`) and the raw ADC readings (`TR raw`).

The default mapping follows the original WaveShare demo files: the five physical sensors are read from ADC channels `0,1,2,3,4` (the demo sends addresses `0..5` and discards the first result because the ADC has a one-sample delay).

If only one sensor responds or the values seem mapped to the wrong physical sensor, your board may use a different wiring. Touch each sensor one by one and watch the `TR raw` values in the telemetry panel. The channel that changes corresponds to the sensor you are touching. Then set `ALPHABOT_TR_CHANNELS` to the left-to-right ADC channel order of your sensors, for example:

```bash
ALPHABOT_TR_CHANNELS=1,2,3,4,5 python run.py
```

### Noise / sensitivity tuning

If the raw values jump around (e.g. 959-963) or the line follow demo reacts to noise, you can tune the sensor in software:

```bash
# Average 5 ADC samples per reading and apply a light low-pass filter
ALPHABOT_TR_SAMPLES=5 ALPHABOT_TR_EMA=0.3 python run.py

# Raise the noise floor so small fluctuations are ignored
ALPHABOT_TR_NOISE=100 python run.py

# Require a stronger line signal before considering a sensor "on the line"
ALPHABOT_TR_ON_LINE=300 python run.py
```

Environment variables:
* `ALPHABOT_TR_SAMPLES` — how many ADC samples to average (default 1)
* `ALPHABOT_TR_EMA` — exponential moving average factor 0..1 (default 0, i.e. off)
* `ALPHABOT_TR_NOISE` — minimum calibrated value used in the line-position average (default 50)
* `ALPHABOT_TR_ON_LINE` — minimum calibrated value to consider a sensor over the line (default 200)

### Hardware tuning

The TR sensor module also has small potentiometers (one per sensor). Turning them adjusts the IR LED brightness / comparator threshold. If the raw values are always high and barely change when you move the sensor over a line, try adjusting the pots slowly while watching the `TR raw` telemetry until you get a clear swing between light and dark surfaces.

## Project layout

```
.
├── app.py          # Flask routes
├── controller.py   # High-level robot controller + demos
├── hardware.py     # GPIO/SMBus/NeoPixel abstraction with mock fallback
├── robot.py        # AlphaBot2 motor driver
├── pca9685.py      # PCA9685 servo driver
├── sensors.py      # Ultrasonic, IR, TR line sensors
├── camera.py       # Pi camera / OpenCV / mock MJPEG stream
├── leds.py         # WS2812 RGB LEDs
├── buzzer.py       # Active buzzer
├── ir_remote.py    # NEC IR decoder
├── static/         # CSS + JS
├── templates/      # HTML
├── requirements.txt
├── run.py
└── README.md
```

## Safety notes

* Always place the robot on a stand or hold the wheels off the ground when testing motors for the first time.
* The autonomous demos will drive the robot. Use the **Stop / Idle** button to regain manual control instantly.
* `RPi.GPIO` and real GPIO access may require running as root unless your user is in the `gpio` group.

## License

Same permissive terms as the original WaveShare examples unless otherwise stated.
