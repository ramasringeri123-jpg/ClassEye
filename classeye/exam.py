"""Exam-hall malpractice detection.

Every frame:
  1. YOLOv8-pose finds every student + 17 body keypoints; YOLOv8 finds mobile phones.
  2. A tracker gives each student a stable ID, so behaviour can be timed.
  3. Behaviour rules (each must last a while, so a stretch or a glance is ignored):

     PHONE        a mobile phone in or near a student's hands / desk area. Besides the
                  whole-frame scan, a close-up of each student's hand area is checked
                  (a few students per frame, in turn) so small phones are not missed.
     PHONE_LAP    head bowed while both hands are held together low in the lap
                  (the posture of reading a phone hidden under the desk)
     CHIT         a hand held at a hiding place: trouser pocket / waist, under the desk,
                  inside the opposite sleeve, or inside the shirt / chest pocket;
                  OR repeated quick reaches to a hiding place; OR paper seen in a hand
                  that is at a hiding place
     TURN_BACK    student turns around (shoulders reversed, or face hidden while ears show)
     PEEP_FRONT   head pushed into the space of the student sitting in front
     SIDE_LOOK    head turned sideways far beyond that student's own normal posture
     PASSING      hands of two students meet, or a hand reaches into a neighbour's space

  4. Every few frames faces are matched against the photos of ALL classes so each
     incident gets the student's USN, name and class.

Each incident is saved with a full-frame photo and a close-up for the Excel report.
"""
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np

from .detector import BOOK, PHONE, Det
from .tracking import Tracker

NOSE, LEYE, REYE, LEAR, REAR, LSH, RSH, LEL, REL, LWR, RWR, LHIP, RHIP = range(13)

# Every alert is a SUSPICION for the invigilator to check, never proof.
RULES = {
    "PHONE": ("Suspicious: mobile phone use", "High"),
    "PHONE_LAP": ("Suspicious: looking at something hidden in lap (possible phone)", "High"),
    "CHIT": ("Suspicious: taking out a hidden chit / paper", "High"),
    "PASSING": ("Suspicious: passing something to a neighbour", "High"),
    "TURN_BACK": ("Suspicious: turning back", "Medium"),
    "PEEP_FRONT": ("Suspicious: looking into front student's paper", "Medium"),
    "SIDE_LOOK": ("Suspicious: looking at neighbour's paper", "Medium"),
}

BONES = [(LSH, RSH), (LSH, LEL), (LEL, LWR), (RSH, REL), (REL, RWR), (LSH, LHIP), (RSH, RHIP), (LHIP, RHIP)]


@dataclass
class Incident:
    time: float
    track_id: int
    kind: str
    duration: float
    usn: str = ""
    name: str = ""
    class_name: str = ""
    photo: str = ""
    crop: str = ""

    @property
    def title(self):
        return RULES[self.kind][0]

    @property
    def severity(self):
        return RULES[self.kind][1]


class ExamMonitor:
    def __init__(self, settings, pose_model, object_model=None, face_engine=None, gallery=None,
                 out_dir="reports", enabled=None):
        self.s = settings
        self.k = settings.timing_factor()
        self.pose, self.objects = pose_model, object_model
        self.face = face_engine
        self.gallery = gallery if gallery is not None and len(gallery) else None
        self.enabled = set(enabled) if enabled else set(RULES)
        self.tracker = Tracker()
        self.incidents = []
        self.people_now = 0
        self.frame_no = 0
        self.folder = os.path.join(out_dir, time.strftime("Exam_%Y-%m-%d_%H-%M-%S"))
        os.makedirs(self.folder, exist_ok=True)
        self._last_alert = {}
        self._loose_phone_since = None

    # ------------------------------------------------------------------
    def process(self, frame, now=None):
        now = now or time.time()
        self.frame_no += 1
        people = self.tracker.update(self.pose(frame), now)
        self.people_now = len(people)
        phones = []
        if self.objects is not None and "PHONE" in self.enabled:
            phones = self.objects(frame, classes={PHONE}, conf=self.s.object_conf)
        if self.objects is not None and {"PHONE", "CHIT"} & self.enabled:
            phones += self._hand_pass(frame, people, now)
        if self.gallery is not None and self.face is not None and \
                self.frame_no % max(1, self.s.identify_every) == 1:
            self._identify(frame, people)

        new = self._phone_rule(frame, people, phones, now)
        for p in people:
            if p.kpts is not None:
                new += self._body_rules(frame, p, people, now)
        new += self._passing_rule(frame, people, now)
        self.incidents += new
        return self._draw(frame, people, phones, now), new

    # ------------------------------------------------------------------
    def _pt(self, p, i):
        k = p.kpts[i]
        return (float(k[0]), float(k[1])) if k[2] >= self.s.keypoint_conf else None

    def _held(self, p, key, active, now, seconds, grace=0.35):
        """True once `active` has stayed true for `seconds` (brief flickers forgiven)."""
        t = p.timers.setdefault(key, {"start": None, "last": None})
        if active:
            if t["start"] is None or now - t["last"] > grace:
                t["start"] = now
            t["last"] = now
            return now - t["start"] >= seconds * self.k, now - t["start"]
        if t["last"] is not None and now - t["last"] > grace:
            t["start"] = None
        return False, 0.0

    @staticmethod
    def _inside(pt, box, shrink=0.0):
        x1, y1, x2, y2 = box
        dx, dy = (x2 - x1) * shrink, (y2 - y1) * shrink
        return x1 + dx <= pt[0] <= x2 - dx and y1 + dy <= pt[1] <= y2 - dy

    @staticmethod
    def _dist(a, b):
        return float(np.hypot(a[0] - b[0], a[1] - b[1]))

    def _report(self, frame, p, kind, duration, now):
        if kind not in self.enabled:
            return []
        key = (p.id if p else 0, kind)
        if now - self._last_alert.get(key, -1e9) < self.s.alert_repeat_s:
            return []
        self._last_alert[key] = now
        st = p.student if p else None
        inc = Incident(now, p.id if p else 0, kind, round(duration, 1),
                       st.usn if st else "", st.name if st else "", st.class_name if st else "")
        inc.photo, inc.crop = self._save_evidence(frame, p, inc)
        if p is not None:
            p.flag_until, p.flag_text = now + 4.0, RULES[kind][0]
        return [inc]

    def _save_evidence(self, frame, p, inc):
        n = len(self.incidents) + 1
        img = frame.copy()
        crop_path = ""
        label = f"{RULES[inc.kind][0]}" + (f" - {inc.usn}" if inc.usn else "")
        if p is not None:
            x1, y1, x2, y2 = p.box.astype(int)
            cv2.rectangle(img, (x1, y1), (x2, y2), (60, 60, 240), 4)
            H, W = frame.shape[:2]
            mx, my = int((x2 - x1) * 0.3), int((y2 - y1) * 0.2)
            crop = frame[max(0, y1 - my):min(H, y2 + my), max(0, x1 - mx):min(W, x2 + mx)]
            if crop.size:
                crop_path = os.path.join(self.folder, f"{n:03d}_{inc.kind.lower()}_closeup.jpg")
                _save(crop_path, crop)
        cv2.rectangle(img, (0, 0), (img.shape[1], 44), (30, 30, 30), -1)
        cv2.putText(img, f"{time.strftime('%H:%M:%S', time.localtime(inc.time))}  {label}", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 80, 255), 2)
        if img.shape[1] > 1600:
            s = 1600 / img.shape[1]
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        photo = os.path.join(self.folder, f"{n:03d}_{inc.kind.lower()}.jpg")
        _save(photo, img)
        return photo, crop_path

    # ------------------------------------------------------------------
    def _phone_rule(self, frame, people, phones, now):
        out, holders = [], set()
        for ph in phones:
            cx, cy = (ph.box[0] + ph.box[2]) / 2, (ph.box[1] + ph.box[3]) / 2
            best, best_d = None, 1e9
            for p in people:
                x1, y1, x2, y2 = p.box
                w, h = x2 - x1, y2 - y1
                if self._inside((cx, cy), (x1 - 0.3 * w, y1, x2 + 0.3 * w, y2 + 0.35 * h)):
                    d = abs(cx - (x1 + x2) / 2) / max(w, 1)
                    if d < best_d:
                        best, best_d = p, d
            if best is not None:
                holders.add(best.id)
            elif self._loose_phone_since is None:
                self._loose_phone_since = now
        if not phones:
            self._loose_phone_since = None
        elif not holders and self._loose_phone_since and now - self._loose_phone_since >= self.s.phone_hold_s * self.k:
            out += self._report(frame, None, "PHONE", now - self._loose_phone_since, now)
        for p in people:   # a phone seen in this student's hand close-up stays "seen" for 1.2 s
            if now - p.memory.get("phone_seen", -1e9) < 1.2:
                holders.add(p.id)
            hit, dur = self._held(p, "phone", p.id in holders, now, self.s.phone_hold_s)
            if hit:
                out += self._report(frame, p, "PHONE", dur, now)
        return out

    def _body_rules(self, frame, p, people, now):
        s, out = self.s, []
        nose, leye, reye = self._pt(p, NOSE), self._pt(p, LEYE), self._pt(p, REYE)
        lear, rear = self._pt(p, LEAR), self._pt(p, REAR)
        lsh, rsh = self._pt(p, LSH), self._pt(p, RSH)
        if lsh is None or rsh is None:
            return out
        sw = max(abs(lsh[0] - rsh[0]), 12.0)                 # shoulder width = body scale
        neck = ((lsh[0] + rsh[0]) / 2, (lsh[1] + rsh[1]) / 2)

        # ---- turning back: shoulders reversed, or face hidden while ears visible ----
        # Facing the camera, the LEFT shoulder appears on the RIGHT of the image.
        reversed_sh = (lsh[0] - rsh[0]) < -0.15 * sw
        face_hidden = nose is None and leye is None and reye is None and (lear or rear) is not None
        hit, dur = self._held(p, "back", reversed_sh or face_hidden, now, s.turn_back_s)
        if hit:
            out += self._report(frame, p, "TURN_BACK", dur, now)

        # ---- looking sideways at a neighbour's paper (vs this student's normal) ----
        if nose is not None and not reversed_sh:
            yaw = (nose[0] - neck[0]) / sw
            base = p.memory.get("yaw", yaw)
            if abs(yaw - base) < s.head_side_ratio * 0.6:     # learn the normal pose slowly
                base = 0.97 * base + 0.03 * yaw
            p.memory["yaw"] = base
            one_ear = (lear is None) != (rear is None)
            turned = abs(yaw - base) + (0.08 if one_ear else 0) > s.head_side_ratio
            hit, dur = self._held(p, "side", turned and now - p.seen_since > 3, now, s.head_side_s)
            if hit:
                out += self._report(frame, p, "SIDE_LOOK", dur, now)

        # ---- peeping into the front student's paper ----
        head = nose or leye or reye
        peeping = False
        if head is not None:
            for o in people:
                if o.id == p.id:
                    continue
                in_front = o.box[3] > p.box[3] + 0.04 * (p.box[3] - p.box[1])
                if in_front and self._inside(head, o.box, shrink=0.12):
                    peeping = True
                    break
        hit, dur = self._held(p, "peep", peeping, now, s.peep_s)
        if hit:
            out += self._report(frame, p, "PEEP_FRONT", dur, now)

        # ---- hand at a hiding place (pocket, waist, under desk, sleeve, shirt) ----
        hiding_wrists = []
        lhip, rhip = self._pt(p, LHIP), self._pt(p, RHIP)
        sides = ((LWR, LHIP, REL, lhip), (RWR, RHIP, LEL, rhip))
        for wr_i, _hip_i, other_elbow_i, hip in sides:
            wr = self._pt(p, wr_i)
            if wr is None:
                continue
            other_elbow = self._pt(p, other_elbow_i)
            hidden = False
            if hip is not None:
                if self._dist(wr, hip) < 0.45 * sw and wr[1] > hip[1] - 0.2 * sw:   # pocket / waist
                    hidden = True
                if wr[1] > hip[1] + 0.35 * sw:                                    # under the desk / legs
                    hidden = True
            if other_elbow is not None and self._dist(wr, other_elbow) < 0.3 * sw:  # inside the sleeve
                hidden = True
            if neck[1] < wr[1] < neck[1] + 0.55 * sw and abs(wr[0] - neck[0]) < 0.35 * sw:  # inside shirt
                hidden = True
            if hidden:
                hiding_wrists.append(wr)
        hiding = bool(hiding_wrists)

        # (a) a hand kept at a hiding place
        hit, dur = self._held(p, "chit", hiding, now, s.conceal_s)
        if hit:
            out += self._report(frame, p, "CHIT", dur, now)

        # (b) paper seen next to a hand that is at a hiding place -> report almost at once
        papers = [b for b, t in p.memory.get("papers", []) if now - t < 1.0]
        paper_at_hand = any(self._dist(w, ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)) < 0.8 * sw
                            for w in hiding_wrists for b in papers)
        hit, dur = self._held(p, "chit_paper", paper_at_hand, now, 0.3)
        if hit:
            out += self._report(frame, p, "CHIT", dur, now)

        # (c) repeated quick reaches to a hiding place (shorter than the hold time each)
        r = p.memory.setdefault("reach", {"since": None, "times": []})
        if hiding and r["since"] is None:
            r["since"] = now
        elif not hiding and r["since"] is not None:
            if now - r["since"] >= 0.4 and (not r["times"] or now - r["times"][-1] > 2.0):
                r["times"].append(now)
            r["since"] = None
        r["times"] = [t for t in r["times"] if now - t < 90]
        if len(r["times"]) >= s.reach_count:
            r["times"] = []
            out += self._report(frame, p, "CHIT", 0.0, now)

        # ---- possible phone hidden in the lap: head bowed + both hands together, low ----
        lw, rw = self._pt(p, LWR), self._pt(p, RWR)
        if nose is not None:
            drop = (nose[1] - neck[1]) / sw                       # grows when the head bows
            base = p.memory.get("upright", drop)
            if drop < base:
                base = 0.8 * base + 0.2 * drop
            elif drop - base < 0.2:                    # only learn from near-upright postures
                base = 0.99 * base + 0.01 * drop
            p.memory["upright"] = base
            bowed = drop - base > 0.3
        else:
            bowed = False
        lap = False
        if bowed and lw is not None and rw is not None and self._dist(lw, rw) < 0.7 * sw:
            low = min(lw[1], rw[1]) > neck[1] + 1.4 * sw
            hips = [h for h in (lhip, rhip) if h is not None]
            if hips:
                low = low or min(lw[1], rw[1]) > min(h[1] for h in hips) - 0.1 * sw
            lap = low
        hit, dur = self._held(p, "lap", lap and now - p.seen_since > 3, now, s.lap_phone_s)
        if hit:
            out += self._report(frame, p, "PHONE_LAP", dur, now)
        return out

    # ------------------------------------------------------------------
    def _hand_pass(self, frame, people, now):
        """Close-up check of a few students' hand areas per frame for phones and paper.

        A phone is only a few pixels wide in a full classroom frame; cropping around the
        hands and running the detector on that crop makes it many times larger.
        """
        found = []
        cands = [p for p in people if p.kpts is not None]
        cands.sort(key=lambda p: p.memory.get("hand_checked", 0.0))
        H, W = frame.shape[:2]
        for p in cands[:max(0, self.s.hand_crops_per_frame)]:
            p.memory["hand_checked"] = now
            lsh, rsh = self._pt(p, LSH), self._pt(p, RSH)
            x1, y1, x2, y2 = p.box
            sw = abs(lsh[0] - rsh[0]) if lsh and rsh else (x2 - x1) * 0.5
            wrists = [w for w in (self._pt(p, LWR), self._pt(p, RWR)) if w is not None]
            if wrists:
                cx = sum(w[0] for w in wrists) / len(wrists)
                cy = sum(w[1] for w in wrists) / len(wrists)
            else:
                cx, cy = (x1 + x2) / 2, y1 + 0.7 * (y2 - y1)
            half = max(2.4 * sw, 0.55 * (y2 - y1), 64) / 2
            a, b = int(max(0, cx - half)), int(max(0, cy - half))
            c, d = int(min(W, cx + half)), int(min(H, cy + half))
            if c - a < 32 or d - b < 32:
                continue
            crop = frame[b:d, a:c]
            dets = self.objects(crop, classes={PHONE, BOOK}, conf=max(0.15, self.s.object_conf - 0.08))
            papers = [(bx, t) for bx, t in p.memory.get("papers", []) if now - t < 1.0]
            for det in dets:
                box = det.box + np.array([a, b, a, b], np.float32)
                if det.cls == PHONE:
                    p.memory["phone_seen"] = now
                    found.append(Det(box, det.score, PHONE))
                else:
                    papers.append((box, now))
            p.memory["papers"] = papers
        return found

    def _passing_rule(self, frame, people, now):
        info = {}
        for p in people:
            if p.kpts is None:
                continue
            lsh, rsh = self._pt(p, LSH), self._pt(p, RSH)
            if lsh is None or rsh is None:
                continue
            sw = max(abs(lsh[0] - rsh[0]), 12.0)
            wrists = [w for w in (self._pt(p, LWR), self._pt(p, RWR)) if w is not None]
            info[p.id] = (p, sw, wrists, ((lsh[0] + rsh[0]) / 2, (lsh[1] + rsh[1]) / 2))
        active = {p.id: False for p in people}
        ids = list(info)
        for i, a in enumerate(ids):
            pa, swa, wa, ca = info[a]
            for b in ids[i + 1:]:
                pb, swb, wb, _ = info[b]
                near = 0.35 * (swa + swb) / 2
                if any(self._dist(x, y) < near for x in wa for y in wb):
                    active[a] = active[b] = True
            for w in wa:
                if self._dist(w, ca) > 1.3 * swa:              # arm stretched out
                    for o in people:
                        if o.id != a and self._inside(w, o.box, 0.15) and not self._inside(w, pa.box, 0.05):
                            active[a] = True
        out = []
        for p in people:
            hit, dur = self._held(p, "pass", active.get(p.id, False), now, 0.6)
            if hit:
                out += self._report(frame, p, "PASSING", dur, now)
        return out

    # ------------------------------------------------------------------
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

    def _draw(self, img, people, phones, now):
        th = max(1, img.shape[1] // 800)
        for p in people:
            x1, y1, x2, y2 = p.box.astype(int)
            flagged = now < p.flag_until
            color = (79, 84, 240) if flagged else (113, 191, 47)
            cv2.rectangle(img, (x1, y1), (x2, y2), color, (3 if flagged else 1) * th)
            if p.kpts is not None:
                for a, b in BONES:
                    pa, pb = self._pt(p, a), self._pt(p, b)
                    if pa and pb:
                        cv2.line(img, (int(pa[0]), int(pa[1])), (int(pb[0]), int(pb[1])), (255, 190, 80), th)
            label = p.student.usn if p.student else f"#{p.id}"
            if flagged:
                label += f"  {p.flag_text}"
            (tw, tht), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5 * th, th)
            cv2.rectangle(img, (x1, y1 - tht - 8), (x1 + tw + 8, y1), color, -1)
            cv2.putText(img, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * th, (255, 255, 255), th)
        for ph in phones:
            x1, y1, x2, y2 = ph.box.astype(int)
            cv2.rectangle(img, (x1, y1), (x2, y2), (60, 60, 255), 2 * th)
            cv2.putText(img, "PHONE", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55 * th, (60, 60, 255), th)
        return img


def _save(path, img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if ok:
        buf.tofile(path)
