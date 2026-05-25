"""
posture.py - Posture monitoring via MediaPipe Pose Landmarker.
Detects neck bend, slouching, and head too close to camera.
"""

import time

from utils import (
    POSTURE_NECK_ANGLE_BAD,
    POSTURE_SLOUCH_RATIO,
    FACE_TOO_CLOSE_RATIO,
    angle_between_points,
    clamp,
)

# Pose landmark indices (33-point model)
NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24


class PostureDetector:
    """Evaluates posture from body landmarks."""

    def __init__(self):
        self.status = "Good"
        self.bad_posture_seconds = 0.0
        self._bad_since = None
        self.posture_score = 100.0
        self.issues = []

    def process(self, pose_landmarks, frame_shape, face_bbox_height=None):
        """Analyze pose landmarks from VisionEngine."""
        h, w = frame_shape[:2]
        self.issues = []

        if pose_landmarks is None:
            self.status = "Unknown"
            return {"status": self.status, "score": self.posture_score}

        def pt(idx):
            p = pose_landmarks[idx]
            vis = getattr(p, "visibility", 1.0) or 1.0
            return (p.x * w, p.y * h, vis)

        nose = pt(NOSE)
        left_sh = pt(LEFT_SHOULDER)
        right_sh = pt(RIGHT_SHOULDER)
        left_hip = pt(LEFT_HIP)
        right_hip = pt(RIGHT_HIP)

        vis_ok = min(nose[2], left_sh[2], right_sh[2]) > 0.5
        if not vis_ok:
            self.status = "Unknown"
            return {"status": self.status, "score": self.posture_score}

        shoulder_mid = (
            (left_sh[0] + right_sh[0]) / 2,
            (left_sh[1] + right_sh[1]) / 2,
        )
        hip_mid = (
            (left_hip[0] + right_hip[0]) / 2,
            (left_hip[1] + right_hip[1]) / 2,
        )

        neck_angle = angle_between_points(
            (nose[0], nose[1]),
            shoulder_mid,
            hip_mid,
        )
        deviation = abs(180 - neck_angle)
        if deviation > POSTURE_NECK_ANGLE_BAD:
            self.issues.append("neck_bend")

        shoulder_drop = (shoulder_mid[0] - hip_mid[0]) / w
        if abs(shoulder_drop) > POSTURE_SLOUCH_RATIO:
            self.issues.append("slouch")

        if face_bbox_height and face_bbox_height > FACE_TOO_CLOSE_RATIO:
            self.issues.append("too_close")

        bad = len(self.issues) > 0
        now = time.time()

        if bad:
            self.status = "Bad"
            if self._bad_since is None:
                self._bad_since = now
            self.bad_posture_seconds += 0.033
        else:
            self.status = "Good"
            self._bad_since = None

        penalty = len(self.issues) * 25 + min(30, self.bad_posture_seconds / 60)
        self.posture_score = clamp(100 - penalty)

        return {
            "status": self.status,
            "score": self.posture_score,
            "neck_angle": deviation,
            "issues": self.issues,
            "bad_duration_sec": self.bad_posture_seconds,
        }

    def check_alerts(self, alert_manager):
        if self.status == "Bad":
            alert_manager.push("Bad posture detected - Sit straight", color=(0, 0, 255))

    def close(self):
        pass
