"""ClassEye entry point.   python app.py"""
import os
import sys

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from PySide6.QtGui import QFont, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from classeye import __version__  # noqa: E402
from classeye.settings import Settings, asset_path, classes_dir, reports_dir, settings_path, user_dir  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main():
    if sys.platform == "win32":
        # own taskbar group + icon, instead of the generic Python one
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"ClassEye.ClassEye.{__version__}")
        except Exception:
            pass
    os.makedirs(user_dir(), exist_ok=True)
    os.chdir(user_dir())
    for d in (classes_dir(), reports_dir()):
        os.makedirs(d, exist_ok=True)
    settings = Settings.load()
    if not os.path.exists(settings_path()):
        settings.save()
    app = QApplication(sys.argv)
    app.setApplicationName("ClassEye")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(asset_path("classeye.ico" if sys.platform == "win32" else "classeye.png")))
    app.setFont(QFont("Segoe UI", 10))
    win = MainWindow(settings)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
