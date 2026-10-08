"""Punkt wejscia: python -m punctum [folder]"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

# Tylko lekkie moduly na gorze: ekran startowy ma sie pokazac, zanim zaladuja
# sie rawpy, OpenCV i glowne okno (to one sa wlasciwym czasem startu).
from .app.ekran_startowy import ASSETS, EkranStartowy
from .app.jedna_instancja import Aplikacja, bezwzgledne, rozbierz_argumenty, zglos_sie
from .app.jezyk import zastosuj_jezyk
from .core import platforma
from .core.settings import Settings
from . import APP_ID
from .przeklad import t


def _ikona_programu(app: QApplication) -> None:
    app.setWindowIcon(QIcon(os.path.join(ASSETS, "punctum.ico")))
    if platforma.WINDOWS:
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


def wyciagnij_na_wierzch(window) -> None:
    # Zminimalizowane okno wraca do poprzedniego stanu (tez zmaksymalizowanego).
    window.setWindowState((window.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
    window.show()
    window.raise_()
    window.activateWindow()


def przyjmij_argumenty(window, argumenty: list[str]) -> None:
    """Argumenty od drugiego uruchomienia programu (punkt 34)."""
    sciezka, pole = rozbierz_argumenty(argumenty)
    folder, plik = rozpoznaj_argument(sciezka)
    modalne = QApplication.activeModalWidget()
    if modalne is not None:
        # Otwarte okno (ustawienia, eksport) pracuje na biezacym zdjeciu -
        # podmiana katalogu pod nim narobilaby szkody.
        wyciagnij_na_wierzch(window)
        modalne.raise_()
        modalne.activateWindow()
        if folder:
            window.status.showMessage(
                t("Zamknij otwarte okno i otwórz zdjęcie jeszcze raz."), 8000)
        return
    if folder and os.path.isdir(folder):
        biezacy = window.settings.last_folder or ""
        if not window.paths or os.path.normcase(os.path.abspath(biezacy)) != os.path.normcase(os.path.abspath(folder)):
            window.load_folder(folder)
        if plik:
            otworz_zdjecie(window, plik)
    wyciagnij_na_wierzch(window)
    if pole:
        window.open_settings(pole=pole)


def main() -> int:
    app = Aplikacja(sys.argv)
    app.setApplicationName("Punctum")
    app.setOrganizationName("Punctum")
    # Drugie uruchomienie (dwuklik zdjecia przy otwartym programie) oddaje
    # plik pierwszemu i konczy sie, zanim cokolwiek pokaze (punkt 34).
    argumenty = bezwzgledne(sys.argv[1:])
    serwer = zglos_sie(argumenty)
    if serwer is None:
        return 0
    serwer.setParent(app)
    serwer.sluchaj_otwierania(app)
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
    window.serwer_instancji = serwer
    ekran.raise_()  # na wypadek, gdyby system zignorowal "na wierzchu" przy aktywacji okna

    sciezka, pole = rozbierz_argumenty(argumenty)
    if not sciezka:
        sciezka, _ = rozbierz_argumenty(serwer.przejmij_czekajace())
    folder, plik = rozpoznaj_argument(sciezka)
    if not folder and window.settings.reopen_last_folder:
        folder = window.settings.last_folder
    if folder and os.path.isdir(folder):
        ekran.krok(t("Otwieranie katalogu {nazwa}…", nazwa=os.path.basename(folder)), 0.6)
        window.load_folder(folder)
        if plik:
            otworz_zdjecie(window, plik)

    # Ekran schodzi dopiero, gdy pierwsze zdjecie i widoczne miniatury sa na
    # miejscu - samo zbudowanie okna to jeszcze nie gotowosc do pracy.
    from .app.pomoc import co_nowego_po_aktualizacji

    def po_starcie() -> None:
        co_nowego_po_aktualizacji(window)
        if pole:
            # Po "Zapisz i uruchom ponownie" wracamy do tego samego pola
            # ustawien, juz w nowym jezyku (punkt 33).
            window.open_settings(pole=pole)

    ekran.po_schowaniu = po_starcie
    ekran.czekaj_na(window, window.stan_startu)
    # Pliki od kolejnych uruchomien czekaly w kolejce - okno jest juz gotowe.
    serwer.ustaw_odbiorce(lambda a: przyjmij_argumenty(window, a))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
