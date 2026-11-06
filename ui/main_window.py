"""Main window: sidebar navigation, top status bar, shared camera worker."""
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from classeye import __version__
from classeye.classrooms import ClassRepository
from classeye.settings import MODEL_FILES, model_path
from .pages import AttendancePage, CamerasPage, ClassesPage, ExamPage, ReportsPage
from .theme import QSS
from .workers import Models, VideoWorker

NAV = [("📷", CamerasPage), ("👥", ClassesPage), ("✅", AttendancePage), ("🛡", ExamPage), ("📊", ReportsPage)]


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.repo = ClassRepository()
        self.models = Models(settings)
        self.worker = None
        self.camera_name = ""
        self.setWindowTitle(f"ClassEye {__version__} - Smart Attendance & Exam Monitoring")
        self.resize(1440, 860)
        self.setStyleSheet(QSS)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- sidebar ----
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(230)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 12)
        brand = QLabel("ClassEye")
        brand.setObjectName("Brand")
        sub = QLabel("Smart Attendance & Exam AI")
        sub.setObjectName("BrandSub")
        sl.addWidget(brand)
        sl.addWidget(sub)
        self.nav_group = QButtonGroup(self)
        self.stack = QStackedWidget()
        self.pages = []
        for i, (icon, cls) in enumerate(NAV):
            page = cls(self)
            self.pages.append(page)
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(20, 16, 20, 16)
            wl.addWidget(page)
            self.stack.addWidget(wrap)
            b = QPushButton(f"  {icon}   {cls.title.replace('&', '&&')}")   # && shows a real "&"
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=i: self.go(n))
            self.nav_group.addButton(b, i)
            sl.addWidget(b)
        sl.addStretch(1)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("BrandSub")
        sl.addWidget(ver)
        outer.addWidget(side)

        # ---- top bar + pages ----
        main = QVBoxLayout()
        main.setSpacing(0)
        top = QFrame()
        top.setObjectName("TopBar")
        top.setFixedHeight(60)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(22, 0, 22, 0)
        self.page_title = QLabel("")
        self.page_title.setObjectName("PageTitle")
        self.live_pill = QLabel("")
        self.live_pill.setObjectName("PillLive")
        self.live_pill.hide()
        self.cam_pill = QLabel("●  No camera")
        self.cam_pill.setObjectName("Pill")
        self.fps_pill = QLabel("")
        self.fps_pill.setObjectName("Pill")
        self.fps_pill.hide()
        tl.addWidget(self.page_title)
        tl.addStretch(1)
        for w in (self.live_pill, self.fps_pill, self.cam_pill):
            tl.addWidget(w)
        main.addWidget(top)
        main.addWidget(self.stack, 1)
        outer.addLayout(main, 1)

        self.cameras, self.classes, self.attendance, self.exam, self.reports = self.pages
        self.classes_changed()
        self.go(0)
        QTimer.singleShot(300, self._check_models)

    # ------------------------------------------------------------------
    def go(self, i):
        self.stack.setCurrentIndex(i)
        self.nav_group.button(i).setChecked(True)
        self.page_title.setText(NAV[i][1].title)
        if self.pages[i] is self.reports:
            self.reports.refresh()

    def toast(self, msg, ms=5000):
        self.statusBar().showMessage(msg, ms)

    def set_live(self, mode):
        if mode:
            self.live_pill.setText(f"●  {mode} LIVE")
            self.live_pill.show()
        else:
            self.live_pill.hide()

    def classes_changed(self):
        page = getattr(self, "attendance", None)    # pages are still being created at startup
        if page is not None:
            page.refresh_classes(self.repo.list())

    def reports_changed(self):
        self.reports.refresh()

    def current_frame(self):
        return None if self.worker is None or self.worker.last_frame is None else self.worker.last_frame.copy()

    def _check_models(self):
        missing = [f for k, f in MODEL_FILES.items() if not os.path.exists(model_path(k))]
        if missing:
            QMessageBox.warning(self, "AI models missing",
                                "These model files are missing from the 'models' folder:\n\n" + "\n".join(missing) +
                                "\n\nRun setup.bat (or: python tools/get_models.py) once with internet.")

    # ------------------------------------------------------------------
    def connect_camera(self, source, name):
        self.disconnect_camera()
        try:
            self.models.ensure_face()
        except Exception as e:
            QMessageBox.critical(self, "Face models", f"Could not load face models: {e}")
            return
        self.camera_name = name
        w = VideoWorker(self.models, source, self.settings)
        w.frame.connect(self._frame)
        w.fps.connect(lambda f: (self.fps_pill.setText(f"{f:.0f} FPS"), self.fps_pill.show()))
        w.status.connect(self.toast)
        w.failed.connect(self._camera_failed)
        w.attendance_tick.connect(self.attendance.on_tick)
        w.attendance_done.connect(self.attendance.on_done)
        w.incident.connect(self.exam.on_incident)
        w.people.connect(self.exam.on_frame_stats)
        w.finished.connect(self._worker_finished)
        self.worker = w
        self.cam_pill.setText(f"●  Connecting: {name}")
        w.start()

    def disconnect_camera(self):
        w = self.worker
        if w is None:
            return
        if w.mode == "exam":
            self.exam.toggle()
        w.stop()
        w.wait(3000)

    def _frame(self, img):
        if self.cam_pill.objectName() != "PillOk":
            self.cam_pill.setObjectName("PillOk")
            self.cam_pill.setStyle(self.cam_pill.style())
        self.cam_pill.setText(f"●  {self.camera_name}")
        page = self.stack.currentWidget().layout().itemAt(0).widget()
        video = getattr(page, "video", None)
        if video is not None:
            video.show_image(img)

    def _camera_failed(self, msg):
        QMessageBox.warning(self, "Camera", msg + "\n\nCheck that the camera is on, on the same Wi-Fi, "
                            "and not used by another app (Zoom, Camera, Teams).")

    def _worker_finished(self):
        if self.sender() is not self.worker:
            return
        self.worker = None
        self.cam_pill.setObjectName("Pill")
        self.cam_pill.setStyle(self.cam_pill.style())
        self.cam_pill.setText("●  No camera")
        self.fps_pill.hide()
        self.set_live(None)
        for p in self.pages:
            v = getattr(p, "video", None)
            if v is not None:
                v.clear_video()

    def closeEvent(self, e):
        if self.worker is not None:
            if self.worker.mode == "exam" and self.exam.incidents:
                self.exam.save()
            self.worker.stop()
            self.worker.wait(3000)
        e.accept()
