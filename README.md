## To open the images on PC use in the terminal not the ssh:
scp pi@192.168.1.xxx:~/motion_snapshots/*.jpg .

## To delete older files on the sd:
find ~/motion_snapshots/ -name "*.jpg" -mtime +7 -print -delete

## To open the python script use:
nano stream.py

## Delete Chronologically
Set this up to run automatically so you never have to think about it (e.g. auto-delete anything older than 7 days, once a day):


crontab -e

If it asks which editor, pick nano (usually option 1). Add this line at the bottom:

0 3 * * * find /home/pi/motion_snapshots/ -name "*.jpg" -mtime +7 -delete

Save and exit (Ctrl+O, Enter, Ctrl+X). This runs every day at 3 AM and clears anything older than a week, so the SD card never fills up unattended.

Want the automatic cleanup set up the same way on your other three Pis too, or just deal with test for now?

## If a sd card change is needed first the host needs to be updated. This example uses the piCam,  use: 
ssh-keygen -R piCam.local

---
---
# Raspberry Pi Zero 2 W Camera Streaming Setup

A guide for setting up a Raspberry Pi Zero 2 W (or similar) with a CSI camera as a live MJPEG streaming server with toggleable motion detection, viewable locally and remotely via Tailscale.

This guide assumes you're adding a **new** camera Pi and already have `stream.py` in this repo — no need to recreate it from scratch, just copy it over.

---

## Requirements

- Raspberry Pi Zero 2 W (or any Pi with a CSI camera port)
- A compatible CSI camera module (tested with OV5647-based modules, e.g. official Camera Module v1 or Joy-IT clones)
- MicroSD card (8GB+)
- A computer to flash the SD card and SSH in from
- Raspberry Pi Imager (https://www.raspberrypi.com/software/)

---

## 1. Flash the SD card

1. Open **Raspberry Pi Imager** on your computer.
2. **Device:** select your Pi model (e.g. Raspberry Pi Zero 2 W).
3. **OS:** choose Raspberry Pi OS Lite (32-bit or 64-bit both work).
4. Before writing, click the **gear icon (⚙)** to open OS customization:
   - **Set hostname** — pick something unique per camera (e.g. `piCam3`) so you can tell devices apart on your network.
   - **Enable SSH** — check "Enable SSH", choose "Use password authentication".
   - **Set username and password**.
   - **Configure WiFi** — enter your SSID and password so it connects on first boot.
   - Save.
5. Click **Write**, confirm, and let it finish writing and verifying.

---

## 2. First boot and connect

1. Insert the SD card into the Pi, connect the camera ribbon cable (check orientation — the blue side of the cable typically faces away from the camera board, and fully seated on both ends), then power it on.
2. Give it 1–2 minutes for first boot.
3. SSH in from your computer:
   ```bash
   ssh <username>@<hostname>.local
   ```
   Or find the IP via your router's device list if `.local` resolution doesn't work.

---

## 3. Update the system

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Reconnect via SSH after it reboots.

---

## 4. Confirm the camera is detected

```bash
rpicam-hello --list-cameras
```

You should see your sensor listed (e.g. `ov5647`) along with its supported resolution modes. If nothing shows up, check the ribbon cable seating and orientation before continuing.

---

## 5. Install dependencies

```bash
sudo apt install -y python3-picamera2 --no-install-recommends
pip install numpy --break-system-packages
```

---

## 6. Set up the streaming script

1. Create the snapshots folder (used for motion-triggered captures):
   ```bash
   mkdir -p ~/motion_snapshots
   ```
2. Copy `stream.py` from this repo onto the Pi (e.g. via `scp` from your computer):
   ```bash
   scp stream.py <username>@<pi-ip-or-hostname>.local:~/stream.py
   ```
3. Confirm your username matches the path used inside `stream.py` (it defaults to `/home/pi/...`):
   ```bash
   whoami
   ```
   If it's not `pi`, edit the `fname` line inside `stream.py`'s `motion_detector()` function to match your actual home directory.
4. **Set the rotation** to match how the camera is physically mounted, near the top of `stream.py`:
   ```python
   ROTATION_DEG = -90  # 0, 90, 180, or -90
   ```

---

## 7. Test manually before making it a service

```bash
python3 ~/stream.py
```

Find the Pi's local IP if you don't have it:
```bash
hostname -I
```

Open in a browser on another device on the same network:
```
http://<pi-ip>:8090/
```

Confirm:
- Live video shows up with correct orientation
- Motion detection toggle button works
- CPU temp shows and updates

Press `Ctrl+C` in the terminal to stop the test once confirmed.

---

## 8. Set up as a persistent systemd service

```bash
sudo nano /etc/systemd/system/camstream.service
```

Paste in (replace `pi` with your actual username in both `User=` and the `ExecStart` path if different):

```
[Unit]
Description=Pi Camera MJPEG Streaming Server
After=network.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /home/pi/stream.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save and exit (`Ctrl+O`, Enter, `Ctrl+X`), then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now camstream
sudo systemctl status camstream
```

Confirm it shows `active (running)`.

---

## 9. Set up remote access with Tailscale

This lets you view the stream from outside your home network without exposing it publicly (the stream has no built-in authentication, so avoid port-forwarding it directly to the internet).

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Open the printed login URL in a browser and approve the device under your Tailscale account. Install Tailscale on whatever device you'll view the stream from too (phone/laptop), logged into the same account.

Get this Pi's Tailscale IP:
```bash
tailscale ip -4
```

From any device connected to your Tailscale network (on any WiFi or cellular data), open:
```
http://<tailscale-ip>:8090/
```

---

## 10. Reboot test

Confirm everything comes back automatically without manual intervention:

```bash
sudo reboot
```

Wait 30–60 seconds, then load the stream URL again (local or Tailscale) without SSHing in or running anything manually first.

---

## 11. Viewing multiple cameras on one page

Since each Pi runs its own independent stream server, you can view several at once with a simple static HTML page on your own computer/phone (no server needed):

```html
<!DOCTYPE html>
<html>
<head>
    <title>My Cameras</title>
    <style>
        body { background: #222; font-family: sans-serif; text-align: center; }
        .cam { display: inline-block; margin: 10px; }
        img { width: 480px; border: 2px solid #555; }
        h3 { color: #eee; }
    </style>
</head>
<body>
    <div class="cam">
        <h3>Camera 1</h3>
        <img src="http://<tailscale-ip-1>:8090/stream.mjpg" />
    </div>
    <div class="cam">
        <h3>Camera 2</h3>
        <img src="http://<tailscale-ip-2>:8090/stream.mjpg" />
    </div>
    <!-- Add more .cam blocks as needed -->
</body>
</html>
```

Save as an `.html` file and open it directly in a browser. There's no hard software limit on how many cameras you can add — the practical limits are your viewing device's bandwidth (each stream is roughly 1–3 Mbps) and each Pi's own CPU handling its own encoding independently.

---

## Troubleshooting

**Camera not detected (`rpicam-hello --list-cameras` shows nothing):**
- Recheck ribbon cable seating and orientation.
- Confirm `/boot/firmware/config.txt` has `camera_auto_detect=1`.
- For third-party sensors, you may need to set `camera_auto_detect=0` and add an explicit `dtoverlay=<sensor>` line (e.g. `dtoverlay=imx219` for Camera Module 3).

**Service fails to start / crash-loops:**
```bash
sudo systemctl status camstream
sudo journalctl -u camstream -n 30 --no-pager
```
Common causes:
- Python syntax errors from manual edits — verify with `python3 -m py_compile ~/stream.py && echo OK` before restarting the service.
- Mixed tabs/spaces in indentation (`TabError`) — if this happens after copy-pasting edits, run `sed -i 's/\t/    /g' ~/stream.py` to normalize to spaces, then re-check indentation levels manually.
- Missing commas between dictionary/function arguments after editing config blocks.

**Video appears cropped or too small:**
Make sure `stream.py`'s video configuration uses a full-sensor mode (e.g. `main={"size": (1296, 972)}` for OV5647, which is a full-sensor-crop resolution) rather than a size that falls into a cropped mode. The page's responsive JavaScript sizing (via `naturalWidth`/`naturalHeight`) should handle displaying whatever resolution is configured without further CSS changes.

**Checking CPU temperature manually:**
```bash
vcgencmd measure_temp
```
Safe operating range is well under 70°C for sustained use; throttling starts around 80°C.

**Viewing motion snapshots:**
Saved on the Pi under `~/motion_snapshots/`. Pull them to your computer with:
```bash
scp <username>@<pi-ip>:~/motion_snapshots/*.jpg .
```
*** chech server / start server
sudo tailscale serve --bg 8090
tailscale serve status
