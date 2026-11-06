"""Attendance history per class and the shortage (below 75%) calculations.

Every finished attendance scan is stored in data/classes/<class id>/attendance.json:
    [{"time": "2026-11-06 14:30", "subject": "Maths", "present": [...USNs], "absent": [...USNs]}, ...]
"""
import json
import math
import os
import time
from dataclasses import dataclass


def _path(classroom):
    return os.path.join(classroom.folder, "attendance.json")


def load_sessions(classroom):
    try:
        with open(_path(classroom), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def record_session(classroom, scan, subject=""):
    sessions = load_sessions(classroom)
    sessions.append({
        "time": time.strftime("%Y-%m-%d %H:%M"),
        "subject": subject,
        "present": sorted(m.usn for m in scan.present()),
        "absent": sorted(m.usn for m in scan.absent()),
    })
    tmp = _path(classroom) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=1)
    os.replace(tmp, _path(classroom))
    return sessions


@dataclass
class StudentStats:
    usn: str
    name: str
    attended: int
    held: int
    percent: float
    status: str        # "Shortage", "At risk", "Safe"
    need: int          # classes in a row needed to reach the threshold (0 if already there)
    can_miss: int      # classes that can be missed and still stay at/above the threshold


def classes_needed(attended, held, threshold):
    """Smallest n with (attended + n) / (held + n) >= threshold."""
    t = threshold / 100.0
    if held == 0 or attended / held >= t:
        return 0
    if t >= 1:
        return 10 ** 6
    return math.ceil((t * held - attended) / (1 - t))


def classes_can_miss(attended, held, threshold):
    """Largest m with attended / (held + m) >= threshold."""
    t = threshold / 100.0
    if held == 0 or t <= 0:
        return 0
    return max(0, math.floor(attended / t - held + 1e-9))


def class_report(students, sessions, threshold=75.0, risk_margin=5.0):
    """Per-student statistics, worst attendance first."""
    rows = []
    for st in students:
        held = sum(1 for s in sessions if st.usn in s["present"] or st.usn in s["absent"])
        attended = sum(1 for s in sessions if st.usn in s["present"])
        pct = round(100.0 * attended / held, 1) if held else 0.0
        if held == 0:
            status = "No classes yet"
        elif pct < threshold:
            status = "Shortage"
        elif pct <= threshold + risk_margin:
            status = "At risk"
        else:
            status = "Safe"
        rows.append(StudentStats(st.usn, st.name, attended, held, pct, status,
                                 classes_needed(attended, held, threshold),
                                 classes_can_miss(attended, held, threshold)))
    order = {"Shortage": 0, "At risk": 1, "Safe": 2, "No classes yet": 3}
    return sorted(rows, key=lambda r: (order[r.status], r.percent, r.usn))


def overview(rows, sessions):
    with_classes = [r for r in rows if r.held]
    return {
        "sessions": len(sessions),
        "average": round(sum(r.percent for r in with_classes) / len(with_classes), 1) if with_classes else 0.0,
        "shortage": sum(1 for r in rows if r.status == "Shortage"),
        "at_risk": sum(1 for r in rows if r.status == "At risk"),
        "perfect": sum(1 for r in with_classes if r.attended == r.held),
    }
