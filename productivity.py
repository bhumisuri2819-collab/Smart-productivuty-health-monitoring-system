"""
productivity.py - Focus, distraction, and activity classification.
Uses face landmarks + Windows keyboard/mouse idle detection.
"""

import time
from collections import deque

import numpy as np

from utils import get_idle_seconds_windows, clamp

PRODUCTIVE = "productive"
ENTERTAINMENT = "entertainment"
AWAY = "away"
DISTRACTED = "distracted"


class ProductivityTracker:
    """Estimates focus and productive vs entertainment time."""

    def __init__(self):
        self.productivity_score = 70.0
        self.focus_status = "Initializing"
        self.focus_seconds = 0.0
        self.entertainment_seconds = 0.0
        self.away_seconds = 0.0
        self.distracted_seconds = 0.0
        self._last_category = PRODUCTIVE
        self._emotion_label = "Neutral"
        self._stress_level = 0.0
        self._wellness_score = 75.0
        self._face_distance_ratio = 0.0
        self.attention_history = deque(maxlen=30)

    def process(self, face_landmarks, frame_shape, keyboard_active=True):
        """Classify activity from face landmarks (shared with fatigue detector)."""
        idle_sec = get_idle_seconds_windows()
        dt = 1.0 / 30.0

        if face_landmarks is None:
            self._update_time(AWAY, dt)
            self.focus_status = "Away"
            self.productivity_score = max(0, self.productivity_score - 0.05)
            return self._metrics(idle_sec)

        nose = face_landmarks[1]
        left_eye = face_landmarks[33]
        right_eye = face_landmarks[263]

        eye_mid_x = (left_eye.x + right_eye.x) / 2
        offset = abs(nose.x - eye_mid_x)
        self.attention_history.append(offset)
        avg_offset = np.mean(self.attention_history)

        ys = [face_landmarks[i].y for i in [10, 152, 234, 454]]
        self._face_distance_ratio = max(ys) - min(ys)

        looking_at_screen = avg_offset < 0.04

        if idle_sec > 120:
            category = AWAY
            self.focus_status = "Away (idle)"
        elif idle_sec > 45 and not keyboard_active:
            category = ENTERTAINMENT
            self.focus_status = "Idle / Entertainment"
        elif not looking_at_screen:
            category = DISTRACTED
            self.focus_status = "Distracted"
        elif keyboard_active and looking_at_screen:
            category = PRODUCTIVE
            self.focus_status = "Focused"
        else:
            category = ENTERTAINMENT
            self.focus_status = "Low activity"

        self._update_time(category, dt)
        self._last_category = category

        if category == PRODUCTIVE:
            self.productivity_score = clamp(self.productivity_score + 0.08)
        elif category == DISTRACTED:
            self.productivity_score = clamp(self.productivity_score - 0.15)
        elif category == ENTERTAINMENT:
            self.productivity_score = clamp(self.productivity_score - 0.05)
        else:
            self.productivity_score = clamp(self.productivity_score - 0.1)

        self._estimate_wellness()
        return self._metrics(idle_sec)

    def _update_time(self, category, dt):
        if category == PRODUCTIVE:
            self.focus_seconds += dt
        elif category == ENTERTAINMENT:
            self.entertainment_seconds += dt
        elif category == AWAY:
            self.away_seconds += dt
        else:
            self.distracted_seconds += dt

    def _estimate_wellness(self):
        if len(self.attention_history) < 5:
            return
        var = float(np.std(self.attention_history))
        self._stress_level = clamp(var * 800)
        self._wellness_score = clamp(
            (self.productivity_score * 0.6) + (100 - self._stress_level) * 0.4
        )
        if self._stress_level > 60:
            self._emotion_label = "Stressed"
        elif self.productivity_score > 70:
            self._emotion_label = "Focused"
        else:
            self._emotion_label = "Neutral"

    def _metrics(self, idle_sec):
        total = (
            self.focus_seconds
            + self.entertainment_seconds
            + self.away_seconds
            + self.distracted_seconds
            + 1e-6
        )
        return {
            "productivity_score": round(self.productivity_score, 1),
            "focus_status": self.focus_status,
            "focus_seconds": self.focus_seconds,
            "entertainment_seconds": self.entertainment_seconds,
            "away_seconds": self.away_seconds,
            "distracted_seconds": self.distracted_seconds,
            "focus_pct": round(100 * self.focus_seconds / total, 1),
            "idle_seconds": idle_sec,
            "category": self._last_category,
            "emotion": self._emotion_label,
            "stress_level": round(self._stress_level, 1),
            "wellness_score": round(self._wellness_score, 1),
            "face_distance_ratio": round(self._face_distance_ratio, 3),
        }

    def close(self):
        pass
