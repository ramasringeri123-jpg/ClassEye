# Contributing to ClassEye

Thanks for helping make classrooms smarter! Contributions of all sizes are welcome:
bug reports, new behaviour rules, UI polish, translations, documentation.

## Quick start

```bash
git clone https://github.com/ramasringeri123-jpg/ClassEye.git
cd ClassEye
# Windows: setup.bat   ·   macOS/Linux: bash setup_mac.sh
python tests/test_classeye.py      # must print ALL TESTS PASSED
python app.py
```

## How to contribute

1. **Open an issue first** for anything bigger than a small fix, so we can agree on the approach.
2. **Fork** the repo and create a branch: `git checkout -b feature/short-name`.
3. Keep changes focused. Add or update a test in `tests/test_classeye.py` for any logic change.
4. Run the tests, then open a **pull request** describing what changed and how you tested it.

## Code layout

| Folder | What lives there |
|---|---|
| `classeye/` | Core logic, no UI: cameras, faces, classrooms, attendance, exam rules, reports |
| `ui/` | PySide6 desktop interface |
| `tools/` | Model download / export |
| `tests/` | Automated tests (no camera or model files needed) |

Keep UI code out of `classeye/` so the logic stays testable.

## Privacy rules (important)

ClassEye works with students' faces. Contributions must keep it **offline-first**:

- Never commit photos, face datasets, embeddings, reports or model files.
  `.gitignore` already excludes `data/`, `reports/` and `models/*.onnx`. Don't override it.
- No feature may upload faces or attendance data to a cloud service without
  explicit, opt-in configuration by the institution.
- Exam-mode alerts are suspicions for a human invigilator, never automatic penalties.
  Keep wording and features consistent with that.

## Ideas we'd love help with

- Liveness / anti-spoofing check for attendance
- Multi-camera exam halls
- A model fine-tuned on exam-hall footage (small chits, hidden phones)
- Late-comer marking and parent notifications
- Translations of the interface

## Code of conduct

Be kind and constructive. Harassment or discrimination of any kind is not tolerated.
