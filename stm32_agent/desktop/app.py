from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import build_palette, build_stylesheet


def create_desktop_application() -> tuple[QApplication, MainWindow]:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setOrganizationName("ChipWhisper")
    app.setApplicationName("ChipWhisper")
    app.setStyle("Fusion")
    app.setPalette(build_palette())
    app.setStyleSheet(build_stylesheet())
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    return app, window


def run_desktop_application() -> int:
    app, window = create_desktop_application()
    window.show()
    return app.exec()


def smoke_test_desktop_application() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = create_desktop_application()
    window.close()
    app.quit()
    return 0
