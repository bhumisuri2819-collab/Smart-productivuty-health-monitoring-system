"""
alerts.py - On-screen alert queue + optional sound (Windows winsound).
Toggle SOUND_ENABLED = False to disable beeps.
"""

import sys
import time
import threading

# ---------------------------------------------------------------------------
# Sound settings
# ---------------------------------------------------------------------------
SOUND_ENABLED = True
_SOUND_COOLDOWN = 8.0
_last_sound_time = 0.0


def _play_beep(freq=800, duration_ms=200):
    """Short beep on Windows; terminal bell elsewhere."""
    global _last_sound_time
    if not SOUND_ENABLED:
        return
    now = time.time()
    if now - _last_sound_time < _SOUND_COOLDOWN:
        return
    _last_sound_time = now
    try:
        if sys.platform == "win32":
            import winsound
            winsound.Beep(freq, duration_ms)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


def play_break_alert():
    _play_beep(600, 300)


def play_blink_alert():
    _play_beep(900, 150)


def play_posture_alert():
    _play_beep(500, 400)


def play_water_alert():
    _play_beep(700, 250)


def play_warning_alert():
    _play_beep(400, 500)


def set_sound_enabled(enabled: bool):
    global SOUND_ENABLED
    SOUND_ENABLED = bool(enabled)


# ---------------------------------------------------------------------------
# Overlay alert manager (thread-safe)
# ---------------------------------------------------------------------------
class AlertManager:
    """Queue of timed messages shown on the camera overlay."""

    def __init__(self):
        self._messages = []
        self._lock = threading.Lock()
        self.total_alerts = 0

    def push(self, text, duration=4.0, color=(0, 0, 255), play_sound=True):
        """Add alert. color is BGR for OpenCV."""
        expire = time.time() + duration
        with self._lock:
            self._messages.append((text, expire, color))
            self.total_alerts += 1

        if not play_sound:
            return
        lower = text.lower()
        if "blink" in lower:
            threading.Thread(target=play_blink_alert, daemon=True).start()
        elif "water" in lower or "hydrat" in lower:
            threading.Thread(target=play_water_alert, daemon=True).start()
        elif "posture" in lower or "straight" in lower or "slouch" in lower:
            threading.Thread(target=play_posture_alert, daemon=True).start()
        elif "break" in lower or "stretch" in lower or "pomodoro" in lower:
            threading.Thread(target=play_break_alert, daemon=True).start()
        elif "light" in lower or "drowsy" in lower:
            threading.Thread(target=play_warning_alert, daemon=True).start()

    def get_active(self):
        now = time.time()
        with self._lock:
            self._messages = [(t, e, c) for t, e, c in self._messages if e > now]
            return list(self._messages)

    def clear(self):
        with self._lock:
            self._messages.clear()
