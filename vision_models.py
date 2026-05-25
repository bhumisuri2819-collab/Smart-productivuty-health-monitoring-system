"""
vision_models.py - MediaPipe Tasks API (0.10.30+) with auto model download.
Replaces deprecated mp.solutions.face_mesh / mp.solutions.pose.
"""

import urllib.request
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from utils import BASE_DIR

MODELS_DIR = BASE_DIR / "models"
FACE_MODEL = MODELS_DIR / "face_landmarker.task"
POSE_MODEL = MODELS_DIR / "pose_landmarker_lite.task"

FACE_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
POSE_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)

_engine = None


def _download_file(url: str, dest: Path):
    """Download model .task file if not present."""
    if dest.exists() and dest.stat().st_size > 1000:
        return
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[Setup] Downloading {dest.name} (one-time, ~few MB)...")
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"[Setup] Saved {dest}")
    except Exception as e:
        raise RuntimeError(
            f"Could not download {dest.name}. Check internet once, or place the file manually in:\n"
            f"  {MODELS_DIR}\n"
            f"URL: {url}\nError: {e}"
        ) from e


class VisionEngine:
    """Shared face + pose landmark detectors (CPU, offline)."""

    def __init__(self):
        _download_file(FACE_URL, FACE_MODEL)
        _download_file(POSE_URL, POSE_MODEL)

        face_options = vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(FACE_MODEL)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        pose_options = vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(POSE_MODEL)),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self.face_landmarker = vision.FaceLandmarker.create_from_options(face_options)
        self.pose_landmarker = vision.PoseLandmarker.create_from_options(pose_options)

    def process_frame(self, frame_rgb):
        """
        Run face + pose on one RGB numpy frame.
        Returns (face_landmarks_list_or_None, pose_landmarks_list_or_None).
        """
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        face_lm = None
        pose_lm = None

        try:
            face_result = self.face_landmarker.detect(mp_image)
            if face_result.face_landmarks:
                face_lm = face_result.face_landmarks[0]
        except Exception:
            pass

        try:
            pose_result = self.pose_landmarker.detect(mp_image)
            if pose_result.pose_landmarks:
                pose_lm = pose_result.pose_landmarks[0]
        except Exception:
            pass

        return face_lm, pose_lm

    def close(self):
        try:
            self.face_landmarker.close()
        except Exception:
            pass
        try:
            self.pose_landmarker.close()
        except Exception:
            pass


def get_vision_engine():
    """Singleton vision engine (models load once)."""
    global _engine
    if _engine is None:
        _engine = VisionEngine()
    return _engine


def close_vision_engine():
    global _engine
    if _engine is not None:
        _engine.close()
        _engine = None
