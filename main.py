"""
main.py - Entry point: live webcam monitoring with health analytics overlay.
Run: python main.py
Press Q in the camera window to quit.
"""

import sys
import time
import json
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from utils import (
    format_duration,
    frame_brightness,
    LOW_LIGHT_THRESHOLD,
    POMODORO_WORK_SEC,
    POMODORO_BREAK_SEC,
    WATER_REMINDER_MIN,
    STRETCH_REMINDER_MIN,
    SESSION_BREAK_MINUTES,
    get_idle_seconds_windows,
    BASE_DIR,
)
from fatigue import FatigueDetector
from posture import PostureDetector
from productivity import ProductivityTracker
from alerts import AlertManager
from analytics import AnalyticsLogger, generate_daily_report
from dashboard import Dashboard
from vision_models import get_vision_engine, close_vision_engine

# ---------------------------------------------------------------------------
# Shared session state (read by dashboard thread)
# ---------------------------------------------------------------------------
SESSION = {
    "productivity_score": 70,
    "fatigue_level": 0,
    "drowsiness_level": 0,
    "posture_status": "Good",
    "posture_score": 100,
    "blink_count": 0,
    "focus_seconds": 0,
    "entertainment_seconds": 0,
    "session_seconds": 0,
    "wellness_score": 75,
    "break_count": 0,
    "streak_days": 1,
    "emotion": "Neutral",
}


def load_streak():
    """Load consecutive-day usage streak from data/streak.json."""
    path = BASE_DIR / "data" / "streak.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            last = data.get("last_date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if last == today:
                return data.get("days", 1)
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            if last == yesterday:
                return data.get("days", 0) + 1
        return 1
    except Exception:
        return 1


def save_streak(days):
    path = BASE_DIR / "data" / "streak.json"
    path.write_text(
        json.dumps(
            {"last_date": datetime.now().strftime("%Y-%m-%d"), "days": days},
            indent=2,
        ),
        encoding="utf-8",
    )


def get_stats():
    return dict(SESSION)


# ---------------------------------------------------------------------------
# Draw overlay on camera frame
# ---------------------------------------------------------------------------
def draw_overlay(frame, lines, alerts, bar_y=0):
    """Draw semi-transparent panel and alert banners."""
    h, w = frame.shape[:2]
    panel_h = 28 * len(lines) + 20
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, panel_h), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    y = 22
    for text, color in lines:
        cv2.putText(
            frame, text, (10, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
        y += 24

    # Active alerts at bottom
    alert_y = h - 30
    for msg, _, color in alerts[-3:]:
        cv2.rectangle(frame, (0, alert_y - 22), (w, alert_y + 8), color, -1)
        cv2.putText(
            frame, msg, (10, alert_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA,
        )
        alert_y -= 32

    return frame


# ---------------------------------------------------------------------------
# Smart timers: Pomodoro, water, stretch, break countdown
# ---------------------------------------------------------------------------
class SmartTimers:
    def __init__(self):
        self.session_start = time.time()
        self.pomodoro_phase = "work"
        self.pomodoro_left = POMODORO_WORK_SEC
        self.water_next = WATER_REMINDER_MIN * 60
        self.stretch_next = STRETCH_REMINDER_MIN * 60
        self.break_countdown = SESSION_BREAK_MINUTES * 60
        self.last_water = time.time()
        self.last_stretch = time.time()

    def tick(self, alert_mgr, fatigue_level):
        now = time.time()
        elapsed = now - self.session_start

        # Break countdown (resets on long session recommendation)
        self.break_countdown = max(0, SESSION_BREAK_MINUTES * 60 - (elapsed % (SESSION_BREAK_MINUTES * 60 + 1)))

        # Pomodoro
        self.pomodoro_left -= 1 / 30.0
        if self.pomodoro_left <= 0:
            if self.pomodoro_phase == "work":
                self.pomodoro_phase = "break"
                self.pomodoro_left = POMODORO_BREAK_SEC
                alert_mgr.push("Pomodoro break - rest 5 minutes", color=(255, 128, 0))
            else:
                self.pomodoro_phase = "work"
                self.pomodoro_left = POMODORO_WORK_SEC
                alert_mgr.push("Pomodoro work session started")

        # Water reminder
        if now - self.last_water > WATER_REMINDER_MIN * 60:
            alert_mgr.push("Drink water - stay hydrated", color=(255, 200, 0))
            self.last_water = now

        # Stretch reminder
        if now - self.last_stretch > STRETCH_REMINDER_MIN * 60:
            alert_mgr.push("Stretch reminder - stand and stretch", color=(200, 100, 255))
            self.last_stretch = now

        # Smart break from fatigue
        if fatigue_level > 65 and int(elapsed) % 300 < 2:
            alert_mgr.push("Smart break recommended - high fatigue")

        return {
            "break_countdown": format_duration(self.break_countdown),
            "pomodoro": f"{self.pomodoro_phase}: {format_duration(self.pomodoro_left)}",
        }


# ---------------------------------------------------------------------------
# Main camera loop
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  Smart Productivity & Health Monitoring System")
    print("  Press Q in the camera window to quit.")
    print("=" * 60)

    # Webcam with error handling
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam. Check camera permissions and drivers.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    print("Loading AI models (first run downloads ~10MB)...")
    try:
        vision = get_vision_engine()
    except Exception as e:
        print(f"ERROR: Could not load MediaPipe models: {e}")
        sys.exit(1)

    fatigue_det = FatigueDetector()
    posture_det = PostureDetector()
    prod_track = ProductivityTracker()
    alert_mgr = AlertManager()
    logger = AnalyticsLogger()
    timers = SmartTimers()

    streak = load_streak()
    save_streak(streak)
    SESSION["streak_days"] = streak

    # Dashboard in background thread
    dash = Dashboard(get_stats)
    dash.start()

    session_start = time.time()
    frame_idx = 0
    fps_frames = 0
    log_interval = 30  # Log CSV every N seconds
    last_log = time.time()
    fps_time = time.time()
    fps = 0.0
    process_every = 2  # Run heavy ML every N frames for FPS

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("WARNING: Frame grab failed, retrying...")
                time.sleep(0.1)
                continue

            frame = cv2.flip(frame, 1)
            frame_idx += 1
            fps_frames += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # FPS calculation
            if time.time() - fps_time >= 1.0:
                fps = fps_frames / max(time.time() - fps_time, 0.001)
                fps_frames = 0
                fps_time = time.time()

            run_ml = (frame_idx % process_every == 0)

            fatigue_data = None
            posture_data = None
            prod_data = None
            face_h_ratio = None

            if run_ml:
                face_lm, pose_lm = vision.process_frame(rgb)

                fatigue_data = fatigue_det.process(face_lm, frame.shape)
                if fatigue_data:
                    fatigue_det.check_alerts(alert_mgr)

                prod_data = prod_track.process(
                    face_lm,
                    frame.shape,
                    keyboard_active=get_idle_seconds_windows() < 15,
                )
                face_h_ratio = prod_data.get("face_distance_ratio") if prod_data else None

                posture_data = posture_det.process(pose_lm, frame.shape, face_h_ratio)
                posture_det.check_alerts(alert_mgr)

            timer_info = timers.tick(alert_mgr, fatigue_det.fatigue_level)

            # Ambient lighting warning
            brightness = frame_brightness(frame)
            if brightness < LOW_LIGHT_THRESHOLD:
                alert_mgr.push("Low lighting - improve room lighting", duration=2.0)

            # Session duration
            session_sec = time.time() - session_start

            # Update shared SESSION for dashboard
            SESSION["session_seconds"] = session_sec
            SESSION["blink_count"] = fatigue_det.blink_count
            SESSION["fatigue_level"] = fatigue_det.fatigue_level
            SESSION["drowsiness_level"] = fatigue_det.drowsiness_level
            SESSION["posture_status"] = posture_det.status
            SESSION["posture_score"] = posture_det.posture_score
            if prod_data:
                SESSION["productivity_score"] = prod_data["productivity_score"]
                SESSION["focus_seconds"] = prod_data["focus_seconds"]
                SESSION["entertainment_seconds"] = prod_data["entertainment_seconds"]
                SESSION["wellness_score"] = prod_data["wellness_score"]
                SESSION["emotion"] = prod_data.get("emotion", "Neutral")
            SESSION["break_count"] = logger.break_count

            # Periodic CSV log
            if time.time() - last_log >= log_interval:
                logger.log_row({
                    "blink_count": fatigue_det.blink_count,
                    "fatigue_level": fatigue_det.fatigue_level,
                    "posture_status": posture_det.status,
                    "productivity_score": SESSION["productivity_score"],
                    "focus_seconds": SESSION["focus_seconds"],
                    "entertainment_seconds": SESSION["entertainment_seconds"],
                    "break_count": logger.break_count,
                    "session_seconds": session_sec,
                    "drowsiness_level": fatigue_det.drowsiness_level,
                    "posture_score": posture_det.posture_score,
                    "wellness_score": SESSION["wellness_score"],
                })
                last_log = time.time()

            # Build overlay lines
            now_str = datetime.now().strftime("%H:%M:%S")
            lines = [
                (f"Time: {now_str}  |  FPS: {fps:.1f}", (200, 200, 200)),
                (f"Session: {format_duration(session_sec)}  |  Daily Active: {format_duration(session_sec)}", (180, 220, 255)),
                (f"Eye Fatigue: {fatigue_det.status_text} ({fatigue_det.fatigue_level:.0f}%)  |  Blinks: {fatigue_det.blink_count}", (100, 255, 200)),
                (f"Drowsiness: {fatigue_det.drowsiness_level:.0f}%  |  EAR: {fatigue_det.last_ear:.2f}", (150, 200, 255)),
                (f"Posture: {posture_det.status} (score {posture_det.posture_score:.0f})  Bad time: {format_duration(posture_det.bad_posture_seconds)}", (255, 200, 100)),
                (f"Break in: {timer_info['break_countdown']}  |  {timer_info['pomodoro']}", (255, 180, 120)),
                (f"Productivity: {SESSION['productivity_score']:.0f}  |  Focus: {prod_track.focus_status}", (120, 255, 120)),
                (f"Water reminder active  |  Streak: {streak} day(s)", (200, 180, 255)),
                (f"Wellness: {SESSION['wellness_score']:.0f}  Stress: {prod_track._stress_level:.0f}  Emotion: {prod_track._emotion_label}", (255, 150, 200)),
            ]
            if prod_data:
                lines.append(
                    (f"Focus {format_duration(prod_data['focus_seconds'])}  |  Entertainment {format_duration(prod_data['entertainment_seconds'])}", (180, 255, 180))
                )

            alerts = alert_mgr.get_active()
            frame = draw_overlay(frame, lines, alerts)

            cv2.imshow("Smart Health Monitor - Press Q to quit", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("b"), ord("B")):
                logger.increment_break()
                alert_mgr.push("Break logged - good job!", color=(0, 200, 0))

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        # Cleanup — prevent memory leaks
        cap.release()
        cv2.destroyAllWindows()
        fatigue_det.close()
        posture_det.close()
        prod_track.close()
        close_vision_engine()

        # Auto-export report on exit
        try:
            paths = generate_daily_report(get_stats())
            print(f"Daily report saved: {paths['pdf']}")
        except Exception as e:
            print(f"Report generation skipped: {e}")

        print("Session ended. Stay healthy!")


if __name__ == "__main__":
    main()
