"""Keeps a stable ID for every student between frames (IoU matching)."""
import numpy as np


def iou(a, b):
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), np.float32)
    a = np.asarray(a, np.float32)[:, None]
    b = np.asarray(b, np.float32)[None]
    w = np.clip(np.minimum(a[..., 2], b[..., 2]) - np.maximum(a[..., 0], b[..., 0]), 0, None)
    h = np.clip(np.minimum(a[..., 3], b[..., 3]) - np.maximum(a[..., 1], b[..., 1]), 0, None)
    inter = w * h
    area = lambda r: (r[..., 2] - r[..., 0]) * (r[..., 3] - r[..., 1])  # noqa: E731
    return inter / np.maximum(area(a) + area(b) - inter, 1e-6)


class Person:
    def __init__(self, pid, det, now):
        self.id = pid
        self.box = np.asarray(det.box, np.float32)
        self.kpts = det.kpts
        self.seen_since = now
        self.lost = 0
        self.timers = {}          # behaviour -> {"start", "last"}
        self.memory = {}          # learned normal posture
        self.votes = {}           # usn -> (student, score)
        self.student = None
        self.flag_until = 0.0
        self.flag_text = ""

    def update(self, det):
        self.box = 0.65 * np.asarray(det.box, np.float32) + 0.35 * self.box
        k = det.kpts
        if k is not None and self.kpts is not None:
            # smooth keypoints that are confident in both frames: less jitter -> fewer
            # flickering rules and fewer false alerts
            k = k.copy()
            both = (k[:, 2] >= 0.3) & (self.kpts[:, 2] >= 0.3)
            k[both, :2] = 0.6 * k[both, :2] + 0.4 * self.kpts[both, :2]
        self.kpts = k
        self.lost = 0

    def vote(self, student, score):
        st, total = self.votes.get(student.usn, (student, 0.0))
        self.votes[student.usn] = (st, total + score)
        self.student = max(self.votes.values(), key=lambda v: v[1])[0]


class Tracker:
    def __init__(self, min_iou=0.25, keep_frames=25):
        self.min_iou, self.keep = min_iou, keep_frames
        self.people = []
        self._next = 1

    def update(self, dets, now):
        m = iou([p.box for p in self.people], [d.box for d in dets])
        used_p, used_d = set(), set()
        if m.size:
            for pi, di in np.dstack(np.unravel_index(np.argsort(-m, axis=None), m.shape))[0]:
                if m[pi, di] < self.min_iou:
                    break
                if pi in used_p or di in used_d:
                    continue
                self.people[pi].update(dets[di])
                used_p.add(pi)
                used_d.add(di)
        for i, p in enumerate(self.people):
            if i not in used_p:
                p.lost += 1
                p.kpts = None
        for i, d in enumerate(dets):
            if i not in used_d:
                self.people.append(Person(self._next, d, now))
                self._next += 1
        self.people = [p for p in self.people if p.lost <= self.keep]
        return [p for p in self.people if p.lost == 0]
