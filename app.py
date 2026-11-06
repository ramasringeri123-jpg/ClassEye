"""ClassEye entry point.   python app.py"""
import os
import sys

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from classeye.settings import Settings, base_dir, classes_dir, models_dir, reports_dir  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main():
    os.chdir(base_dir())
    for d in (classes_dir(), models_dir(), reports_dir()):
        os.makedirs(d, exist_ok=True)
    settings = Settings.load()
    if not os.path.exists(os.path.join(base_dir(), "settings.json")):
        settings.save()
    app = QApplication(sys.argv)
    app.setApplicationName("ClassEye")
    app.setFont(QFont("Segoe UI", 10))
    win = MainWindow(settings)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
