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


def rozpoznaj_argument(arg: str) -> tuple[str, str]:
    """(katalog, zdjecie) z argumentu wiersza polecen.

    Skojarzenie plikow w Eksploratorze (instalator, punkt 18) podaje sciezke
    zdjecia, nie katalogu - wtedy otwieramy jego katalog, zeby pasek miniatur
    mial sasiednie zdjecia, a samo zdjecie wybieramy potem.
    """
    if arg and os.path.isfile(arg):
        plik = os.path.abspath(arg)
        return os.path.dirname(plik), plik
    return arg, ""


def otworz_zdjecie(window, plik: str) -> None:
    # Porownanie po normcase: Eksplorator potrafi podac inna wielkosc liter
    # niz os.listdir, a na Windows to ten sam plik.
    klucz = os.path.normcase(plik)
    for i, sciezka in enumerate(window.paths):
        if os.path.normcase(sciezka) == klucz:
            # Przez pasek miniatur, zeby zaznaczenie w pasku zgadzalo sie
            # z podgladem (tak samo robi narzedzie MCP open_photo).
            window.filmstrip.setCurrentRow(i)
            window.open_photo(sciezka)
            return


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
    window.uruchom_mcp()  # agenci AI (punkt 6); sam serwer to watek, bez kosztu startu
    ekran.raise_()  # na wypadek, gdyby system zignorowal "na wierzchu" przy aktywacji okna

    folder, plik = rozpoznaj_argument(sys.argv[1] if len(sys.argv) > 1 else "")
    if not folder and window.settings.reopen_last_folder:
        folder = window.settings.last_folder
    if folder and os.path.isdir(folder):
        ekran.krok(t("Otwieranie katalogu {nazwa}…", nazwa=os.path.basename(folder)), 0.6)
        window.load_folder(folder)
        if plik:
            otworz_zdjecie(window, plik)

    # Ekran schodzi dopiero, gdy pierwsze zdjecie i widoczne miniatury sa na
    # miejscu - samo zbudowanie okna to jeszcze nie gotowosc do pracy.
    ekran.czekaj_na(window, window.stan_startu)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
