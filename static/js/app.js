const API = "/api";

async function post(path, body = {}) {
    const res = await fetch(API + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

// ---------------------------------------------------------------------------
// D-pad drive
// ---------------------------------------------------------------------------
const dpad = document.getElementById("dpad");
for (const btn of dpad.querySelectorAll("button")) {
    const send = (dir) => post("/move", { direction: dir });
    const down = () => send(btn.dataset.dir);
    const up = () => send("stop");
    btn.addEventListener("mousedown", down);
    btn.addEventListener("mouseup", up);
    btn.addEventListener("mouseleave", up);
    btn.addEventListener("touchstart", (e) => { e.preventDefault(); down(); });
    btn.addEventListener("touchend", (e) => { e.preventDefault(); up(); });
}

// ---------------------------------------------------------------------------
// Speed
// ---------------------------------------------------------------------------
const speedInput = document.getElementById("speed");
const speedVal = document.getElementById("speed-val");
speedInput.addEventListener("input", () => {
    speedVal.textContent = speedInput.value;
    post("/speed", { speed: parseInt(speedInput.value, 10) });
});

// ---------------------------------------------------------------------------
// Servo
// ---------------------------------------------------------------------------
const servoPad = document.querySelector(".dpad.small");
for (const btn of servoPad.querySelectorAll("button")) {
    const send = (dir) => post("/servo", { direction: dir });
    const down = () => send(btn.dataset.servo);
    const up = () => send("stop");
    btn.addEventListener("mousedown", down);
    btn.addEventListener("mouseup", up);
    btn.addEventListener("mouseleave", up);
    btn.addEventListener("touchstart", (e) => { e.preventDefault(); down(); });
    btn.addEventListener("touchend", (e) => { e.preventDefault(); up(); });
}

document.getElementById("pan").addEventListener("input", (e) => post("/servo", { pan: parseInt(e.target.value, 10) }));
document.getElementById("tilt").addEventListener("input", (e) => post("/servo", { tilt: parseInt(e.target.value, 10) }));

// ---------------------------------------------------------------------------
// RGB LEDs
// ---------------------------------------------------------------------------
const colorPicker = document.getElementById("color-picker");
function hexToRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return { r: (n >> 16) & 0xFF, g: (n >> 8) & 0xFF, b: n & 0xFF };
}
colorPicker.addEventListener("input", () => post("/rgb", hexToRgb(colorPicker.value)));

document.getElementById("led-off").addEventListener("click", () => post("/rgb/mode", { mode: "off" }));

for (const btn of document.querySelectorAll("button.mode")) {
    btn.addEventListener("click", () => {
        document.querySelectorAll("button.mode").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        post("/rgb/mode", { mode: btn.dataset.mode });
    });
}

document.getElementById("brightness").addEventListener("input", (e) => post("/rgb/brightness", { brightness: parseInt(e.target.value, 10) }));

// ---------------------------------------------------------------------------
// Buzzer
// ---------------------------------------------------------------------------
document.getElementById("buzzer-on").addEventListener("click", () => post("/buzzer", { state: "on" }));
document.getElementById("buzzer-off").addEventListener("click", () => post("/buzzer", { state: "off" }));

// ---------------------------------------------------------------------------
// Demos
// ---------------------------------------------------------------------------
for (const btn of document.querySelectorAll("button.demo")) {
    btn.addEventListener("click", () => {
        document.querySelectorAll("button.demo").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        post("/demo", { mode: btn.dataset.demo });
    });
}

document.getElementById("calibrate").addEventListener("click", async () => {
    document.getElementById("calib-result").textContent = " Calibrating…";
    try {
        const data = await post("/calibrate");
        document.getElementById("calib-result").textContent = ` Done (min=${data.min}, max=${data.max})`;
    } catch (e) {
        document.getElementById("calib-result").textContent = " Failed";
    }
});

// ---------------------------------------------------------------------------
// Telemetry
// ---------------------------------------------------------------------------
const connectionBadge = document.getElementById("connection");
const statusEl = document.getElementById("status");

function updateBars(values) {
    const chart = document.getElementById("line-bars");
    chart.innerHTML = "";
    for (const v of values) {
        const bar = document.createElement("div");
        bar.className = "bar";
        bar.style.height = `${Math.min(100, Math.max(0, v / 10))}%`;
        chart.appendChild(bar);
    }
}

async function updateCameraInfo() {
    try {
        const info = await fetch(API + "/camera/info").then(r => r.json());
        const el = document.getElementById("camera-info");
        el.textContent = `Source: ${info.source} (${info.width}x${info.height})`;
    } catch (err) {
        document.getElementById("camera-info").textContent = "Camera info unavailable";
    }
}
updateCameraInfo();

async function pollTelemetry() {
    try {
        const data = await fetch(API + "/telemetry").then(r => r.json());
        connectionBadge.textContent = "connected";
        connectionBadge.className = "badge ok";

        document.getElementById("dist").textContent = data.distance?.toFixed ? data.distance.toFixed(2) : data.distance;
        document.getElementById("ir-l").classList.toggle("on", data.ir_obstacle.left);
        document.getElementById("ir-r").classList.toggle("on", data.ir_obstacle.right);
        document.getElementById("line-pos").textContent = data.tr_sensor.position;
        updateBars(data.tr_sensor.values);
        document.getElementById("ir-key").textContent = data.ir_remote.name || "--";
        document.getElementById("current-demo").textContent = data.demo;
        speedInput.value = data.motor_speed;
        speedVal.textContent = data.motor_speed;

        statusEl.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
        connectionBadge.textContent = "disconnected";
        connectionBadge.className = "badge err";
        console.error(err);
    }
}

setInterval(pollTelemetry, 250);
pollTelemetry();
