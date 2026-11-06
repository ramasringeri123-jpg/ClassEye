"""Automated checks for ClassEye's logic (no camera or AI model files needed).

    python tests/test_classeye.py
"""
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np
from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classeye.attendance import AttendanceScan  # noqa: E402
from classeye.cameras import parse_source  # noqa: E402
from classeye.classrooms import ClassRepository, FaceGallery, Student, build_gallery  # noqa: E402
from classeye.detector import Det, decode  # noqa: E402
from classeye.exam import ExamMonitor  # noqa: E402
from classeye.faces import DetectedFace  # noqa: E402
from classeye.reports import write_attendance, write_exam_report  # noqa: E402
from classeye.settings import Settings  # noqa: E402

rng = np.random.default_rng(7)
PASSED = []


def check(name):
    def wrap(fn):
        def run():
            fn()
            PASSED.append(name)
            print(f"  PASS  {name}")
        return run
    return wrap


def unit(v):
    return (v / np.linalg.norm(v)).astype(np.float32)


def jitter(v, amount=0.25):
    return unit(v + amount * rng.normal(size=128) / np.sqrt(128) * 4)


def fake_gallery(n, per=3, class_name="AIML A"):
    ids = [unit(rng.normal(size=128)) for _ in range(n)]
    studs = [Student(f"4AL22AI{i:03d}", f"Student {i}", "aiml-a", class_name) for i in range(n)]
    vecs, owner = [], []
    for i, base in enumerate(ids):
        for _ in range(per):
            vecs.append(jitter(base, 0.15))
            owner.append(i)
    return FaceGallery(studs, np.stack(vecs), owner), ids, studs


# ---------------------------------------------------------------------------
@check("classrooms: create, rename, students, photos, delete")
def t_classrooms():
    root = tempfile.mkdtemp()
    repo = ClassRepository(root)
    a = repo.create("AIML A Section")
    repo.create("CSE B")
    try:
        repo.create("aiml a section")
        raise AssertionError("duplicate class name allowed")
    except ValueError:
        pass
    repo.rename(a.id, "AIML B Section")
    assert repo.get(a.id).name == "AIML B Section"          # id stays, name changes
    s = repo.add_student(a.id, " 4al22ai001 ", "Asha Rao")
    assert s.usn == "4AL22AI001"
    repo.add_student(a.id, "4AL22AI001", "Asha R")            # same USN -> update, no duplicate
    assert [x.name for x in repo.students(a.id)] == ["Asha R"]
    img = np.full((2000, 1500, 3), 120, np.uint8)
    p = repo.add_photo(a.id, "4AL22AI001", image=img)
    assert os.path.exists(p) and max(cv2.imread(p).shape[:2]) == 1600   # big photos shrunk
    repo.add_photo(a.id, "4AL22AI001", image=img)
    assert len(repo.students(a.id)[0].photos) == 2
    repo.remove_student(a.id, "4AL22AI001")
    assert repo.students(a.id) == []
    repo.delete(a.id)
    assert [c.name for c in repo.list()] == ["CSE B"]
    shutil.rmtree(root)


@check("classrooms: import CSV with photo folder")
def t_import():
    root = tempfile.mkdtemp()
    repo = ClassRepository(os.path.join(root, "classes"))
    c = repo.create("ECE A")
    sheet = os.path.join(root, "list.csv")
    with open(sheet, "w", encoding="utf-8") as f:
        f.write("﻿USN,Student Name\n4al22ec001,Ravi\n4AL22EC002,Meena\n,blank\n")
    photos = os.path.join(root, "pics")
    os.makedirs(os.path.join(photos, "4AL22EC002"))
    cv2.imwrite(os.path.join(photos, "4AL22EC001.jpg"), np.zeros((50, 50, 3), np.uint8))
    cv2.imwrite(os.path.join(photos, "4AL22EC002", "a.png"), np.zeros((50, 50, 3), np.uint8))
    assert repo.import_students(c.id, sheet, photos) == 2
    st = {s.usn: s for s in repo.students(c.id)}
    assert len(st["4AL22EC001"].photos) == 1 and len(st["4AL22EC002"].photos) == 1
    shutil.rmtree(root)


@check("gallery: build with cache, warnings for bad photos, merge across classes")
def t_gallery():
    root = tempfile.mkdtemp()
    repo = ClassRepository(root)
    c = repo.create("AIML A")
    for usn in ("A1", "A2", "A3"):
        repo.add_student(c.id, usn, usn)
    repo.add_photo(c.id, "A1", image=np.full((200, 200, 3), 200, np.uint8))
    repo.add_photo(c.id, "A2", image=np.zeros((200, 200, 3), np.uint8))   # "no face"

    class StubEngine:
        calls = 0

        def main_face(self, img):
            StubEngine.calls += 1
            if img.mean() < 1:
                return None
            r = np.zeros(15, np.float32)
            r[:4] = [50, 50, 100, 100]
            r[4:14] = [80, 90, 120, 90, 100, 110, 85, 130, 115, 130]
            return r

        def embed(self, img, row):
            return unit(np.arange(128, dtype=np.float32) + row[0])

    g, studs, warn = build_gallery(repo, c.id, StubEngine())
    assert [s.usn for s in g.students] == ["A1"] and len(g.vectors) == 2 and len(studs) == 3
    assert any("A2" in w for w in warn) and any("A3" in w and "no photo" in w for w in warn)
    calls = StubEngine.calls
    build_gallery(repo, c.id, StubEngine())
    assert StubEngine.calls == calls, "embedding cache not used"
    g2, _, _ = fake_gallery(4, class_name="CSE B")
    merged = FaceGallery.merge([g, g2])
    assert len(merged) == 5 and merged.best_per_student([g2.vectors[0]]).shape == (1, 5)
    st, sim = merged.identify(g2.vectors[0], 0.4, 0.05)
    assert st.class_name == "CSE B"
    shutil.rmtree(root)


@check("attendance: present / absent / stranger / look-alike / one-face-one-student")
def t_attendance():
    g, ids, studs = fake_gallery(8)
    no_photo = Student("4AL22AI099", "New Student")
    scan = AttendanceScan("AIML A", g, studs + [no_photo], 0.40, 0.05, 3)
    frame = np.zeros((720, 1280, 3), np.uint8)
    here = [0, 1, 2, 3, 4]
    for f in range(6):
        faces = [DetectedFace((40 + 140 * k, 80, 60, 60), 0.9, None, jitter(ids[i])) for k, i in enumerate(here)]
        faces.append(DetectedFace((20, 600, 60, 60), 0.9, None, unit(rng.normal(size=128))))     # stranger
        faces.append(DetectedFace((900, 600, 14, 14), 0.9, None, None))                           # far away
        faces.append(DetectedFace((1000, 80, 60, 60), 0.9, None, jitter(ids[0])))               # duplicate face
        if f == 0:
            faces.append(DetectedFace((1100, 300, 60, 60), 0.9, None, jitter(ids[6])))          # seen once
        scan.feed(frame, faces)
    present = {m.usn for m in scan.present()}
    assert present == {studs[i].usn for i in here}, present
    assert scan.marks[studs[0].usn].hits == 6        # duplicate never double-counted
    assert scan.marks[studs[6].usn].hits == 1 and not scan.is_present(scan.marks[studs[6].usn])
    s = scan.summary()
    assert s["present"] == 5 and s["absent"] == 4 and s["no_photo"] == 1 and s["too_small"] == 6

    twin = unit(ids[0] + 0.01 * rng.normal(size=128))
    g2 = FaceGallery([studs[0], studs[1]], np.stack([ids[0], twin]), [0, 1])
    t = AttendanceScan("X", g2, [studs[0], studs[1]], 0.4, 0.05, 1)
    t.feed(frame, [DetectedFace((0, 0, 50, 50), 0.9, None, jitter(ids[0], 0.05))])
    assert t.present() == [], "look-alike guessed"
    globals()["_scan"] = scan


# ---------------------------------------------------------------------------
@check("detector: YOLO output decoding (detection + pose)")
def t_decode():
    out = np.zeros((1, 84, 8400), np.float32)
    out[0, :4, 5] = [320, 320, 40, 80]
    out[0, 4 + 67, 5] = 0.9
    out[0, :4, 6] = [321, 322, 41, 78]
    out[0, 4 + 67, 6] = 0.8                      # duplicate -> removed by NMS
    out[0, :4, 9] = [100, 100, 50, 150]
    out[0, 4, 9] = 0.95                         # person, filtered by classes
    dets = decode(out, 0.5, (0, 140), (720, 1280), 0.3, 0.45, {67})
    assert len(dets) == 1 and dets[0].cls == 67
    assert np.allclose(dets[0].box, [600, 280, 680, 440], atol=1)
    pose = np.zeros((1, 56, 8400), np.float32)
    pose[0, :4, 3] = [320, 320, 100, 200]
    pose[0, 4, 3] = 0.9
    pose[0, 5:, 3] = np.tile([300, 250, 0.9], 17)
    d = decode(pose, 1.0, (0, 0), (640, 640), 0.3, 0.45)
    assert len(d) == 1 and d[0].kpts.shape == (17, 3) and abs(d[0].kpts[0, 1] - 250) < 1e-3


# ---------------------------------------------------------------------------
def body(box, nose_dx=0.0, face=True, flip=False, wrists=None, hips=True, sw=60):
    """Synthetic seated student facing the camera."""
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2
    sy = y1 + 0.35 * (y2 - y1)
    k = np.zeros((17, 3), np.float32)

    def put(i, x, y):
        k[i] = [x, y, 0.95]
    if face:
        put(0, cx + nose_dx * sw, y1 + 0.18 * (y2 - y1))
        put(1, cx + 8 + nose_dx * sw, y1 + 0.15 * (y2 - y1))
        put(2, cx - 8 + nose_dx * sw, y1 + 0.15 * (y2 - y1))
    put(3, cx + 15, y1 + 0.17 * (y2 - y1))
    put(4, cx - 15, y1 + 0.17 * (y2 - y1))
    left, right = (cx - sw / 2, cx + sw / 2) if flip else (cx + sw / 2, cx - sw / 2)
    put(5, left, sy)                      # left shoulder appears on image RIGHT when facing camera
    put(6, right, sy)
    put(7, left + (6 if not flip else -6), sy + 40)
    put(8, right - (6 if not flip else -6), sy + 40)
    put(9, cx + 25, sy + 75)              # wrists on the desk, well below chest
    put(10, cx - 25, sy + 75)
    if hips:
        put(11, cx + 22, y2 - 10)
        put(12, cx - 22, y2 - 10)
    for i, (x, y) in (wrists or {}).items():
        put(i, x, y)
    return Det(np.array(box, np.float32), 0.9, 0, k)


class Fake:
    def __init__(self):
        self.out = []

    def __call__(self, frame, classes=None, conf=None):
        return self.out


def simulate(scene, seconds=8, fps=10, phones=None, enabled=None):
    pose, obj = Fake(), Fake()
    folder = tempfile.mkdtemp()
    mon = ExamMonitor(Settings(), pose, obj, out_dir=folder, enabled=enabled)
    frame = np.full((720, 1280, 3), 90, np.uint8)
    for i in range(int(seconds * fps)):
        t = i / fps
        pose.out = scene(t)
        obj.out = phones(t) if phones else []
        mon.process(frame.copy(), now=1000 + t)
    return mon, folder


A = (100, 200, 260, 560)
B = (300, 200, 460, 560)
FRONT = (90, 380, 280, 720)


def kinds(m):
    return [i.kind for i in m.incidents]


@check("exam: a calm class raises no alerts")
def t_calm():
    m, d = simulate(lambda t: [body(A), body(B)], 12)
    assert kinds(m) == [], kinds(m)
    shutil.rmtree(d)


@check("exam: mobile phone, attributed to the right student")
def t_phone():
    m, d = simulate(lambda t: [body(A), body(B)], 4,
                    phones=lambda t: [Det(np.array([370, 420, 395, 470], np.float32), 0.7, 67)] if t > 1 else [])
    assert kinds(m) == ["PHONE"] and m.incidents[0].track_id == 2, (kinds(m), m.incidents)
    assert os.path.exists(m.incidents[0].photo) and os.path.exists(m.incidents[0].crop)
    shutil.rmtree(d)


@check("exam: taking a chit from the pocket")
def t_pocket():
    m, d = simulate(lambda t: [body(A, wrists={9: (204, 545)} if t > 2 else None), body(B)], 6)
    assert kinds(m) == ["CHIT"], kinds(m)
    shutil.rmtree(d)


@check("exam: reaching inside the sleeve")
def t_sleeve():
    # right wrist goes to the left elbow (left elbow is at cx+30+6, sy+40)
    m, d = simulate(lambda t: [body(A, wrists={10: (216, 366)} if t > 2 else None), body(B)], 6)
    assert kinds(m) == ["CHIT"], kinds(m)
    shutil.rmtree(d)


@check("exam: turning back (shoulders reversed)")
def t_back():
    m, d = simulate(lambda t: [body(A, flip=3 < t < 6, face=not (3 < t < 6)), body(B)], 8)
    assert kinds(m) == ["TURN_BACK"], kinds(m)
    shutil.rmtree(d)


@check("exam: peeping into the front student's paper")
def t_peep():
    def scene(t):
        a = body(A)
        if t > 3:
            a.kpts[0, :2] = [185, 470]       # head pushed down into the front student's space
        return [a, body(FRONT)]
    m, d = simulate(scene, 7)
    assert "PEEP_FRONT" in kinds(m), kinds(m)
    shutil.rmtree(d)


@check("exam: looking sideways at a neighbour (long) vs a quick glance (ignored)")
def t_side():
    m, d = simulate(lambda t: [body(A, nose_dx=0.75 if 4 <= t <= 8 else 0), body(B)], 10)
    assert kinds(m) == ["SIDE_LOOK"], kinds(m)
    shutil.rmtree(d)
    m, d = simulate(lambda t: [body(A, nose_dx=0.75 if 4 <= t <= 4.8 else 0), body(B)], 10)
    assert kinds(m) == [], kinds(m)
    shutil.rmtree(d)


@check("exam: passing something between neighbours")
def t_pass():
    def scene(t):
        if 3 <= t <= 5:
            return [body(A, wrists={9: (281, 430)}), body(B, wrists={10: (284, 432)})]
        return [body(A), body(B)]
    m, d = simulate(scene, 7)
    assert kinds(m).count("PASSING") == 2, kinds(m)
    shutil.rmtree(d)


@check("exam: alert repeat limit and disabled rules")
def t_limits():
    m, d = simulate(lambda t: [body(A), body(B)], 30,
                    phones=lambda t: [Det(np.array([370, 420, 395, 470], np.float32), 0.7, 67)],
                    enabled={"PHONE"})
    assert kinds(m) == ["PHONE", "PHONE"], kinds(m)   # 20 s repeat limit
    shutil.rmtree(d)


@check("exam: identifies students with photos from every class")
def t_identify():
    g1, ids1, _ = fake_gallery(3, class_name="AIML A")
    g2, ids2, _ = fake_gallery(3, class_name="CSE B")
    merged = FaceGallery.merge([g1, g2])

    class FaceStub:
        def detect(self, frame):
            return [DetectedFace((360, 210, 40, 40), 0.9, None, jitter(ids2[1], 0.1))]

    pose, obj = Fake(), Fake()
    folder = tempfile.mkdtemp()
    mon = ExamMonitor(Settings(), pose, obj, FaceStub(), merged, folder)
    frame = np.zeros((720, 1280, 3), np.uint8)
    for i in range(30):
        pose.out = [body(A), body(B)]
        obj.out = [Det(np.array([370, 420, 395, 470], np.float32), 0.7, 67)] if i > 5 else []
        mon.process(frame, now=1000 + i / 10)
    inc = mon.incidents[0]
    assert inc.class_name == "CSE B" and inc.usn == merged.students[4].usn, inc
    globals()["_incidents"] = mon.incidents
    shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------------------
@check("reports: attendance sheet, absentees, register, exam report")
def t_reports():
    out = tempfile.mkdtemp()
    scan = globals()["_scan"]
    scan.marks[scan.gallery.students[0].usn].snapshot = np.full((120, 110, 3), 150, np.uint8)
    path, reg = write_attendance(scan, out, "Maths", "Dr. Rao")
    wb = load_workbook(path)
    ws = wb["Attendance"]
    status = {ws.cell(row=r, column=3).value: ws.cell(row=r, column=5).value for r in range(6, ws.max_row + 1)}
    assert list(status.values()).count("Present") == 5 and len(wb["Absentees"]._cells) > 0
    assert len(ws._images) >= 5   # a face photo for each recognised student
    write_attendance(scan, out)
    r = load_workbook(reg).active
    assert r.max_column == 7 and r.cell(row=2, column=6).value in ("P", "A")

    # exam report from a real run
    m, d = simulate(lambda t: [body(A), body(B)], 3,
                    phones=lambda t: [Det(np.array([370, 420, 395, 470], np.float32), 0.7, 67)])
    m.incidents[0].usn, m.incidents[0].name, m.incidents[0].class_name = "4AL22AI001", "Asha", "AIML B"
    p = write_exam_report(m.incidents, out, "Hall 2", "IA-2")
    ex = load_workbook(p)["Incidents"]
    assert ex.cell(row=5, column=3).value == "4AL22AI001" and ex.cell(row=5, column=6).value == "Using a mobile phone"
    assert len(ex._images) == 1
    print("        sample files:", os.path.basename(path), "|", os.path.basename(p))
    globals()["_report_dir"] = out


@check("cameras: address parsing")
def t_parse():
    assert parse_source("1") == 1
    assert parse_source("192.168.43.1:8080") == "http://192.168.43.1:8080/video"
    assert parse_source("10.0.0.5") == "http://10.0.0.5:8080/video"
    assert parse_source("rtsp://a:b@1.2.3.4:554/s") == "rtsp://a:b@1.2.3.4:554/s"
    assert parse_source("") is None


if __name__ == "__main__":
    print("ClassEye tests")
    for fn in [t_classrooms, t_import, t_gallery, t_attendance, t_decode, t_calm, t_phone, t_pocket,
               t_sleeve, t_back, t_peep, t_side, t_pass, t_limits, t_identify, t_reports, t_parse]:
        fn()
    print(f"ALL {len(PASSED)} TESTS PASSED")
