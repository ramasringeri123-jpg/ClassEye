"""The app's pages: Cameras, Classes, Attendance, Exam, Reports."""
import os
import subprocess
import sys
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from classeye.cameras import parse_source
from classeye.classrooms import FaceGallery, build_gallery, read_image
from classeye.history import class_report, load_sessions, overview, record_session
from classeye.reports import write_attendance, write_class_report, write_exam_report, write_shortage_report
from classeye.settings import reports_dir
from .widgets import Card, Stat, VideoView, muted, row
from .workers import CameraScan, Job, to_qimage


def open_file(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def button(text, kind="", slot=None):
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if slot:
        b.clicked.connect(slot)
    b.setCursor(Qt.PointingHandCursor)
    return b


def table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setStretchLastSection(True)
    t.setShowGrid(False)
    return t


# =============================================================================
class CamerasPage(QWidget):
    title = "Cameras"

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.scanner = None
        lay = QHBoxLayout(self)
        lay.setSpacing(16)

        left = QVBoxLayout()
        self.video = VideoView("Pick a camera and press Connect")
        left.addWidget(self.video, 1)
        lay.addLayout(left, 3)

        side = QVBoxLayout()
        find = Card("Find cameras")
        find.body.addWidget(muted("Finds webcams and USB cameras on this computer, plus Wi-Fi cameras and "
                                  "phones (IP Webcam / DroidCam) on the same network."))
        self.net_chk = QCheckBox("Also search the Wi-Fi network")
        self.net_chk.setChecked(True)
        find.body.addWidget(self.net_chk)
        self.scan_btn = button("Scan for cameras", "Primary", self.scan)
        find.body.addWidget(self.scan_btn)
        self.scan_status = muted("")
        find.body.addWidget(self.scan_status)
        self.cam_list = QListWidget()
        self.cam_list.setMinimumHeight(160)
        self.cam_list.itemDoubleClicked.connect(lambda _: self.connect_selected())
        find.body.addWidget(self.cam_list)
        find.body.addLayout(row(button("Connect", "Success", self.connect_selected),
                                button("Disconnect", "", self.app.disconnect_camera)))
        side.addWidget(find)

        manual = Card("Add a camera by address")
        manual.body.addWidget(muted("Phone with IP Webcam: 192.168.1.7:8080\n"
                                    "CCTV: rtsp://user:password@192.168.1.20:554/stream1"))
        self.addr = QLineEdit()
        self.addr.setPlaceholderText("IP address, rtsp:// or http:// link")
        manual.body.addWidget(self.addr)
        manual.body.addWidget(button("Connect to this address", "", self.connect_address))
        side.addWidget(manual)
        side.addStretch(1)
        lay.addLayout(side, 2)

    def scan(self):
        if self.scanner and self.scanner.isRunning():
            return
        self.cam_list.clear()
        self.scan_btn.setEnabled(False)
        self.scanner = CameraScan(self.net_chk.isChecked())
        self.scanner.progress.connect(self.scan_status.setText)
        self.scanner.found.connect(self._show_found)
        self.scanner.finished.connect(lambda: self.scan_btn.setEnabled(True))
        self.scanner.start()

    def _show_found(self, cams):
        self.cam_list.clear()
        for c in cams:
            it = QListWidgetItem(c.label)
            it.setData(Qt.UserRole, c)
            self.cam_list.addItem(it)
        if cams:
            self.cam_list.setCurrentRow(0)

    def connect_selected(self):
        it = self.cam_list.currentItem()
        if it is None:
            QMessageBox.information(self, "Cameras", "Scan and select a camera first.")
            return
        cam = it.data(Qt.UserRole)
        self.app.connect_camera(cam.source, cam.name)

    def connect_address(self):
        src = parse_source(self.addr.text())
        if src is None:
            QMessageBox.information(self, "Cameras", "Type the camera address first.")
            return
        self.app.connect_camera(src, str(self.addr.text()).strip())


# =============================================================================
class ClassesPage(QWidget):
    title = "Classes & Students"

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.repo = app.repo
        lay = QHBoxLayout(self)
        lay.setSpacing(16)

        # ---- class list ----
        cl = Card("Classrooms")
        self.class_list = QListWidget()
        self.class_list.currentItemChanged.connect(lambda *_: self.load_students())
        cl.body.addWidget(self.class_list, 1)
        cl.body.addLayout(row(button("+ New class", "Primary", self.new_class),
                              button("Rename", "", self.rename_class)))
        cl.body.addWidget(button("Delete class", "Danger", self.delete_class))
        cl.setMaximumWidth(300)
        lay.addWidget(cl, 1)

        # ---- students ----
        right = QVBoxLayout()
        st = Card("Students")
        self.class_title = QLabel("Select a class")
        self.class_title.setObjectName("PageTitle")
        st.body.addWidget(self.class_title)
        self.table = table(["Photo", "USN", "Name", "Photos"])
        self.table.setIconSize(QPixmap(56, 56).size())
        self.table.verticalHeader().setDefaultSectionSize(62)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        st.body.addWidget(self.table, 1)
        st.body.addLayout(row(button("+ Add student", "Primary", self.add_student),
                              button("Add photos from files", "", self.add_photo_files),
                              button("Capture from camera", "Success", self.capture_photo),
                              None,
                              button("Import list (CSV/Excel)", "", self.import_list),
                              button("Remove student", "Danger", self.remove_student)))
        right.addWidget(st, 1)
        self.health = Card("Dataset check")
        self.health_text = muted("Select a class to check its photos.")
        self.health.body.addWidget(self.health_text)
        self.health.body.addWidget(button("Check photos now", "", self.check_dataset))
        right.addWidget(self.health)
        lay.addLayout(right, 3)
        self.refresh()

    # ---- classes ----
    def refresh(self, select_id=None):
        current = select_id or self.current_id()
        self.class_list.blockSignals(True)
        self.class_list.clear()
        for c in self.repo.list():
            it = QListWidgetItem(f"{c.name}   ({len(self.repo.students(c.id))})")
            it.setData(Qt.UserRole, c.id)
            self.class_list.addItem(it)
            if c.id == current:
                self.class_list.setCurrentItem(it)
        self.class_list.blockSignals(False)
        if self.class_list.currentItem() is None and self.class_list.count():
            self.class_list.setCurrentRow(0)
        self.load_students()
        self.app.classes_changed()

    def current_id(self):
        it = self.class_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def new_class(self):
        name, ok = QInputDialog.getText(self, "New class", "Class name (e.g. AIML B Section):")
        if ok and name.strip():
            try:
                c = self.repo.create(name)
                self.refresh(c.id)
            except ValueError as e:
                QMessageBox.warning(self, "New class", str(e))

    def rename_class(self):
        cid = self.current_id()
        if not cid:
            return
        old = self.repo.get(cid).name
        name, ok = QInputDialog.getText(self, "Rename class", "New name:", text=old)
        if ok and name.strip() and name.strip() != old:
            try:
                self.repo.rename(cid, name)
                self.refresh(cid)
            except ValueError as e:
                QMessageBox.warning(self, "Rename class", str(e))

    def delete_class(self):
        cid = self.current_id()
        if not cid:
            return
        c = self.repo.get(cid)
        n = len(self.repo.students(cid))
        if QMessageBox.question(self, "Delete class",
                                f"Delete '{c.name}' and all {n} students with their photos?\n"
                                "This cannot be undone.") == QMessageBox.Yes:
            self.repo.delete(cid)
            self.refresh()

    # ---- students ----
    def load_students(self):
        cid = self.current_id()
        self.table.setRowCount(0)
        if not cid:
            self.class_title.setText("Create a class to get started")
            return
        c = self.repo.get(cid)
        studs = self.repo.students(cid)
        self.class_title.setText(f"{c.name}  ·  {len(studs)} students")
        for s in studs:
            r = self.table.rowCount()
            self.table.insertRow(r)
            photo = QTableWidgetItem()
            if s.photos:
                pm = QPixmap(s.photos[0])
                if not pm.isNull():
                    photo.setIcon(QIcon(pm.scaled(56, 56, Qt.KeepAspectRatioByExpanding,
                                                  Qt.SmoothTransformation)))
            self.table.setItem(r, 0, photo)
            self.table.setItem(r, 1, QTableWidgetItem(s.usn))
            self.table.setItem(r, 2, QTableWidgetItem(s.name))
            cnt = QTableWidgetItem(str(len(s.photos)))
            if len(s.photos) < 3:
                cnt.setForeground(QColor("#F5A524"))
                cnt.setToolTip("Add at least 3 photos for best accuracy")
            self.table.setItem(r, 3, cnt)
        self.table.setColumnWidth(0, 76)
        self.table.setColumnWidth(1, 150)

    def current_usn(self):
        r = self.table.currentRow()
        return self.table.item(r, 1).text() if r >= 0 and self.table.item(r, 1) else None

    def add_student(self):
        cid = self.current_id()
        if not cid:
            QMessageBox.information(self, "Students", "Create or select a class first.")
            return
        usn, ok = QInputDialog.getText(self, "Add student", "USN:")
        if not ok or not usn.strip():
            return
        name, ok = QInputDialog.getText(self, "Add student", "Full name:")
        if not ok:
            return
        try:
            st = self.repo.add_student(cid, usn, name)
        except ValueError as e:
            QMessageBox.warning(self, "Add student", str(e))
            return
        self.refresh(cid)
        self._select_usn(st.usn)
        QMessageBox.information(self, "Add student",
                                f"{st.name} added.\nNow add 3-5 photos: 'Capture from camera' (best) "
                                "or 'Add photos from files'.")

    def _select_usn(self, usn):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 1).text() == usn:
                self.table.selectRow(r)
                return

    def add_photo_files(self):
        cid, usn = self.current_id(), self.current_usn()
        if not usn:
            QMessageBox.information(self, "Photos", "Select a student in the table first.")
            return
        files, _ = QFileDialog.getOpenFileNames(self, f"Photos of {usn}", "",
                                                "Images (*.jpg *.jpeg *.png *.bmp *.webp)")
        bad = []
        for f in files:
            img = read_image(f)
            if img is None or self.app.models.ensure_face().main_face(img) is None:
                bad.append(os.path.basename(f))
                continue
            self.repo.add_photo(cid, usn, image=img)
        self.refresh(cid)
        self._select_usn(usn)
        if bad:
            QMessageBox.warning(self, "Photos", "No face found in:\n" + "\n".join(bad))

    def capture_photo(self):
        cid, usn = self.current_id(), self.current_usn()
        if not usn:
            QMessageBox.information(self, "Capture", "Select a student in the table first.")
            return
        frame = self.app.current_frame()
        if frame is None:
            QMessageBox.information(self, "Capture", "Connect a camera first (Cameras page).")
            return
        row_ = self.app.models.ensure_face().main_face(frame)
        if row_ is None:
            QMessageBox.warning(self, "Capture", "No face visible. Ask the student to face the camera.")
            return
        x, y, w, h = (int(v) for v in row_[:4])
        H, W = frame.shape[:2]
        p = int(0.7 * max(w, h))
        crop = frame[max(0, y - p):min(H, y + h + p), max(0, x - p):min(W, x + w + p)]
        self.repo.add_photo(cid, usn, image=crop)
        self.refresh(cid)
        self._select_usn(usn)
        self.app.toast(f"Photo saved for {usn}. Take 3-5 with slightly different angles.")

    def remove_student(self):
        cid, usn = self.current_id(), self.current_usn()
        if usn and QMessageBox.question(self, "Remove student",
                                        f"Remove {usn} and their photos?") == QMessageBox.Yes:
            self.repo.remove_student(cid, usn)
            self.refresh(cid)

    def import_list(self):
        cid = self.current_id()
        if not cid:
            QMessageBox.information(self, "Import", "Create or select a class first.")
            return
        sheet, _ = QFileDialog.getOpenFileName(self, "Student list (columns USN and Name)", "",
                                               "Student list (*.csv *.xlsx)")
        if not sheet:
            return
        photos = QFileDialog.getExistingDirectory(self, "Optional: folder with photos named by USN")
        try:
            n = self.repo.import_students(cid, sheet, photos or None)
        except Exception as e:
            QMessageBox.warning(self, "Import", f"Could not import: {e}")
            return
        self.refresh(cid)
        QMessageBox.information(self, "Import", f"Imported {n} students.")

    def check_dataset(self):
        cid = self.current_id()
        if not cid:
            return
        self.health_text.setText("Checking photos...")
        self._job = Job(build_gallery, self.repo, cid, self.app.models.ensure_face())
        self._job.finished_ok.connect(self._show_health)
        self._job.failed.connect(lambda m: self.health_text.setText(f"Check failed: {m}"))
        self._job.start()

    def _show_health(self, result):
        gallery, students, warnings = result
        text = f"{len(gallery)} of {len(students)} students ready for recognition."
        if warnings:
            text += "\n\n" + "\n".join(warnings[:12]) + ("\n..." if len(warnings) > 12 else "")
        else:
            text += "  All photos look good."
        self.health_text.setText(text)


# =============================================================================
class AttendancePage(QWidget):
    title = "Attendance"

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.last_report = None
        lay = QHBoxLayout(self)
        lay.setSpacing(16)

        left = QVBoxLayout()
        self.video = VideoView("Connect a camera on the Cameras page")
        left.addWidget(self.video, 1)
        stats = QHBoxLayout()
        self.s_present, self.s_absent, self.s_total = Stat("Present"), Stat("Absent"), Stat("Students")
        self.s_unknown = Stat("Unknown persons")
        self.s_unknown.value.setStyleSheet("color:#C0392B;")
        for s in (self.s_present, self.s_absent, self.s_total, self.s_unknown):
            stats.addWidget(s)
        left.addLayout(stats)
        lay.addLayout(left, 3)

        side = QVBoxLayout()
        setup = Card("Take attendance")
        form = QFormLayout()
        self.class_box = QComboBox()
        self.subject = QLineEdit()
        self.subject.setPlaceholderText("optional")
        self.teacher = QLineEdit()
        self.teacher.setPlaceholderText("optional")
        self.seconds = QSpinBox()
        self.seconds.setRange(10, 600)
        self.seconds.setSuffix(" seconds")
        self.seconds.setValue(app.settings.scan_seconds)
        form.addRow("Class", self.class_box)
        form.addRow("Subject", self.subject)
        form.addRow("Faculty", self.teacher)
        form.addRow("Scan time", self.seconds)
        setup.body.addLayout(form)
        self.start_btn = button("Start attendance", "Success", self.start)
        self.stop_btn = button("Finish now", "", self.finish)
        self.stop_btn.setEnabled(False)
        setup.body.addLayout(row(self.start_btn, self.stop_btn))
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        setup.body.addWidget(self.progress)
        side.addWidget(setup)

        live = Card("Recognised")
        self.present_list = QListWidget()
        live.body.addWidget(self.present_list)
        side.addWidget(live, 1)
        absent = Card("Absentees")
        self.absent_list = QListWidget()
        absent.body.addWidget(self.absent_list)
        self.unknown_note = QLabel("")
        self.unknown_note.setWordWrap(True)
        self.unknown_note.setStyleSheet("background:#FBE5E3; color:#8E2B20; border-radius:6px; padding:6px 8px;"
                                        " font-weight:600;")
        self.unknown_note.hide()
        absent.body.addWidget(self.unknown_note)
        self.unknown_list = QListWidget()
        self.unknown_list.setIconSize(QPixmap(64, 64).size())
        self.unknown_list.setMaximumHeight(150)
        self.unknown_list.hide()
        absent.body.addWidget(self.unknown_list)
        self.open_btn = button("Open Excel report", "Primary", lambda: open_file(self.last_report))
        self.open_btn.setEnabled(False)
        absent.body.addWidget(self.open_btn)
        side.addWidget(absent, 1)
        lay.addLayout(side, 2)

    def refresh_classes(self, classes):
        cur = self.class_box.currentData()
        self.class_box.clear()
        for c in classes:
            self.class_box.addItem(c.name, c.id)
        i = self.class_box.findData(cur)
        if i >= 0:
            self.class_box.setCurrentIndex(i)

    def start(self):
        w = self.app.worker
        if w is None:
            QMessageBox.information(self, "Attendance", "Connect a camera first (Cameras page).")
            return
        if w.mode != "preview":
            QMessageBox.information(self, "Attendance", "Stop exam monitoring / class mode first.")
            return
        cid = self.class_box.currentData()
        if not cid:
            QMessageBox.information(self, "Attendance", "Create a class with students first.")
            return
        self.start_btn.setEnabled(False)
        self.app.toast("Preparing face data...")
        self._job = Job(build_gallery, self.app.repo, cid, self.app.models.ensure_face())
        self._job.finished_ok.connect(lambda res: self._begin(cid, res))
        self._job.failed.connect(lambda m: (QMessageBox.warning(self, "Attendance", m),
                                            self.start_btn.setEnabled(True)))
        self._job.start()

    def _begin(self, cid, result):
        gallery, students, warnings = result
        if len(gallery) == 0:
            self.start_btn.setEnabled(True)
            QMessageBox.warning(self, "Attendance", "No student in this class has a usable photo yet.")
            return
        w = self.app.worker
        if w is None:
            self.start_btn.setEnabled(True)
            return
        self.present_list.clear()
        self.absent_list.clear()
        self.s_total.set(len(students))
        self.s_present.set(0)
        self.s_absent.set(len(students))
        self.s_unknown.set(0)
        self.unknown_note.hide()
        self.unknown_list.clear()
        self.unknown_list.hide()
        w.begin_attendance(self.app.repo.get(cid).name, gallery, students, self.seconds.value())
        w.scan.class_id = cid
        self.stop_btn.setEnabled(True)
        self.app.set_live("ATTENDANCE")

    def finish(self):
        if self.app.worker:
            self.app.worker.end_attendance()

    def on_tick(self, frac, names, unknown=0):
        self.progress.setValue(int(frac * 100))
        self.s_unknown.set(unknown)
        self.s_present.set(len(names))
        total = int(self.s_total.value.text() or 0)
        self.s_absent.set(max(0, total - len(names)))
        if self.present_list.count() != len(names):
            self.present_list.clear()
            self.present_list.addItems(sorted(names))

    def on_done(self, scan):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setValue(100)
        self.app.set_live(None)
        s = scan.summary()
        self.s_present.set(s["present"])
        self.s_absent.set(s["absent"])
        self.absent_list.clear()
        self.absent_list.addItems([f"{m.usn}  ·  {m.name}" for m in sorted(scan.absent(), key=lambda m: m.usn)])
        unknown = scan.unknown_people()
        self.s_unknown.set(len(unknown))
        self.unknown_list.clear()
        if unknown:
            self.unknown_note.setText(f"⚠ {len(unknown)} unknown person(s) in class - not in this class's dataset")
            for i, u in enumerate(unknown, 1):
                it = QListWidgetItem(f"Unknown person {i}  ·  first seen "
                                     f"{time.strftime('%H:%M:%S', time.localtime(u.first_seen))}  ·  seen {u.sightings}x")
                if u.snapshot is not None:
                    it.setIcon(QIcon(QPixmap.fromImage(to_qimage(u.snapshot))))
                self.unknown_list.addItem(it)
            self.unknown_note.show()
            self.unknown_list.show()
        else:
            self.unknown_note.hide()
            self.unknown_list.hide()
        try:
            path, reg = write_attendance(scan, reports_dir(), self.subject.text().strip(),
                                         self.teacher.text().strip())
        except PermissionError:
            QMessageBox.warning(self, "Attendance", "Close the Excel file that is open, then try again.")
            return
        self.last_report = path
        self.open_btn.setEnabled(True)
        try:   # remember this session for the class dashboard
            record_session(self.app.repo.get(scan.class_id), scan, self.subject.text().strip())
        except (KeyError, AttributeError, OSError):
            pass
        self.app.reports_changed()
        note = ""
        if s["too_small"] > s["frames"]:
            note = "\n\nMany faces were too far away. Move the camera closer for better results."
        if unknown:
            note += f"\n\n⚠ {len(unknown)} UNKNOWN person(s) were in the class (photos in the report)."
        QMessageBox.information(self, "Attendance saved",
                                f"{scan.classroom}: {s['present']} present, {s['absent']} absent "
                                f"({s['percent']}%).\n\nSaved to {os.path.basename(path)}{note}")


# =============================================================================
class ExamPage(QWidget):
    title = "Exam Monitoring"

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.incidents = []
        lay = QHBoxLayout(self)
        lay.setSpacing(16)

        left = QVBoxLayout()
        self.video = VideoView("Connect a camera on the Cameras page")
        left.addWidget(self.video, 1)
        stats = QHBoxLayout()
        self.s_people, self.s_inc, self.s_flag = Stat("Students watched"), Stat("Incidents"), Stat("Students flagged")
        for s in (self.s_people, self.s_inc, self.s_flag):
            stats.addWidget(s)
        left.addLayout(stats)
        lay.addLayout(left, 3)

        side = QVBoxLayout()
        setup = Card("Exam session")
        form = QFormLayout()
        self.hall = QLineEdit("Exam Hall 1")
        self.exam_name = QLineEdit()
        self.exam_name.setPlaceholderText("e.g. IA-2 Maths (optional)")
        self.sens = QComboBox()
        self.sens.addItems(["Low", "Normal", "High"])
        self.sens.setCurrentText(app.settings.sensitivity)
        form.addRow("Hall", self.hall)
        form.addRow("Exam", self.exam_name)
        form.addRow("Sensitivity", self.sens)
        setup.body.addLayout(form)
        from classeye.exam import RULES
        self.rule_boxes = {}
        grid = QGridLayout()
        for i, (key, (title, _sev)) in enumerate(RULES.items()):
            cb = QCheckBox(title)
            cb.setChecked(True)
            self.rule_boxes[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        setup.body.addLayout(grid)
        self.beep = QCheckBox("Sound on incident")
        self.beep.setChecked(True)
        setup.body.addWidget(self.beep)
        self.toggle_btn = button("Start monitoring", "Success", self.toggle)
        self.save_btn = button("Save report", "Primary", self.save)
        self.save_btn.setEnabled(False)
        setup.body.addLayout(row(self.toggle_btn, self.save_btn))
        setup.body.addWidget(muted("Students are identified using the photos of ALL classes."))
        side.addWidget(setup)

        log = Card("Incidents")
        self.table = table(["Time", "Student", "Incident"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.cellClicked.connect(self._preview)
        self.table.cellDoubleClicked.connect(lambda r, _c: open_file(self.incidents[r].photo))
        log.body.addWidget(self.table, 1)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(150)
        log.body.addWidget(self.preview)
        side.addWidget(log, 1)
        lay.addLayout(side, 2)

    def toggle(self):
        w = self.app.worker
        if w is not None and w.mode == "exam":
            mon = w.end_exam()
            self.toggle_btn.setText("Start monitoring")
            self.toggle_btn.setObjectName("Success")
            self.toggle_btn.setStyle(self.toggle_btn.style())
            self.app.set_live(None)
            if self.incidents:
                self.save()
            return
        if w is None:
            QMessageBox.information(self, "Exam", "Connect a camera first (Cameras page).")
            return
        if w.mode in ("attendance", "class"):
            QMessageBox.information(self, "Exam", "Finish the attendance scan / class mode first.")
            return
        self.toggle_btn.setEnabled(False)
        self.app.toast("Loading exam AI models and all class photos...")
        enabled = {k for k, cb in self.rule_boxes.items() if cb.isChecked()}
        self.app.settings.sensitivity = self.sens.currentText()
        self._job = Job(self._prepare, enabled)
        self._job.finished_ok.connect(self._begin)
        self._job.failed.connect(lambda m: (QMessageBox.warning(self, "Exam", m),
                                            self.toggle_btn.setEnabled(True)))
        self._job.start()

    def _prepare(self, enabled):
        """Runs in a background thread - no widget access here."""
        from classeye.exam import ExamMonitor
        settings = self.app.settings
        pose, objects = self.app.models.ensure_exam()
        face = self.app.models.ensure_face()
        galleries = [build_gallery(self.app.repo, c.id, face)[0] for c in self.app.repo.list()]
        gallery = FaceGallery.merge(galleries)
        return ExamMonitor(settings, pose, objects, face, gallery, reports_dir(), enabled)

    def _begin(self, monitor):
        self.toggle_btn.setEnabled(True)
        w = self.app.worker
        if w is None:
            return
        self.incidents = []
        self.table.setRowCount(0)
        self.preview.clear()
        self.s_inc.set(0)
        self.s_flag.set(0)
        w.begin_exam(monitor)
        self.toggle_btn.setText("Stop monitoring")
        self.toggle_btn.setObjectName("Danger")
        self.toggle_btn.setStyle(self.toggle_btn.style())
        self.save_btn.setEnabled(True)
        self.app.set_live("EXAM")
        self.app.toast(f"Monitoring. {len(monitor.gallery)} enrolled students can be identified.")

    def on_incident(self, inc):
        self.incidents.append(inc)
        r = self.table.rowCount()
        self.table.insertRow(r)
        who = f"{inc.usn} {inc.name}".strip() or f"Person #{inc.track_id}"
        for j, v in enumerate([time.strftime("%H:%M:%S", time.localtime(inc.time)), who, inc.title]):
            it = QTableWidgetItem(v)
            if inc.severity == "High":
                it.setForeground(QColor("#F0544F"))
            self.table.setItem(r, j, it)
        self.table.scrollToBottom()
        self._preview(r, 0)
        self.s_inc.set(len(self.incidents))
        self.s_flag.set(len({i.usn or f"#{i.track_id}" for i in self.incidents}))
        if self.beep.isChecked():
            QApplication.beep()

    def on_frame_stats(self, people):
        self.s_people.set(people)

    def _preview(self, r, _c):
        if 0 <= r < len(self.incidents):
            p = self.incidents[r].crop or self.incidents[r].photo
            if p and os.path.exists(p):
                self.preview.setPixmap(QPixmap(p).scaled(self.preview.width(), 150, Qt.KeepAspectRatio,
                                                         Qt.SmoothTransformation))

    def save(self):
        if not self.incidents:
            QMessageBox.information(self, "Exam report", "No incidents recorded.")
            return
        try:
            path = write_exam_report(self.incidents, reports_dir(), self.hall.text().strip() or "Exam Hall",
                                     self.exam_name.text().strip())
        except PermissionError:
            QMessageBox.warning(self, "Exam report", "Close the Excel file that is open, then try again.")
            return
        self.app.reports_changed()
        if QMessageBox.question(self, "Exam report", f"Saved {len(self.incidents)} incidents.\nOpen it now?") \
                == QMessageBox.Yes:
            open_file(path)


# =============================================================================
class ReportsPage(QWidget):
    title = "Reports"

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        card = Card("Saved reports")
        self.table = table(["Report", "Type", "Saved"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._open)
        card.body.addWidget(self.table, 1)
        card.body.addLayout(row(button("Open selected", "Primary", lambda: self._open(self.table.currentRow(), 0)),
                                button("Open reports folder", "", lambda: open_file(reports_dir())),
                                button("Refresh", "", self.refresh), None))
        lay.addWidget(card)
        self.refresh()

    def refresh(self):
        d = reports_dir()
        os.makedirs(d, exist_ok=True)
        files = sorted((f for f in os.listdir(d) if f.endswith(".xlsx")),
                       key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
        self.table.setRowCount(0)
        for f in files:
            r = self.table.rowCount()
            self.table.insertRow(r)
            kind = "Exam" if f.startswith("Exam") else ("Register" if f.startswith("Register") else "Attendance")
            when = time.strftime("%d %b %Y  %I:%M %p", time.localtime(os.path.getmtime(os.path.join(d, f))))
            for j, v in enumerate([f, kind, when]):
                self.table.setItem(r, j, QTableWidgetItem(v))

    def _open(self, r, _c):
        if r >= 0 and self.table.item(r, 0):
            open_file(os.path.join(reports_dir(), self.table.item(r, 0).text()))


# =============================================================================
class DashboardPage(QWidget):
    title = "Dashboard"
    COLORS = {"Shortage": "#C0392B", "At risk": "#D68910", "Safe": "#1E8449"}

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rows, self.sessions = [], []
        lay = QVBoxLayout(self)
        lay.setSpacing(14)

        top = Card()
        bar = QHBoxLayout()
        self.class_box = QComboBox()
        self.class_box.setMinimumWidth(220)
        self.class_box.currentIndexChanged.connect(lambda _: self.refresh())
        self.limit = QSpinBox()
        self.limit.setRange(50, 100)
        self.limit.setValue(75)
        self.limit.setSuffix(" %")
        self.limit.valueChanged.connect(lambda _: self.refresh())
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search USN or name")
        self.search.textChanged.connect(lambda _: self._fill())
        bar.addWidget(QLabel("Class"))
        bar.addWidget(self.class_box)
        bar.addSpacing(12)
        bar.addWidget(QLabel("Minimum attendance"))
        bar.addWidget(self.limit)
        bar.addSpacing(12)
        bar.addWidget(self.search, 1)
        bar.addWidget(button("Refresh", "", self.refresh))
        bar.addWidget(button("Export for HOD (Excel)", "Primary", self.export))
        top.body.addLayout(bar)
        lay.addWidget(top)

        stats = QHBoxLayout()
        self.s_sessions, self.s_avg = Stat("Classes held"), Stat("Average attendance")
        self.s_short, self.s_risk, self.s_perfect = Stat("Shortage"), Stat("At risk (within 5%)"), Stat("100% attendance")
        self.s_short.value.setStyleSheet("color:#C0392B;")
        self.s_risk.value.setStyleSheet("color:#D68910;")
        self.s_perfect.value.setStyleSheet("color:#1E8449;")
        for s in (self.s_sessions, self.s_avg, self.s_short, self.s_risk, self.s_perfect):
            stats.addWidget(s)
        lay.addLayout(stats)

        body = QHBoxLayout()
        students = Card("Students")
        self.alert = QLabel("")
        self.alert.setWordWrap(True)
        self.alert.setStyleSheet("background:#FBE5E3; color:#8E2B20; border-radius:6px; padding:8px 10px; font-weight:600;")
        self.alert.hide()
        students.body.addWidget(self.alert)
        self.table = table(["USN", "Name", "Attended", "Held", "Attendance", "Status", "Advice"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        students.body.addWidget(self.table, 1)
        body.addWidget(students, 3)

        hist = Card("Recent classes")
        self.hist = table(["Date & time", "Subject", "Present"])
        self.hist.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        hist.body.addWidget(self.hist, 1)
        body.addWidget(hist, 1)
        lay.addLayout(body, 1)

    def refresh_classes(self, classes):
        cur = self.class_box.currentData()
        self.class_box.blockSignals(True)
        self.class_box.clear()
        for c in classes:
            self.class_box.addItem(c.name, c.id)
        i = self.class_box.findData(cur)
        if i >= 0:
            self.class_box.setCurrentIndex(i)
        self.class_box.blockSignals(False)
        self.refresh()

    def refresh(self):
        cid = self.class_box.currentData()
        self.rows, self.sessions = [], []
        if cid:
            try:
                c = self.app.repo.get(cid)
            except KeyError:
                c = None
            if c is not None:
                self.sessions = load_sessions(c)
                self.rows = class_report(self.app.repo.students(cid), self.sessions, self.limit.value())
        ov = overview(self.rows, self.sessions)
        self.s_sessions.set(ov["sessions"])
        self.s_avg.set(f"{ov['average']}%")
        self.s_short.set(ov["shortage"])
        self.s_risk.set(ov["at_risk"])
        self.s_perfect.set(ov["perfect"])
        if ov["shortage"]:
            names = ", ".join(r.name for r in self.rows if r.status == "Shortage")[:300]
            self.alert.setText(f"⚠  {ov['shortage']} student(s) below {self.limit.value()}%: {names}")
            self.alert.show()
        else:
            self.alert.hide()
        self._fill()
        self.hist.setRowCount(0)
        for s in reversed(self.sessions[-30:]):
            r = self.hist.rowCount()
            self.hist.insertRow(r)
            total = len(s["present"]) + len(s["absent"])
            for j, v in enumerate([s["time"], s.get("subject", "") or "-", f"{len(s['present'])}/{total}"]):
                self.hist.setItem(r, j, QTableWidgetItem(v))

    def _fill(self):
        q = self.search.text().strip().lower()
        self.table.setRowCount(0)
        for st in self.rows:
            if q and q not in st.usn.lower() and q not in st.name.lower():
                continue
            if st.status == "Shortage":
                advice = f"Must attend the next {st.need} class(es)"
            elif st.held:
                advice = f"Can miss {st.can_miss} more class(es)"
            else:
                advice = ""
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [st.usn, st.name, str(st.attended), str(st.held), f"{st.percent}%" if st.held else "-",
                    st.status, advice]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j in (4, 5) and st.status in self.COLORS:
                    it.setForeground(QColor(self.COLORS[st.status]))
                    if j == 5:
                        f = it.font()
                        f.setBold(True)
                        it.setFont(f)
                self.table.setItem(r, j, it)
        self.table.setColumnWidth(0, 130)

    def export(self):
        cid = self.class_box.currentData()
        if not cid or not self.sessions:
            QMessageBox.information(self, "Dashboard", "Take attendance for this class at least once first.")
            return
        try:
            path = write_shortage_report(self.app.repo.get(cid).name, self.rows, self.sessions,
                                         self.limit.value(), reports_dir())
        except PermissionError:
            QMessageBox.warning(self, "Dashboard", "Close the Excel file that is open, then try again.")
            return
        self.app.reports_changed()
        open_file(path)


# =============================================================================
class ClassModePage(QWidget):
    title = "Class Mode"
    LEVEL_COLORS = {"Good": "#1E8449", "Average": "#D68910", "Poor": "#C0392B", "Poor (sleeping)": "#C0392B"}
    STATE_TEXT = {"Attentive": "👀 Attentive", "Writing": "✍ Writing / reading", "Distracted": "↔ Distracted",
                  "Sleeping": "😴 Sleeping", "Away": "– Not visible"}

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.last_report = None
        lay = QHBoxLayout(self)
        lay.setSpacing(16)

        left = QVBoxLayout()
        self.video = VideoView("Connect a camera on the Cameras page")
        left.addWidget(self.video, 1)
        stats = QHBoxLayout()
        self.s_class, self.s_people = Stat("Class attention"), Stat("Students watched")
        self.s_sleep, self.s_time = Stat("Sleeping now"), Stat("Minutes")
        self.s_sleep.value.setStyleSheet("color:#C0392B;")
        for s in (self.s_class, self.s_people, self.s_sleep, self.s_time):
            stats.addWidget(s)
        left.addLayout(stats)
        lay.addLayout(left, 3)

        side = QVBoxLayout()
        setup = Card("Lecture")
        form = QFormLayout()
        self.class_box = QComboBox()
        self.subject = QLineEdit()
        self.subject.setPlaceholderText("optional")
        form.addRow("Class", self.class_box)
        form.addRow("Subject", self.subject)
        setup.body.addLayout(form)
        self.toggle_btn = button("Start class mode", "Success", self.toggle)
        setup.body.addWidget(self.toggle_btn)
        setup.body.addWidget(muted("Estimates each student's attention from head direction and posture. "
                                   "Approximate - a guide for the teacher, not a grade."))
        side.addWidget(setup)

        board = Card("Students (lowest attention first)")
        self.table = table(["Student", "Attention", "Right now", "Level"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        board.body.addWidget(self.table, 1)
        self.open_btn = button("Open attention report", "Primary", lambda: open_file(self.last_report))
        self.open_btn.setEnabled(False)
        board.body.addWidget(self.open_btn)
        side.addWidget(board, 1)
        lay.addLayout(side, 2)

    def refresh_classes(self, classes):
        cur = self.class_box.currentData()
        self.class_box.clear()
        for c in classes:
            self.class_box.addItem(c.name, c.id)
        i = self.class_box.findData(cur)
        if i >= 0:
            self.class_box.setCurrentIndex(i)

    def running(self):
        w = self.app.worker
        return w is not None and w.mode == "class"

    def toggle(self):
        w = self.app.worker
        if self.running():
            self.stop()
            return
        if w is None:
            QMessageBox.information(self, "Class mode", "Connect a camera first (Cameras page).")
            return
        if w.mode != "preview":
            QMessageBox.information(self, "Class mode", "Finish the attendance scan / exam monitoring first.")
            return
        cid = self.class_box.currentData()
        if not cid:
            QMessageBox.information(self, "Class mode", "Create a class first (students are named from its photos).")
            return
        self.toggle_btn.setEnabled(False)
        self.app.toast("Loading pose model and class photos...")
        name = self.class_box.currentText()
        self._job = Job(self._prepare, cid, name)
        self._job.finished_ok.connect(self._begin)
        self._job.failed.connect(lambda m: (QMessageBox.warning(self, "Class mode", m),
                                            self.toggle_btn.setEnabled(True)))
        self._job.start()

    def _prepare(self, cid, name):
        """Runs in a background thread - no widget access here."""
        from classeye.attention import AttentionMonitor
        pose, _ = self.app.models.ensure_exam()
        face = self.app.models.ensure_face()
        gallery = build_gallery(self.app.repo, cid, face)[0]
        return AttentionMonitor(self.app.settings, pose, face, gallery, name)

    def _begin(self, monitor):
        self.toggle_btn.setEnabled(True)
        w = self.app.worker
        if w is None:
            return
        self.table.setRowCount(0)
        for st in (self.s_class, self.s_people, self.s_sleep, self.s_time):
            st.set(0)
        w.begin_class(monitor)
        self.toggle_btn.setText("Stop and save report")
        self.toggle_btn.setObjectName("Danger")
        self.toggle_btn.setStyle(self.toggle_btn.style())
        self.app.set_live("CLASS")

    def stop(self):
        w = self.app.worker
        mon = w.end_class() if w is not None else None
        self.toggle_btn.setText("Start class mode")
        self.toggle_btn.setObjectName("Success")
        self.toggle_btn.setStyle(self.toggle_btn.style())
        self.app.set_live(None)
        if mon is None or mon.started is None:
            return
        summary = mon.summary()
        if not summary["students"]:
            QMessageBox.information(self, "Class mode", "No students were watched long enough for a report.")
            return
        try:
            path = write_class_report(mon.class_name, summary, mon.timeline_rows(), reports_dir(),
                                      self.subject.text().strip())
        except PermissionError:
            QMessageBox.warning(self, "Class mode", "Close the Excel file that is open, then try again.")
            return
        self.last_report = path
        self.open_btn.setEnabled(True)
        self.app.reports_changed()
        poor = [r for r in summary["students"] if r.level.startswith("Poor")]
        QMessageBox.information(self, "Class mode", f"Class attention: {summary['class_percent']}% over "
                                f"{summary['minutes']} min.\n{len(poor)} student(s) with poor attention.\n\n"
                                f"Saved to {os.path.basename(path)}")

    def on_tick(self, summary):
        self.s_class.set(f"{summary['class_percent']:.0f}%")
        self.s_people.set(summary["people_now"])
        self.s_sleep.set(summary["sleeping_now"])
        self.s_time.set(summary["minutes"])
        rows = summary["students"]
        self.table.setRowCount(len(rows))
        for r, st in enumerate(rows):
            who = f"{st.usn}  ·  {st.name}" if st.usn else f"Not identified ({st.key})"
            vals = [who, f"{st.percent:.0f}%", self.STATE_TEXT.get(st.state, st.state), st.level]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j in (1, 3):
                    it.setForeground(QColor(self.LEVEL_COLORS.get(st.level, "#1B2333")))
                self.table.setItem(r, j, it)
