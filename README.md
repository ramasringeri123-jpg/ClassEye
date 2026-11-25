<p align="center"><img src="assets/classeye.png" width="128" alt="ClassEye logo"></p>

<h1 align="center">ClassEye — Smart Attendance & Exam Monitoring</h1>

<p align="center"><a href="https://github.com/ramasringeri123-jpg/ClassEye/releases/latest"><b>⬇ Download for Windows</b></a></p>

![License: MIT](https://img.shields.io/badge/license-MIT-blue) ![Python 3.10–3.12](https://img.shields.io/badge/python-3.10%E2%80%933.12-3776AB) ![Platform: Windows | macOS](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey) ![Runs offline](https://img.shields.io/badge/runs-100%25%20offline-2ea44f) ![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)

**Open-source · Technovate 2.0 · 12-hour hackathon · built on 6 Nov 2026**

ClassEye turns any camera — a laptop webcam, a USB camera, a CCTV camera or a phone — into:

1. **Smart Attendance:** scans the classroom, recognises every student from the class dataset
   (USN, name, photos) and saves a formatted Excel sheet with present/absent, absentees and a running register.
2. **Exam Monitoring:** watches the whole hall and reports malpractice with photo evidence:
   mobile phone use, taking out hidden chits (pocket, waist, sleeve, shirt, under the desk),
   turning back, peeping into the front student's paper, looking at a neighbour's paper,
   and passing things. Students are identified using the photos of **all** classes, and every
   incident goes into an Excel report.

## Features

| Area | What it does |
|---|---|
| Cameras | Auto-discovers every camera on the computer (Device Manager) **and** Wi-Fi cameras on the network (phones with IP Webcam/DroidCam, RTSP CCTV). Manual address also supported. |
| Classes | Unlimited classrooms (e.g. *AIML A Section*, *AIML B Section*), each with its own dataset. Create, rename, delete. |
| Dataset | Add students (USN + name), capture face photos from the live camera, add photo files, or import a CSV/Excel list with a photo folder. A dataset check flags missing or unusable photos. |
| Attendance | Multi-frame voting, look-alike protection and one-face-one-student matching for accuracy. **Unknown people** (anyone not in the class dataset) are flagged live and listed with photos. Excel with face photos, absentees, unknown persons and a per-class register with attendance %. |
| Dashboard | Per-class attendance history, each student's %, **75% shortage alerts** (limit adjustable), "must attend next N classes" advice, and a one-click Excel summary for the HOD. |
| Class mode | Estimates each student's **attention %** during a lecture from head direction and posture (attentive, writing, distracted, sleeping). Sleeping students are marked *Poor attention*. Excel report with a minute-by-minute class attention chart. |
| Exam mode | Every alert is reported as **suspicious** for the invigilator to check. Close-up checks of each student's hand area catch small phones, plus a lap-phone posture rule and repeated-reach / paper-in-hand chit rules. Pose-based behaviour rules with time thresholds (a stretch or a glance is ignored), adjustable sensitivity, per-rule on/off, photo and close-up evidence, Excel incident report with a per-student summary. |

## How it works

```mermaid
flowchart LR
    CAM[Any camera] --> STREAM[LiveStream<br/>threaded, auto-reconnect]
    STREAM --> ATT{Mode}
    ATT -->|Attendance| FD[YuNet face detection] --> FR[SFace embeddings] --> VOTE[Match vs class dataset<br/>multi-frame voting] --> X1[Attendance.xlsx + Register]
    ATT -->|Exam| POSE[YOLOv8-pose<br/>17 keypoints] --> TRK[Tracker<br/>stable IDs] --> RULES[Behaviour rules]
    OBJ[YOLOv8 phone detection] --> RULES
    FR2[Face ID vs ALL classes] --> RULES
    RULES --> X2[Exam_Report.xlsx + evidence photos]
```

## Download & install (Windows 10/11)

1. Open the [latest release](https://github.com/ramasringeri123-jpg/ClassEye/releases/latest).
2. Download **`ClassEye-Setup-<version>.exe`** and run it. No admin password needed; the AI models are included.
3. Open **ClassEye** from the Start menu or the desktop icon.

> **"Windows protected your PC"?** ClassEye isn't code-signed yet. Click **More info → Run anyway**.

No install allowed on the computer? Download **`ClassEye-Portable-<version>.zip`**, unzip it (even onto a pen drive) and run `ClassEye.exe`.

**Where your data is kept (installed version)**

| What | Folder |
|---|---|
| Classes, students, face photos, settings | `%LOCALAPPDATA%\ClassEye` |
| Excel reports and evidence photos | `Documents\ClassEye Reports` |

Uninstalling or updating never deletes these. The portable version keeps everything inside its own folder.

## Run from source (developers)

**Windows:** `setup.bat` once (needs internet, ~10 min), then `run.bat`.
**macOS:** `bash setup_mac.sh` once, then `bash run_mac.sh`.
**After pulling an update:** just start with `run.bat` / `run_mac.sh` — any new library is installed automatically.
**Tests:** `python tests/test_classeye.py`
**Windows build:** `build_exe.bat` → `dist\ClassEye\ClassEye.exe`; `build_exe.bat --installer` also makes the Setup.exe and portable zip (needs [Inno Setup 6](https://jrsoftware.org/isdl.php)).

**Publishing a new version:** raise `__version__` in `classeye/__init__.py`, commit, then push a tag such as `v1.1.0`.
GitHub Actions ([release.yml](.github/workflows/release.yml)) builds the installer and portable zip and attaches them to a new Release.

Phone as camera: install **IP Webcam** (Android), press *Start server*, then *Scan for cameras*
in ClassEye or type the phone's address (e.g. `192.168.43.1:8080`).

## Project structure

```
app.py                 entry point
classeye/settings.py   paths + tunable thresholds (settings.json)
classeye/cameras.py    camera discovery (local + network) and live stream
classeye/faces.py      YuNet face detection + SFace face embeddings
classeye/classrooms.py classrooms, students, photos, face gallery
classeye/attendance.py attendance scan logic
classeye/detector.py   YOLOv8 ONNX runner (objects + pose)
classeye/tracking.py   student tracker
classeye/exam.py       malpractice rules + evidence
classeye/reports.py    Excel reports
ui/                    PySide6 desktop interface
classeye/attention.py  class mode (attention estimate)
tools/get_models.py    model download / export
tools/build.py         Windows app + installer + portable zip
installer/             Inno Setup installer script
assets/                logo and app icon
.github/workflows/     automatic release build
tests/                 automated tests
```

## Open source & privacy

ClassEye is free and open source under the **MIT License** (see [LICENSE](LICENSE)).
The AI models keep their own licenses: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md),
especially the **AGPL-3.0** terms of the YOLOv8 models used in exam mode.

Everything runs **offline** on the college's own computer: no student face, photo or
attendance record is uploaded anywhere. Student data lives only on that computer
(`%LOCALAPPDATA%\ClassEye`, or the `data/` folder when run from source), never in Git. Institutions using ClassEye should collect
students' consent at enrolment.

Want to help? Read [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests are welcome.

## Credits

- **AI assistance:** this project was built with help from **Claude (Anthropic)**, an AI coding assistant,
  as permitted by the event mentors.
- [OpenCV](https://opencv.org) and the [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo):
  YuNet face detector and SFace face recognizer
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics): pose and object models (exported to ONNX)
- [ONNX Runtime](https://onnxruntime.ai), [PySide6 / Qt](https://www.qt.io/qt-for-python),
  [openpyxl](https://openpyxl.readthedocs.io), [NumPy](https://numpy.org), [pygrabber](https://github.com/andreaschiavinato/python_grabber)

## Team
Built at Technovate 2.0 by Sriram, Sinchana, Trisha and Suhan.

## Limits & next steps
- Recognition needs faces at least ~26 px wide: use one camera per ~30 students or a 1080p+ camera.
- Behaviour alerts are suspicions for an invigilator to review, not automatic penalties.
- Next: multi-camera halls, a fine-tuned model for small chits, and SMS alerts to invigilators.
