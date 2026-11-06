# Third-party notices

ClassEye's own source code is MIT licensed (see `LICENSE`). It relies on the
following third-party models and libraries, which keep their own licenses.
**No model files are stored in this repository**; `tools/get_models.py`
downloads them on your machine.

## AI models

| Model | Used for | Source | License |
|---|---|---|---|
| YuNet (`face_detection_yunet_2023mar.onnx`) | Face detection | [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT |
| SFace (`face_recognition_sface_2021dec.onnx`) | Face recognition | [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) | Apache-2.0 |
| YOLOv8n / YOLOv8n-pose | Phone detection, body pose | [Ultralytics](https://github.com/ultralytics/ultralytics) | **AGPL-3.0** |

### Important: YOLOv8 is AGPL-3.0

The YOLOv8 models are licensed by Ultralytics under the GNU AGPL-3.0 (a
commercial license is also available from Ultralytics). If you **distribute**
ClassEye together with these models (for example the packaged `ClassEye.exe`
with its `models` folder), or offer it to others over a network, you must
follow the AGPL-3.0 terms for that combined work, including making the
complete source available. Keeping this repository public covers the source
for the version you ship. Attendance mode does not use YOLO at all.

## Libraries

| Library | License |
|---|---|
| [OpenCV](https://opencv.org) (`opencv-python`) | Apache-2.0 |
| [ONNX Runtime](https://onnxruntime.ai) | MIT |
| [PySide6 / Qt for Python](https://www.qt.io/qt-for-python) | LGPL-3.0 |
| [NumPy](https://numpy.org) | BSD-3-Clause |
| [openpyxl](https://openpyxl.readthedocs.io) | MIT |
| [pygrabber](https://github.com/andreaschiavinato/python_grabber) | MIT |
| [Ultralytics](https://github.com/ultralytics/ultralytics) (only to export models) | AGPL-3.0 |

Check each project's page for the exact, current terms.
