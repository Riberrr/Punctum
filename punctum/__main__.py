"""Punkt wejscia: python -m punctum [folder]"""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from .app import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Punctum")
    app.setOrganizationName("Punctum")

    window = MainWindow()
    window.show()

    folder = sys.argv[1] if len(sys.argv) > 1 else ""
    if not folder and window.settings.reopen_last_folder:
        folder = window.settings.last_folder
    if folder and os.path.isdir(folder):
        window.load_folder(folder)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
