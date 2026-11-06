"""Paths and tunable settings. Settings live in settings.json next to the app."""
import json
import os
import sys
from dataclasses import asdict, dataclass, fields


def base_dir() -> str:
    """Folder of the .exe when packaged, else the project root."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    return os.path.join(base_dir(), "data")


def classes_dir() -> str:
    return os.path.join(data_dir(), "classes")


def models_dir() -> str:
    return os.path.join(base_dir(), "models")


def reports_dir() -> str:
    return os.path.join(base_dir(), "reports")


MODEL_FILES = {
    "face_detector": "face_detection_yunet_2023mar.onnx",
    "face_recognizer": "face_recognition_sface_2021dec.onnx",
    "pose": "yolov8n-pose.onnx",
    "objects": "yolov8n.onnx",
}


def model_path(key: str) -> str:
    return os.path.join(models_dir(), MODEL_FILES[key])


@dataclass
class Settings:
    # camera
    capture_width: int = 1920
    capture_height: int = 1080

    # faces
    face_min_score: float = 0.6
    face_min_size: int = 26           # px; smaller faces are not recognised
    face_upscale: float = 1.0         # 1.5 helps back rows on 720p cameras
    match_threshold: float = 0.40     # SFace cosine similarity
    match_margin: float = 0.05        # best must beat runner-up by this much

    # attendance
    scan_seconds: int = 45
    hits_to_mark_present: int = 3

    # exam
    person_conf: float = 0.35
    object_conf: float = 0.30
    keypoint_conf: float = 0.45
    sensitivity: str = "Normal"       # Low / Normal / High
    phone_hold_s: float = 0.5
    turn_back_s: float = 1.5
    peep_s: float = 1.5
    head_side_s: float = 2.5
    head_side_ratio: float = 0.40
    conceal_s: float = 1.2
    alert_repeat_s: float = 20.0
    identify_every: int = 8           # frames between face identification passes

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        path = os.path.join(base_dir(), "settings.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                names = {f.name for f in fields(cls)}
                for k, v in raw.items():
                    if k in names:
                        setattr(s, k, v)
            except (OSError, ValueError):
                pass
        return s

    def save(self) -> None:
        with open(os.path.join(base_dir(), "settings.json"), "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    def timing_factor(self) -> float:
        """How long a behaviour must last before it is reported."""
        return {"Low": 1.6, "High": 0.6}.get(self.sensitivity, 1.0)
