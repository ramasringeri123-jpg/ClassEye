"""Background threads so the window never freezes."""
import time
import traceback

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from classeye.attendance import AttendanceScan
from classeye.cameras import LiveStream, find_local_cameras, scan_network
from classeye.faces import FaceEngine
from classeye.settings import model_path


def to_qimage(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class Models:
    """Loaded once, shared by every page."""

    def __init__(self, settings):
        self.settings = settings
        self.face = None
        self.pose = None
        self.objects = None

    def ensure_face(self):
        if self.face is None:
            s = self.settings
            self.face = FaceEngine(model_path("face_detector"), model_path("face_recognizer"),
                                   s.face_min_score, s.face_min_size, s.face_upscale)
        return self.face

    def ensure_exam(self):
        if self.pose is None:
            from classeye.detector import YoloModel
            self.pose = YoloModel(model_path("pose"), conf=self.settings.person_conf)
            self.objects = YoloModel(model_path("objects"), conf=min(0.25, self.settings.object_conf))
        return self.pose, self.objects


class Job(QThread):
    """Run any function in the background: finished(result) or failed(message)."""
    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs

    def run(self):
        try:
            self.finished_ok.emit(self.fn(*self.args, **self.kwargs))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


class CameraScan(QThread):
    found = Signal(list)
    progress = Signal(str)

    def __init__(self, include_network=True):
        super().__init__()
        self.include_network = include_network

    def run(self):
        cams = []
        self.progress.emit("Looking for cameras connected to this computer...")
        try:
            cams += find_local_cameras()
        except Exception:
            traceback.print_exc()
        self.found.emit(list(cams))
        if self.include_network:
            self.progress.emit("Searching the Wi-Fi network for cameras...")
            try:
                cams += scan_network(lambda d, t: self.progress.emit(
                    f"Searching the Wi-Fi network for cameras... {int(100 * d / max(1, t))}%"))
            except Exception:
                traceback.print_exc()
        self.progress.emit(f"Found {len(cams)} camera(s)")
        self.found.emit(cams)


class VideoWorker(QThread):
    frame = Signal(QImage)
    fps = Signal(float)
    status = Signal(str)
    failed = Signal(str)
    attendance_tick = Signal(float, list)     # progress 0..1, present names
    attendance_done = Signal(object)          # AttendanceScan
    incident = Signal(object)                 # exam Incident
    people = Signal(int)                      # students currently tracked in exam mode

    def __init__(self, models, source, settings):
        super().__init__()
        self.models, self.source, self.settings = models, source, settings
        self.stream = None
        self.mode = "preview"
        self.show_faces = False
        self.last_frame = None
        self.scan = None
        self.scan_seconds = 45
        self.scan_start = 0.0
        self.monitor = None
        self._alive = True

    # ---- commands (called from the UI thread) ----
    def begin_attendance(self, classroom_name, gallery, students, seconds):
        s = self.settings
        self.scan = AttendanceScan(classroom_name, gallery, students, s.match_threshold,
                                   s.match_margin, s.hits_to_mark_present)
        self.scan_seconds, self.scan_start = seconds, time.time()
        self.mode = "attendance"

    def end_attendance(self):
        if self.mode == "attendance":
            self.mode = "preview"
            self.attendance_done.emit(self.scan)

    def begin_exam(self, monitor):
        self.monitor = monitor
        self.mode = "exam"

    def end_exam(self):
        self.mode = "preview"
        return self.monitor

    def stop(self):
        self._alive = False

    # ---- loop ----
    def run(self):
        self.stream = LiveStream(self.source, self.settings.capture_width, self.settings.capture_height)
        self.status.emit("Connecting to camera...")
        if not self.stream.start():
            self.failed.emit(self.stream.error or "The camera did not send any picture.")
            self.stream.stop()
            return
        self.status.emit("Camera connected")
        last, count, t0 = -1, 0, time.time()
        while self._alive:
            seq, img = self.stream.latest()
            if img is None or seq == last:
                self.msleep(4)
                continue
            last = seq
            self.last_frame = img.copy()
            try:
                img = self._process(img)
            except Exception as e:
                traceback.print_exc()
                self.status.emit(f"Processing error: {e}")
            self.frame.emit(to_qimage(img))
            count += 1
            if time.time() - t0 >= 1:
                self.fps.emit(count / (time.time() - t0))
                count, t0 = 0, time.time()
        self.stream.stop()

    def _process(self, img):
        th = max(1, img.shape[1] // 800)
        if self.mode == "attendance":
            faces = self.models.face.detect(img)
            for face, usn, sim in self.scan.feed(img, faces):
                x, y, w, h = face.box
                if usn:
                    color, text = (113, 191, 47), f"{usn}  {int(sim * 100)}%"
                elif face.vector is None:
                    color, text = (36, 165, 245), "too far"
                else:
                    color, text = (79, 84, 240), "unknown"
                cv2.rectangle(img, (x, y), (x + w, y + h), color, th + 1)
                cv2.rectangle(img, (x, y - 18 * th), (x + max(w, 9 * len(text) * th), y), color, -1)
                cv2.putText(img, text, (x + 3, y - 5 * th), cv2.FONT_HERSHEY_SIMPLEX, 0.45 * th, (255, 255, 255), th)
            elapsed = time.time() - self.scan_start
            self.attendance_tick.emit(min(1.0, elapsed / max(1, self.scan_seconds)),
                                      [f"{m.usn}  ·  {m.name}" for m in self.scan.present()])
            if elapsed >= self.scan_seconds:
                self.end_attendance()
        elif self.mode == "exam" and self.monitor is not None:
            img, new = self.monitor.process(img)
            self.people.emit(self.monitor.people_now)
            for inc in new:
                self.incident.emit(inc)
        elif self.show_faces and self.models.face is not None:
            for f in self.models.face.detect(img, with_vectors=False):
                x, y, w, h = f.box
                cv2.rectangle(img, (x, y), (x + w, y + h), (255, 140, 79), th + 1)
        return img
