#!/usr/bin/env python3
"""
esp32_xbox_control.py
- Xbox controller analog drive: RT = forward, LT = backward, L stick X = steer
- A button toggles flash
- OpenCV shows MJPEG stream from ESP (fast)
- Sends per-wheel PWM via: /action?go=drive&l=<0-255>&r=<0-255>
- Run with: python esp32_xbox_control.py --ip 192.168.1.50
- Use --calibrate to open an axis/button readout to find mappings
"""

import argparse
import math
import time
import threading
import requests
import cv2
import numpy as np
import pygame

# ----------------------
# Config (change IP)
# ----------------------
DEFAULT_ESP_IP = "192.168.1.50"  # change or pass via --ip
STREAM_PORT = 81

# Default joystick mapping (common Xbox mappings). If these don't match your controller, run with --calibrate.
DEFAULT_AXIS_LT = 2     # Left Trigger (or share axis)
DEFAULT_AXIS_RT = 5     # Right Trigger
DEFAULT_AXIS_LX = 0     # Left stick X
BUTTON_A = 0            # A button index (common)

# control loop params
UPDATE_INTERVAL = 0.05  # seconds between command sends
MAX_PWM = 255

# ----------------------
# Utility functions
# ----------------------
def clamp(x, a, b):
    return max(a, min(b, x))

def norm_trigger_value(raw):
    """
    Normalize a typical trigger axis reading to 0..1.
    Many controllers report -1 (released) .. +1 (pressed) or 0..1.
    We handle both heuristically.
    """
    if raw >= -1.0 and raw <= 1.0:
        # If range seems centered near -1..1
        if raw < -0.5:
            # convert -1..1 -> 0..1
            return (raw + 1.0) / 2.0
        else:
            # perhaps already 0..1
            return clamp(raw, 0.0, 1.0)
    return 0.0

# ----------------------
# Networking
# ----------------------
class ESPClient:
    def __init__(self, ip):
        self.base = f"http://{ip}"
        self.session = requests.Session()
        self.timeout = 1.5

    def drive(self, left_pwm, right_pwm):
        # left_pwm and right_pwm in 0..255
        url = f"{self.base}/action?go=drive&l={int(left_pwm)}&r={int(right_pwm)}"
        try:
            r = self.session.get(url, timeout=self.timeout)
            return r.status_code == 200
        except Exception as e:
            # optionally print once or debug
            # print("drive request error", e)
            return False

    def toggle_flash(self):
        url = f"{self.base}/action?go=flash"
        try:
            r = self.session.get(url, timeout=self.timeout)
            return r.status_code == 200
        except:
            return False

# ----------------------
# Joystick control thread
# ----------------------
class XboxController:
    def __init__(self, esp, axis_lt=DEFAULT_AXIS_LT, axis_rt=DEFAULT_AXIS_RT, axis_lx=DEFAULT_AXIS_LX, btn_a=BUTTON_A):
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("No joystick detected. Plug in Xbox controller and try again.")
        self.j = pygame.joystick.Joystick(0)
        self.j.init()
        print(f"Using joystick: {self.j.get_name()}")
        self.esp = esp
        self.axis_lt = axis_lt
        self.axis_rt = axis_rt
        self.axis_lx = axis_lx
        self.btn_a = btn_a
        self.running = True
        self.last_flash = False
        self.last_sent = (None, None)
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def read_axes(self):
        pygame.event.pump()
        # safe reads
        def axis(i):
            try:
                return self.j.get_axis(i)
            except:
                return 0.0
        lt_raw = axis(self.axis_lt)
        rt_raw = axis(self.axis_rt)
        lx_raw = axis(self.axis_lx)
        # Some controllers map triggers to one axis where LT/RT are -1..1 combined.
        return lt_raw, rt_raw, lx_raw

    def read_buttons(self):
        pygame.event.pump()
        try:
            return self.j.get_button(self.btn_a)
        except:
            return 0

    def loop(self):
        last_time = 0
        while self.running:
            now = time.time()
            if now - last_time < UPDATE_INTERVAL:
                time.sleep(0.005)
                continue
            last_time = now

            lt_raw, rt_raw, lx_raw = self.read_axes()
            a_pressed = self.read_buttons()

            # normalize triggers (0..1)
            lt = norm_trigger_value(lt_raw)
            rt = norm_trigger_value(rt_raw)

            # compute forward/backward base = RT - LT (range -1..1)
            drive_val = rt - lt
            # small deadzone
            if abs(drive_val) < 0.05:
                drive_val = 0.0

            # left stick X (-1 left .. +1 right). Use deadzone
            steer = lx_raw
            if abs(steer) < 0.07:
                steer = 0.0
            steer = clamp(steer, -1.0, 1.0)

            # Mix drive and steer into left/right wheel values.
            # We use simple mixing:
            # left = drive * (1 - steer)
            # right = drive * (1 + steer)
            # If steer is left (-1), left = drive * 2, right = 0  (we'll scale after)
            left = drive_val * (1 - steer)
            right = drive_val * (1 + steer)

            # Normalize so max magnitude <= 1
            m = max(abs(left), abs(right), 1.0)
            left /= m
            right /= m

            # Map -1..1 to 0..255 per-wheel forward-only assumption:
            # We'll map negative values to 0 (no reverse in this simple drive command).
            # If you extend firmware to accept signed values, you can map sign to direction.
            left_pwm = int(clamp(left, 0.0, 1.0) * MAX_PWM)
            right_pwm = int(clamp(right, 0.0, 1.0) * MAX_PWM)

            # Send only if different enough
            if (left_pwm, right_pwm) != self.last_sent:
                ok = self.esp.drive(left_pwm, right_pwm)
                # you can optionally handle ok==False
                self.last_sent = (left_pwm, right_pwm)

            # Flash toggle on A button press edge
            if a_pressed and (not self.last_flash):
                self.esp.toggle_flash()
            self.last_flash = bool(a_pressed)

    def stop(self):
        self.running = False
        self.thread.join(timeout=0.5)
        # send stop command (both zero)
        try:
            self.esp.drive(0, 0)
        except:
            pass

# ----------------------
# OpenCV stream thread
# ----------------------
def stream_thread(esp_ip):
    stream_url = f"http://{esp_ip}:{STREAM_PORT}/stream"
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        print("Failed to open stream. Check URL:", stream_url)
        return
    cv2.namedWindow("ESP32-CAM Preview", cv2.WINDOW_NORMAL)
    while True:
        ret, frame = cap.read()
        if not ret:
            # brief pause and retry
            time.sleep(0.1)
            continue
        # rotate 180 if your camera is upside down (the HTML rotated it in the web UI).
        # The camera in your sketch rotated via CSS; stream likely is already upside down,
        # If needed uncomment the next line:
        # frame = cv2.rotate(frame, cv2.ROTATE_180)
        cv2.imshow("ESP32-CAM Preview", frame)
        # waitKey(1) to keep window responsive; exit on 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()

# ----------------------
# Calibration helper
# ----------------------
def calibration_mode():
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No joystick found for calibration.")
        return
    j = pygame.joystick.Joystick(0)
    j.init()
    print("Joystick:", j.get_name())
    print("Move triggers and sticks — press Ctrl-C to quit calibration.")
    try:
        while True:
            pygame.event.pump()
            axes = [j.get_axis(i) for i in range(j.get_numaxes())]
            buttons = [j.get_button(i) for i in range(j.get_numbuttons())]
            print("Axes:", [round(a,3) for a in axes])
            print("Buttons:", buttons)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Calibration done. Note axis indexes above and pass via options if needed.")

# ----------------------
# Main
# ----------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", type=str, default=DEFAULT_ESP_IP, help="ESP32 IP")
    parser.add_argument("--axis-lt", type=int, default=DEFAULT_AXIS_LT)
    parser.add_argument("--axis-rt", type=int, default=DEFAULT_AXIS_RT)
    parser.add_argument("--axis-lx", type=int, default=DEFAULT_AXIS_LX)
    parser.add_argument("--btn-a", type=int, default=BUTTON_A)
    parser.add_argument("--calibrate", action="store_true", help="Run joystick calibration readout")
    args = parser.parse_args()

    if args.calibrate:
        calibration_mode()
        return

    esp = ESPClient(args.ip)
    # start stream
    st = threading.Thread(target=stream_thread, args=(args.ip,), daemon=True)
    st.start()

    try:
        ctrl = XboxController(esp, axis_lt=args.axis_lt, axis_rt=args.axis_rt, axis_lx=args.axis_lx, btn_a=args.btn_a)
    except Exception as e:
        print("Controller init error:", e)
        return

    print("Running. Close the preview window or press Ctrl+C to stop (or 'q' in the preview).")
    try:
        while True:
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        ctrl.stop()

if __name__ == "__main__":
    main()
