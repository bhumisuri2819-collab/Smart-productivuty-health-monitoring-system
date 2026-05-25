"""
utils.py - Shared helpers, constants, paths, and Windows idle detection.
Used by every module in Smart Health Monitor.
"""

import sys
import ctypes
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Project paths (auto-created on import)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
GRAPHS_DIR = BASE_DIR / "graphs"
REPORTS_DIR = BASE_DIR / "reports"
MODELS_DIR = BASE_DIR / "models"

for folder in (DATA_DIR, GRAPHS_DIR, REPORTS_DIR, MODELS_DIR):
    folder.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Detection thresholds (tune in utils.py for your desk/camera)
# ---------------------------------------------------------------------------
EAR_BLINK_THRESHOLD = 0.21
EAR_STRAIN_THRESHOLD = 0.18
BLINKS_PER_MIN_LOW = 8
BLINKS_PER_MIN_HIGH = 30
SESSION_BREAK_MINUTES = 45
POSTURE_NECK_ANGLE_BAD = 25
POSTURE_SLOUCH_RATIO = 0.12
FACE_TOO_CLOSE_RATIO = 0.35
LOW_LIGHT_THRESHOLD = 60
POMODORO_WORK_SEC = 25 * 60
POMODORO_BREAK_SEC = 5 * 60
WATER_REMINDER_MIN = 30
STRETCH_REMINDER_MIN = 60

# Face landmark indices for Eye Aspect Ratio (EAR)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]


def eye_aspect_ratio(landmarks, eye_indices, w, h):
    """Eye Aspect Ratio from face landmarks. Lower = eyes more closed."""
    try:
        pts = np.array(
            [(landmarks[i].x * w, landmarks[i].y * h) for i in eye_indices],
            dtype=np.float32,
        )
        v1 = np.linalg.norm(pts[1] - pts[5])
        v2 = np.linalg.norm(pts[2] - pts[4])
        h_dist = np.linalg.norm(pts[0] - pts[3])
        if h_dist < 1e-6:
            return 0.3
        return (v1 + v2) / (2.0 * h_dist)
    except (IndexError, AttributeError, TypeError):
        return 0.3


def angle_between_points(a, b, c):
    """Angle at point b (degrees) for posture neck check."""
    a, b, c = np.array(a), np.array(b), np.array(c)
    ba, bc = a - b, c - b
    cosine = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    cosine = np.clip(cosine, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def format_duration(seconds):
    """Seconds -> HH:MM:SS."""
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def today_csv_path():
    """Daily log: data/log_YYYY-MM-DD.csv"""
    return DATA_DIR / f"log_{datetime.now().strftime('%Y-%m-%d')}.csv"


def get_idle_seconds_windows():
    """Seconds since last keyboard/mouse input (Windows ctypes, no extra libs)."""
    if sys.platform != "win32":
        return 0.0
    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
    except Exception:
        return 0.0


def frame_brightness(frame):
    """Mean brightness 0-255 for low-light warning."""
    try:
        import cv2
        if len(frame.shape) == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(np.mean(frame))
    except Exception:
        return 128.0


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def open_folder(path):
    """Open folder in Windows Explorer (or xdg-open on Linux)."""
    import os
    import subprocess

    p = str(path)
    if sys.platform == "win32":
        os.startfile(p)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])
