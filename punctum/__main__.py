"""Punkt wejscia: python -m punctum [folder]"""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

# Tylko lekkie moduly na gorze: ekran startowy ma sie pokazac, zanim zaladuja
# sie rawpy, OpenCV i glowne okno (to one sa wlasciwym czasem startu).
from .app.ekran_startowy import ASSETS, EkranStartowy
from .app.jezyk import zastosuj_jezyk
from .core.settings import Settings
from . import APP_ID
from .przeklad import t


def _ikona_programu(app: QApplication) -> None:
    app.setWindowIcon(QIcon(os.path.join(ASSETS, "punctum.ico")))
    if sys.platform == "win32":
        # Bez wlasnego identyfikatora Windows grupuje okno pod python.exe
        # i na pasku zadan pokazuje ikone Pythona zamiast naszej.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Punctum")
    app.setOrganizationName("Punctum")
    _ikona_programu(app)
    # Jezyk przed pierwszym oknem - napisy licza sie przy tworzeniu widzetow,
    # a ekran startowy tez juz mowi w wybranym jezyku.
    zastosuj_jezyk(app, Settings.load().language)

    ekran = EkranStartowy()
    ekran.show()
    ekran.krok(t("Wczytywanie modułów…"), 0.12)
    from .app import MainWindow

    ekran.krok(t("Przygotowanie okna…"), 0.4)
    window = MainWindow()
    window.show()

    folder = sys.argv[1] if len(sys.argv) > 1 else ""
    if not folder and window.settings.reopen_last_folder:
        folder = window.settings.last_folder
    if folder and os.path.isdir(folder):
        ekran.krok(t("Otwieranie katalogu {nazwa}…", nazwa=os.path.basename(folder)), 0.6)
        window.load_folder(folder)

    # Ekran schodzi dopiero, gdy pierwsze zdjecie i widoczne miniatury sa na
    # miejscu - samo zbudowanie okna to jeszcze nie gotowosc do pracy.
    ekran.czekaj_na(window, window.stan_startu)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
