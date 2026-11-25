"""Class Mode: estimates how much each student is paying attention during a lecture.

Every frame, YOLOv8-pose gives each student's head and shoulder keypoints. From them
we estimate where the student is looking and whether the head has dropped:

    ATTENTIVE   face visible and pointed the same way as most of the class (the board)
    WRITING     head bowed a little - taking notes or reading (counts as half attention)
    DISTRACTED  head turned well away from the board, or turned around
    SLEEPING    head dropped very low (or face hidden while the head is down) and
                hardly moving for `sleep_s` seconds

Each state is worth points (1, 0.5, 0, 0). A student's attention % is the time-weighted
average of their points over the lecture. Students are identified by face against the
class dataset, so the report lists USN and name.

It is an APPROXIMATE indicator for the teacher, not a grade.
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field

import cv2
import numpy as np

from .tracking import Tracker

NOSE, LEYE, REYE, LEAR, REAR, LSH, RSH = range(7)
POINTS = {"Attentive": 1.0, "Writing": 0.5, "Distracted": 0.0, "Sleeping": 0.0, "Away": 0.0}
COLORS = {"Attentive": (113, 191, 47), "Writing": (230, 170, 40), "Distracted": (36, 140, 245),
          "Sleeping": (79, 84, 240), "Away": (150, 150, 150)}


@dataclass
class StudentAttention:
    key: str                         # USN, or "#<track id>" if not identified
    usn: str = ""
    name: str = ""
    seconds: float = 0.0
    points: float = 0.0
    by_state: dict = field(default_factory=lambda: defaultdict(float))
    state: str = ""
    sleeping_now: bool = False

    @property
    def percent(self):
        return round(100.0 * self.points / self.seconds, 1) if self.seconds > 0 else 0.0

    @property
    def level(self):
        if self.by_state["Sleeping"] >= 60:
            return "Poor (sleeping)"
        p = self.percent
        if p >= 70:
            return "Good"
        if p >= 40:
            return "Average"
        return "Poor"


class AttentionMonitor:
    def __init__(self, settings, pose_model, face_engine=None, gallery=None, class_name="Class"):
        self.s = settings
        self.pose = pose_model
        self.face = face_engine
        self.gallery = gallery if gallery is not None and len(gallery) else None
        self.class_name = class_name
        self.tracker = Tracker(keep_frames=40)
        self.started = None
        self.last_time = None
        self.frame_no = 0
        self.students = {}                 # key -> StudentAttention
        self.timeline = defaultdict(lambda: [0.0, 0.0])   # minute -> [points, seconds]
        self.people_now = 0

    # ------------------------------------------------------------------
    def process(self, frame, now=None):
        now = now or time.time()
        if self.started is None:
            self.started = self.last_time = now
        dt = min(1.0, max(0.0, now - self.last_time))      # frame gap (ignore long stalls)
        self.last_time = now
        self.frame_no += 1
        people = self.tracker.update(self.pose(frame), now)
        self.people_now = len(people)
        if self.gallery is not None and self.face is not None and \
                self.frame_no % max(1, self.s.identify_every) == 1:
            self._identify(frame, people)

        feats = {p.id: self._features(p) for p in people if p.kpts is not None}
        yaws = [f["yaw"] for f in feats.values() if f and f["yaw"] is not None]
        board = float(np.median(yaws)) if len(yaws) >= 3 else None   # where most of the class looks
        drops = [f["drop"] for f in feats.values() if f and f["drop"] is not None]
        class_drop = float(np.median(drops)) if len(drops) >= 3 else None   # the class's usual head height

        minute = int((now - self.started) // 60)
        for p in people:
            f = feats.get(p.id)
            state = self._classify(p, f, board, class_drop, now) if f else "Away"
            rec = self._record_for(p)
            rec.state = state
            rec.sleeping_now = state == "Sleeping"
            rec.seconds += dt
            rec.points += POINTS[state] * dt
            rec.by_state[state] += dt
            tl = self.timeline[minute]
            tl[0] += POINTS[state] * dt
            tl[1] += dt
        return self._draw(frame, people), self.summary()

    # ------------------------------------------------------------------
    def _pt(self, p, i):
        k = p.kpts[i]
        return (float(k[0]), float(k[1])) if k[2] >= self.s.keypoint_conf else None

    def _features(self, p):
        lsh, rsh = self._pt(p, LSH), self._pt(p, RSH)
        if lsh is None or rsh is None:
            return None
        sw = max(abs(lsh[0] - rsh[0]), 12.0)
        neck = ((lsh[0] + rsh[0]) / 2, (lsh[1] + rsh[1]) / 2)
        nose, leye, reye = self._pt(p, NOSE), self._pt(p, LEYE), self._pt(p, REYE)
        lear, rear = self._pt(p, LEAR), self._pt(p, REAR)
        reversed_sh = (lsh[0] - rsh[0]) < -0.15 * sw            # turned around
        head = nose or leye or reye or lear or rear
        return {
            "sw": sw, "neck": neck, "reversed": reversed_sh,
            "face": nose is not None and (leye is not None or reye is not None),
            "yaw": (nose[0] - neck[0]) / sw if nose is not None and not reversed_sh else None,
            "drop": (head[1] - neck[1]) / sw if head is not None else None,   # bigger = head lower
            "head": head,
        }

    def _classify(self, p, f, board, class_drop, now):
        m = p.memory
        # learn this student's upright head height (the most upright recent posture)
        if f["drop"] is not None:
            base = m.get("upright", f["drop"])
            if f["drop"] < base:                       # more upright than we thought: adopt quickly
                base = 0.8 * base + 0.2 * f["drop"]
            elif f["drop"] - base < 0.2:               # near upright: adjust slowly
                base = 0.99 * base + 0.01 * f["drop"]
            # head clearly bowed: keep the reference (never learn sleeping as "normal")
            m["upright"] = base
            bow = f["drop"] - base
            if class_drop is not None:                 # also compare with the rest of the class
                bow = max(bow, f["drop"] - class_drop)
        else:
            bow = None

        # how still the head is (sleeping students barely move)
        if f["head"] is not None:
            prev = m.get("head_prev")
            move = 0.0 if prev is None else np.hypot(f["head"][0] - prev[0], f["head"][1] - prev[1]) / f["sw"]
            m["head_prev"] = f["head"]
            m["motion"] = 0.9 * m.get("motion", move) + 0.1 * move
        still = m.get("motion", 1.0) < 0.03

        # ---- sleeping: head very low, or face hidden with head down, and still for a while ----
        very_low = bow is not None and (bow > 0.75 or f["drop"] > 0.05)
        face_down = not f["face"] and bow is not None and bow > 0.45
        drowsy = (very_low or face_down) and still
        if drowsy:
            m.setdefault("drowsy_since", now)
        else:
            m.pop("drowsy_since", None)
        if drowsy and now - m["drowsy_since"] >= self.s.sleep_s:
            return "Sleeping"

        if f["reversed"]:
            return "Distracted"
        if not f["face"]:
            return "Writing" if bow is not None and bow > 0.3 else "Distracted"
        if bow is not None and bow > 0.3:
            return "Writing"
        # ---- facing the board? compare with the class (or the student's own usual direction) ----
        ref = board
        if ref is None:
            ref = m.get("yaw_ref", f["yaw"])
            if abs(f["yaw"] - ref) < self.s.attention_turn_ratio * 0.6:
                ref = 0.98 * ref + 0.02 * f["yaw"]
            m["yaw_ref"] = ref
        turned = abs(f["yaw"] - ref) > self.s.attention_turn_ratio
        if turned:
            m.setdefault("turned_since", now)
        else:
            m.pop("turned_since", None)
        if turned and now - m["turned_since"] >= 2.0:          # a quick glance is fine
            return "Distracted"
        return "Attentive"

    def _record_for(self, p):
        key = p.student.usn if p.student else f"#{p.id}"
        rec = self.students.get(key)
        if rec is None:
            rec = self.students[key] = StudentAttention(
                key, p.student.usn if p.student else "", p.student.name if p.student else "")
            # a track identified late: fold its earlier anonymous time into the student
            anon = self.students.pop(f"#{p.id}", None) if p.student else None
            if anon:
                rec.seconds, rec.points = anon.seconds, anon.points
                for k, v in anon.by_state.items():
                    rec.by_state[k] += v
        return rec

    def _identify(self, frame, people):
        for f in self.face.detect(frame):
            if f.vector is None:
                continue
            st, sim = self.gallery.identify(f.vector, self.s.match_threshold, self.s.match_margin)
            if st is None:
                continue
            cx, cy = f.centre
            for p in people:
                x1, y1, x2, y2 = p.box
                if x1 <= cx <= x2 and y1 <= cy <= y1 + 0.55 * (y2 - y1):
                    p.vote(st, sim)
                    break

    # ------------------------------------------------------------------
    def summary(self):
        rows = [r for r in self.students.values() if r.seconds >= 5]
        total_pts = sum(r.points for r in rows)
        total_s = sum(r.seconds for r in rows)
        return {
            "class_percent": round(100 * total_pts / total_s, 1) if total_s else 0.0,
            "students": sorted(rows, key=lambda r: r.percent),
            "sleeping_now": sum(1 for r in self.students.values() if r.sleeping_now),
            "people_now": self.people_now,
            "minutes": round((self.last_time - self.started) / 60, 1) if self.started else 0.0,
        }

    def timeline_rows(self):
        return [(m + 1, round(100 * pts / secs, 1) if secs else 0.0)
                for m, (pts, secs) in sorted(self.timeline.items())]

    def _draw(self, img, people):
        th = max(1, img.shape[1] // 800)
        for p in people:
            key = p.student.usn if p.student else f"#{p.id}"
            rec = self.students.get(key)
            state = rec.state if rec else "Away"
            col = COLORS.get(state, (200, 200, 200))
            x1, y1, x2, y2 = p.box.astype(int)
            cv2.rectangle(img, (x1, y1), (x2, y2), col, (3 if state == "Sleeping" else 2) * th)
            label = f"{key}  {state}" + (f"  {rec.percent:.0f}%" if rec and rec.seconds >= 5 else "")
            (tw, tht), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5 * th, th)
            cv2.rectangle(img, (x1, y1 - tht - 8), (x1 + tw + 8, y1), col, -1)
            cv2.putText(img, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * th, (255, 255, 255), th)
        return img
