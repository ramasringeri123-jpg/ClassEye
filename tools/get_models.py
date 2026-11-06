"""Download / prepare the AI models (run once, needs internet).

    python tools/get_models.py            face models + YOLO (nano, fastest)
    python tools/get_models.py --size s   bigger YOLO: better for large halls, slower
    python tools/get_models.py --faces    face models only (attendance works without YOLO)

Face models come from the official OpenCV model zoo. The YOLOv8 models are
exported to ONNX with the `ultralytics` package, which is installed only for
this step - the app itself never needs PyTorch.
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")
ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models/"
FACE = {
    "face_detection_yunet_2023mar.onnx": ZOO + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": ZOO + "face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
        print(f"  ok   {os.path.basename(dest)}")
        return
    print(f"  get  {os.path.basename(dest)} ...")
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    if os.path.getsize(tmp) < 100_000:
        os.remove(tmp)
        raise SystemExit(f"Download failed (file too small): {url}")
    os.replace(tmp, dest)
    print(f"  ok   {os.path.basename(dest)}  {os.path.getsize(dest) / 1e6:.1f} MB")


def export_yolo(size, imgsz):
    targets = [(f"yolov8{size}-pose.pt", "yolov8n-pose.onnx"), (f"yolov8{size}.pt", "yolov8n.onnx")]
    if all(os.path.exists(os.path.join(MODELS, t)) for _, t in targets):
        print("  ok   YOLO models already present")
        return
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  installing ultralytics for the one-time export (a few minutes)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "ultralytics", "onnx", "onnxslim"])
        from ultralytics import YOLO
    here = os.getcwd()
    os.chdir(MODELS)
    try:
        for src, target in targets:
            dest = os.path.join(MODELS, target)
            if os.path.exists(dest):
                print(f"  ok   {target}")
                continue
            print(f"  make {target} from {src} ...")
            out = YOLO(src).export(format="onnx", imgsz=imgsz, opset=12, dynamic=False, simplify=False)
            os.replace(out, dest)
            print(f"  ok   {target}")
        for f in os.listdir(MODELS):
            if f.endswith(".pt"):
                os.remove(os.path.join(MODELS, f))
    finally:
        os.chdir(here)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="n", choices=["n", "s", "m"])
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--faces", action="store_true", help="face models only")
    a = ap.parse_args()
    os.makedirs(MODELS, exist_ok=True)
    print("Face models:")
    for name, url in FACE.items():
        fetch(url, os.path.join(MODELS, name))
    if not a.faces:
        print("Exam-mode models:")
        export_yolo(a.size, a.imgsz)
    print("Done. Models are in", MODELS)


if __name__ == "__main__":
    main()
