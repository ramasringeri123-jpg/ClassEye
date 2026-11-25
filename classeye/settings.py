"""Paths and tunable settings.

Where things live
  * Running from source (python app.py): everything stays in the project folder, as before.
  * Installed app (ClassEye-Setup.exe): the program folder is read-only, so
      - student data + settings  ->  %LOCALAPPDATA%\\ClassEye        (not synced to OneDrive)
      - Excel reports            ->  Documents\\ClassEye Reports      (easy for teachers to find)
  * Portable copy: put an empty file named `portable.txt` next to ClassEye.exe (or keep an
    existing `data` folder there) and everything stays beside the .exe.
"""
import json
import os
import sys
from dataclasses import asdict, dataclass, fields


def app_dir() -> str:
    """Folder of the program itself (read-only when installed)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_path(name: str) -> str:
    return os.path.join(getattr(sys, "_MEIPASS", app_dir()), "assets", name)


def _portable() -> bool:
    if not getattr(sys, "frozen", False):
        return True
    d = app_dir()
    return os.path.exists(os.path.join(d, "portable.txt")) or os.path.isdir(os.path.join(d, "data"))


def user_dir() -> str:
    """Writable folder for student data and settings."""
    if _portable():
        return app_dir()
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Application Support")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(root, "ClassEye")


base_dir = user_dir          # older name


def data_dir() -> str:
    return os.path.join(user_dir(), "data")


def classes_dir() -> str:
    return os.path.join(data_dir(), "classes")


def settings_path() -> str:
    return os.path.join(user_dir(), "settings.json")


def models_dir() -> str:
    """Models shipped with the program (a user-installed copy in user_dir()/models wins)."""
    return os.path.join(app_dir(), "models")


def reports_dir() -> str:
    if _portable():
        return os.path.join(app_dir(), "reports")
    return os.path.join(os.path.expanduser("~"), "Documents", "ClassEye Reports")


MODEL_FILES = {
    "face_detector": "face_detection_yunet_2023mar.onnx",
    "face_recognizer": "face_recognition_sface_2021dec.onnx",
    "pose": "yolov8n-pose.onnx",
    "objects": "yolov8n.onnx",
}


def model_path(key: str) -> str:
    own = os.path.join(user_dir(), "models", MODEL_FILES[key])   # e.g. an upgraded, bigger YOLO
    return own if os.path.exists(own) else os.path.join(models_dir(), MODEL_FILES[key])


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
    lap_phone_s: float = 3.0          # head bowed + hands together low for this long
    reach_count: int = 2              # quick reaches to a hiding place within 90 s
    hand_crops_per_frame: int = 2     # students whose hand area gets a close-up check per frame
    identify_every: int = 8           # frames between face identification passes

    # class mode (attention)
    sleep_s: float = 20.0             # head down and still this long = sleeping
    attention_turn_ratio: float = 0.45  # head turned away from the board by this much = distracted

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        path = settings_path()
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
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    def timing_factor(self) -> float:
        """How long a behaviour must last before it is reported."""
        return {"Low": 1.6, "High": 0.6}.get(self.sensitivity, 1.0)
