"""
fatigue.py - Eye fatigue, blink tracking, and drowsiness estimation.
Uses MediaPipe Face Landmarker (Tasks API) for Eye Aspect Ratio (EAR).
"""

import time
from collections import deque

from utils import (
    EAR_BLINK_THRESHOLD,
    EAR_STRAIN_THRESHOLD,
    BLINKS_PER_MIN_LOW,
    BLINKS_PER_MIN_HIGH,
    SESSION_BREAK_MINUTES,
    eye_aspect_ratio,
    LEFT_EYE,
    RIGHT_EYE,
    clamp,
)


class FatigueDetector:
    """Tracks blinks, EAR, fatigue level, and drowsiness."""

    def __init__(self):
        self.blink_count = 0
        self.ear_history = deque(maxlen=90)
        self.blink_timestamps = deque(maxlen=120)
        self._eyes_closed = False
        self._session_start = time.time()
        self.fatigue_level = 0.0
        self.drowsiness_level = 0.0
        self.status_text = "Normal"
        self.last_ear = 0.3

    def process(self, face_landmarks, frame_shape):
        """
        Analyze pre-detected face landmarks.
        Returns dict with metrics or None if no face.
        """
        if face_landmarks is None:
            return None

        h, w = frame_shape[:2]
        left_ear = eye_aspect_ratio(face_landmarks, LEFT_EYE, w, h)
        right_ear = eye_aspect_ratio(face_landmarks, RIGHT_EYE, w, h)
        ear = (left_ear + right_ear) / 2.0
        self.last_ear = ear
        self.ear_history.append(ear)
        now = time.time()

        # Blink detection: EAR drops below threshold then recovers
        if ear < EAR_BLINK_THRESHOLD:
            if not self._eyes_closed:
                self._eyes_closed = True
        else:
            if self._eyes_closed:
                self.blink_count += 1
                self.blink_timestamps.append(now)
            self._eyes_closed = False

        recent = [t for t in self.blink_timestamps if now - t < 60]
        blinks_per_min = len(recent)
        session_min = (now - self._session_start) / 60.0

        fatigue = 0.0
        if ear < EAR_STRAIN_THRESHOLD:
            fatigue += 25
        if blinks_per_min < BLINKS_PER_MIN_LOW:
            fatigue += 30
        if blinks_per_min > BLINKS_PER_MIN_HIGH:
            fatigue += 15
        if session_min > SESSION_BREAK_MINUTES:
            fatigue += min(40, (session_min - SESSION_BREAK_MINUTES) * 2)

        self.fatigue_level = clamp(fatigue)

        low_frames = sum(1 for e in self.ear_history if e < EAR_BLINK_THRESHOLD)
        self.drowsiness_level = clamp(
            (low_frames / max(len(self.ear_history), 1)) * 100
        )

        if self.drowsiness_level > 50:
            self.status_text = "Drowsy"
        elif self.fatigue_level > 60:
            self.status_text = "High Fatigue"
        elif self.fatigue_level > 35:
            self.status_text = "Moderate"
        else:
            self.status_text = "Normal"

        return {
            "ear": ear,
            "blinks_per_min": blinks_per_min,
            "fatigue_level": self.fatigue_level,
            "drowsiness_level": self.drowsiness_level,
            "status": self.status_text,
            "session_minutes": session_min,
        }

    def check_alerts(self, alert_manager):
        if self.fatigue_level > 55:
            alert_manager.push("Take a break - eye strain detected")
        if self.last_ear < EAR_STRAIN_THRESHOLD and not self._eyes_closed:
            alert_manager.push("Blink your eyes", duration=3.0, color=(0, 255, 255))
        if self.fatigue_level > 40:
            alert_manager.push("Look away from screen for 20 seconds", color=(0, 165, 255))

    def close(self):
        pass
