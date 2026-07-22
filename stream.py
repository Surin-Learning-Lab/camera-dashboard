import io
import json
import logging
import socketserver
import time
import numpy as np
from datetime import datetime
from http import server
from threading import Condition, Thread

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput

MOTION_THRESHOLD = 8
MOTION_COOLDOWN = 5
ROTATION_DEG = 270

motion_enabled = False
last_snapshot_time = 0

def get_cpu_temp():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None

PAGE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pi Camera</title>
<style>
  :root {{
    --bg: #0f1115;
    --card: #171a21;
    --accent: #3b82f6;
    --good: #22c55e;
    --text: #e5e7eb;
    --muted: #9ca3af;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 24px 16px 48px;
  }}
  h1 {{ font-size: 1.4rem; font-weight: 600; margin: 0 0 20px; }}
  .card {{
    background: var(--card);
    border-radius: 16px;
    padding: 16px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    width: 100%;
    max-width: 640px;
  }}
  .video-wrap {{
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    border-radius: 12px;
    background: #000;
  }}
  #camImg {{ display: block; max-width: none; }}
  .controls {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 16px;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .status-group {{ display: flex; align-items: center; gap: 10px; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--muted); }}
  .dot.on {{ background: var(--good); box-shadow: 0 0 8px var(--good); }}
  button.toggle {{
    border: none;
    padding: 10px 18px;
    border-radius: 999px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    background: var(--accent);
    color: white;
  }}
  button.toggle.off {{ background: #2d3138; color: var(--muted); }}
  .temp-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #1f232b;
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 0.85rem;
    color: var(--muted);
  }}
  .temp-value {{ font-weight: 600; color: var(--text); }}
</style>
</head>
<body>
<h1>Live Camera</h1>
<div class="card">
  <div class="video-wrap" id="videoWrap">
    <img id="camImg" src="stream.mjpg" style="transform: rotate({rotation}deg);" />
  </div>
  <div class="controls">
    <div class="status-group">
      <span class="dot {dotclass}" id="dot"></span>
      <span id="motion-label">Motion detection: {status}</span>
    </div>
    <button class="toggle {btnclass}" id="motion-btn" onclick="toggleMotion()">{btntext}</button>
  </div>
  <div class="controls">
    <span class="temp-badge">CPU Temp: <span class="temp-value" id="temp">--</span>&deg;C</span>
  </div>
</div>
<script>
let motionOn = {motion_js};
const rotation = {rotation};
const img = document.getElementById('camImg');
const wrap = document.getElementById('videoWrap');

function resize() {{
  const nw = img.naturalWidth, nh = img.naturalHeight;
  if (!nw || !nh) return;
  const rotated = Math.abs(rotation % 180) === 90;
  const dispW = rotated ? nh : nw;
  const dispH = rotated ? nw : nh;
  const containerW = wrap.parentElement.clientWidth - 32;
  const scale = containerW / dispW;
  wrap.style.height = Math.round(dispH * scale) + 'px';
  img.style.width = Math.round(nw * scale) + 'px';
  img.style.height = Math.round(nh * scale) + 'px';
}}

function render() {{
  document.getElementById('dot').className = 'dot' + (motionOn ? ' on' : '');
  document.getElementById('motion-label').textContent = 'Motion detection: ' + (motionOn ? 'ON' : 'OFF');
  const btn = document.getElementById('motion-btn');
  btn.textContent = motionOn ? 'Turn Off' : 'Turn On';
  btn.className = 'toggle' + (motionOn ? '' : ' off');
}}

function toggleMotion() {{
  fetch(motionOn ? '/motion/off' : '/motion/on').then(() => {{
    motionOn = !motionOn;
    render();
  }});
}}

function updateTemp() {{
  fetch('/temp').then(r => r.json()).then(d => {{
    document.getElementById('temp').textContent = d.temp !== null ? d.temp : 'N/A';
  }});
}}

img.addEventListener('load', resize);
window.addEventListener('resize', resize);
setInterval(() => {{ if (img.naturalWidth) resize(); }}, 2000);

render();
setInterval(updateTemp, 5000);
updateTemp();
</script>
</body>
</html>
"""

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class StreamingHandler(server.BaseHTTPRequestHandler):
    def _serve_stream(self, out):
        self.send_response(200)
        self.send_header('Age', 0)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
        self.end_headers()
        try:
            while True:
                with out.condition:
                    out.condition.wait()
                    frame = out.frame
                self.wfile.write(b'--FRAME\r\n')
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', len(frame))
                self.end_headers()
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except Exception as e:
            logging.warning('Removed streaming client %s: %s', self.client_address, str(e))

    def do_GET(self):
        global motion_enabled
        if self.path == '/':
            content = PAGE.format(
                status="ON" if motion_enabled else "OFF",
                dotclass="on" if motion_enabled else "",
                btnclass="" if motion_enabled else "off",
                btntext="Turn Off" if motion_enabled else "Turn On",
                motion_js="true" if motion_enabled else "false",
                rotation=ROTATION_DEG,
            ).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/motion/on':
            motion_enabled = True
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"on"}')
        elif self.path == '/motion/off':
            motion_enabled = False
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"off"}')
        elif self.path == '/motion/status':
            content = json.dumps({'motion': motion_enabled}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/temp':
            temp = get_cpu_temp()
            content = json.dumps({'temp': temp}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self._serve_stream(main_output)
        elif self.path == '/thumb.mjpg':
            self._serve_stream(thumb_output)
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def motion_detector():
    global last_snapshot_time
    prev = None
    w, h = 320, 240
    while True:
        if not motion_enabled:
            prev = None
            time.sleep(1)
            continue
        lores = picam2.capture_array("lores")
        gray = lores[:h, :w]
        if prev is not None:
            diff = np.mean(np.abs(gray.astype(int) - prev.astype(int)))
            if diff > MOTION_THRESHOLD:
                now = time.time()
                if now - last_snapshot_time > MOTION_COOLDOWN:
                    last_snapshot_time = now
                    fname = datetime.now().strftime("/home/pi/motion_snapshots/motion_%Y%m%d_%H%M%S.jpg")
                    with main_output.condition:
                        frame = main_output.frame
                    if frame:
                        with open(fname, "wb") as f:
                            f.write(frame)
                        logging.info("Motion detected, saved %s", fname)
        prev = gray
        time.sleep(0.5)

picam2 = Picamera2()
video_config = picam2.create_video_configuration(
    main={"size": (1296, 972)},
    lores={"size": (320, 240), "format": "YUV420"}
)
picam2.configure(video_config)

main_output = StreamingOutput()
thumb_output = StreamingOutput()

picam2.start_recording(MJPEGEncoder(), FileOutput(main_output))
picam2.start_recording(MJPEGEncoder(), FileOutput(thumb_output), name="lores")

Thread(target=motion_detector, daemon=True).start()

try:
    address = ('', 8090)
    server = StreamingServer(address, StreamingHandler)
    server.serve_forever()
finally:
    picam2.stop_recording()
