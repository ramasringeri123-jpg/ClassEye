"""Small reusable UI pieces."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout


class Card(QFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 16)
        self.body.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setObjectName("CardTitle")
            self.body.addWidget(t)


class Stat(QFrame):
    def __init__(self, label, value="0", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        self.value = QLabel(value)
        self.value.setObjectName("StatValue")
        cap = QLabel(label)
        cap.setObjectName("StatLabel")
        lay.addWidget(self.value)
        lay.addWidget(cap)

    def set(self, v):
        self.value.setText(str(v))


class VideoView(QLabel):
    def __init__(self, placeholder="No camera connected", parent=None):
        super().__init__(placeholder, parent)
        self.placeholder = placeholder
        self.setObjectName("Video")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(560, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def show_image(self, qimg):
        pm = QPixmap.fromImage(qimg)
        self.setPixmap(pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def clear_video(self):
        self.clear()
        self.setText(self.placeholder)


def row(*widgets, stretch_last=False):
    lay = QHBoxLayout()
    lay.setSpacing(8)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        else:
            lay.addWidget(w)
    if stretch_last:
        lay.addStretch(1)
    return lay


def muted(text):
    l = QLabel(text)
    l.setObjectName("Muted")
    l.setWordWrap(True)
    return l
