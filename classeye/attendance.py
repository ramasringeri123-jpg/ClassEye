"""Attendance scan: collects face matches over many frames before deciding.

Why it is accurate:
  * Present only after `hits_needed` separate recognitions (no single lucky match).
  * Best match must beat the runner-up student by `margin` (look-alikes, siblings).
  * One face -> one student and one student -> one face in every frame.
  * Faces too small to recognise are counted so the teacher gets a warning
    instead of a silent wrong "Absent".
"""
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Mark:
    usn: str
    name: str
    enrolled: bool
    hits: int = 0
    best: float = 0.0
    first_seen: float = 0.0
    snapshot: np.ndarray = None


class AttendanceScan:
    def __init__(self, classroom_name, gallery, students, threshold=0.40, margin=0.05, hits_needed=3):
        self.classroom = classroom_name
        self.gallery = gallery
        self.threshold, self.margin, self.hits_needed = threshold, margin, hits_needed
        self.started = time.time()
        self.frames = 0
        self.unknown_faces = 0
        self.small_faces = 0
        self.peak_faces = 0
        enrolled = {s.usn for s in gallery.students}
        self.marks = {s.usn: Mark(s.usn, s.name, s.usn in enrolled) for s in students}

    def feed(self, frame, faces, now=None):
        """Update with one frame. Returns [(face, usn or None, similarity)] for drawing."""
        now = now or time.time()
        self.frames += 1
        self.peak_faces = max(self.peak_faces, len(faces))
        result = [(f, None, 0.0) for f in faces]
        usable = [i for i, f in enumerate(faces) if f.vector is not None]
        self.small_faces += len(faces) - len(usable)
        if not usable or len(self.gallery) == 0:
            self.unknown_faces += len(usable)
            return result

        sims = self.gallery.best_per_student([faces[i].vector for i in usable])
        ranked = -np.sort(-sims, axis=1)
        top = ranked[:, 0]
        second = ranked[:, 1] if sims.shape[1] > 1 else np.full(len(usable), -1.0)

        taken_face, taken_student = set(), set()
        order = np.dstack(np.unravel_index(np.argsort(-sims, axis=None), sims.shape))[0]
        for fi, si in order:
            s = float(sims[fi, si])
            if s < self.threshold:
                break
            if fi in taken_face or si in taken_student:
                continue
            if s < top[fi] - 1e-6 or top[fi] - second[fi] < self.margin:
                continue
            taken_face.add(fi)
            taken_student.add(si)
            face = faces[usable[fi]]
            st = self.gallery.students[si]
            m = self.marks.get(st.usn)
            if m is None:
                continue
            m.hits += 1
            if not m.first_seen:
                m.first_seen = now
            if s > m.best:
                m.best = s
                m.snapshot = _crop(frame, face.box)
            result[usable[fi]] = (face, st.usn, s)
        self.unknown_faces += len(usable) - len(taken_face)
        return result

    def is_present(self, mark):
        return mark.hits >= self.hits_needed

    def present(self):
        return [m for m in self.marks.values() if self.is_present(m)]

    def absent(self):
        return [m for m in self.marks.values() if not self.is_present(m)]

    def summary(self):
        total = len(self.marks)
        p = len(self.present())
        return {"total": total, "present": p, "absent": total - p,
                "percent": round(100 * p / total, 1) if total else 0.0,
                "frames": self.frames, "unknown": self.unknown_faces,
                "too_small": self.small_faces, "peak_faces": self.peak_faces,
                "no_photo": sum(1 for m in self.marks.values() if not m.enrolled)}


def _crop(frame, box, pad=0.4):
    x, y, w, h = box
    H, W = frame.shape[:2]
    x0, y0 = max(0, int(x - w * pad)), max(0, int(y - h * pad))
    x1, y1 = min(W, int(x + w * (1 + pad))), min(H, int(y + h * (1 + pad)))
    if x1 <= x0 or y1 <= y0:
        return None
    c = frame[y0:y1, x0:x1]
    return cv2.resize(c, (110, max(1, int(110 * c.shape[0] / c.shape[1]))))
