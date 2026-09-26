"""Ekran startowy: tlo z pliku, napisy i pasek postepu rysowane w programie.

Tlo (rozmyte swiatla i ostry punkt) generuje `tools/make_assets.py`. Nazwa,
haslo, wersja i stan ladowania sa rysowane tutaj, bo zaleza od jezyka -
obrazek z wpisanym tekstem trzeba by trzymac osobno dla kazdego przekladu.

Modul importuje tylko Qt i przeklad: pokazuje sie, zanim zaladuja sie rawpy,
OpenCV i glowne okno, czyli wlasnie wtedy, gdy jest na co czekac.
"""

from __future__ import annotations

import os
import random
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QSplashScreen

from .. import __version__
from ..przeklad import N_, t

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
SZEROKOSC, WYSOKOSC = 640, 380

# Losowane przy kazdym starcie. Pisane jak haslo, nie jak opis programu:
# punctum to ten jeden szczegol, dla ktorego zdjecie dziala.
HASLA = (
    N_("Dla tego jednego szczegółu."),
    N_("Każde zdjęcie ma swój punkt."),
    N_("Wywołaj to, co ważne."),
    N_("Twoje zdjęcia, twoje światło."),
    N_("Znajdź to, co przyciąga wzrok."),
    N_("Wydobądź światło z cienia."),
    N_("Każdy kadr kryje swój szczegół."),
    N_("Tam, gdzie zatrzymuje się spojrzenie."),
    N_("Pokaż to, co zobaczyłeś."),
    N_("Jedno spojrzenie, jeden punkt."),
)

# Krotszy start mignalby tylko ekranem; po skompilowaniu (punkt 18) start
# i tak jest dluzszy, wiec to ograniczenie przestanie byc odczuwalne.
MINIMUM_MS = 1200
MAKSIMUM_MS = 30000
# Po gotowosci okna ekran zostaje jeszcze chwile - zyczenie uzytkownika:
# zejscie w tej samej chwili, gdy pojawia sie zdjecie, bylo zbyt nagle.
PO_GOTOWOSCI_MS = 2500
OKNO_GOTOWE = 0.6  # czesc paska przypadajaca na etapy do zbudowania okna

FIOLET, FIOLET_JASNY = QColor("#6c63ff"), QColor("#7b73ff")


def _czcionka(piksele: float, gruba: bool = False) -> QFont:
    font = QFont("Segoe UI")
    font.setPixelSize(round(piksele))
    if gruba:
        # Na Windows polgruby kroj to osobna rodzina; sama waga DemiBold
        # dawala zwykly Segoe UI i nazwa wygladala blado.
        font.setFamilies(["Segoe UI Semibold", "Segoe UI"])
        font.setWeight(QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.5)
    return font


def _tlo() -> QPixmap:
    ekran = QGuiApplication.primaryScreen()
    gestosc = ekran.devicePixelRatio() if ekran else 1.0
    nazwa = "ekran-startowy@2x.png" if gestosc > 1.0 else "ekran-startowy.png"
    pixmap = QPixmap(os.path.join(ASSETS, nazwa))
    if pixmap.isNull():  # brak pliku nie moze zatrzymac startu programu
        pixmap = QPixmap(SZEROKOSC, WYSOKOSC)
        pixmap.fill(QColor("#141318"))
    else:
        pixmap.setDevicePixelRatio(pixmap.width() / SZEROKOSC)
    return pixmap


class EkranStartowy(QSplashScreen):
    def __init__(self, haslo: str | None = None):
        super().__init__(_tlo())
        self.haslo = haslo or random.choice(HASLA)
        self.stan = t("Uruchamianie…")
        self.postep = 0.0
        self._logo = QSvgRenderer(os.path.join(ASSETS, "logo.svg"))
        self._pokazany = time.monotonic()

    def show(self) -> None:
        super().show()
        self._pokazany = time.monotonic()
        QApplication.processEvents()

    def krok(self, stan: str, postep: float) -> None:
        """Nowy etap ladowania. Odrysowanie od razu - petla zdarzen stoi."""
        self.stan, self.postep = stan, max(0.0, min(1.0, postep))
        self.repaint()
        QApplication.processEvents()

    def czekaj_na(self, okno, stan) -> None:
        """Zostaje na ekranie, dopoki okno nie jest gotowe do pracy.

        `stan()` zwraca (napis, ulamek 0..1) albo None, gdy wszystko gotowe.
        Po zbudowaniu okna petla zdarzen juz chodzi (zdjecie i miniatury
        laduja sie w watkach), wiec pytamy co 100 ms zamiast blokowac.
        Gorny limit, bo ekran zawsze na wierzchu nie moze wisiec bez konca,
        gdy cos utknie.
        """
        start = time.monotonic()
        zegar = QTimer(self)
        zegar.setInterval(100)

        def sprawdz() -> None:
            teraz = stan()
            if teraz is None or (time.monotonic() - start) * 1000 > MAKSIMUM_MS:
                zegar.stop()
                self.stan, self.postep = t("Gotowe"), 1.0
                self.update()
                QTimer.singleShot(PO_GOTOWOSCI_MS, lambda: self.zakoncz(okno))
                return
            napis, ulamek = teraz
            # etapy sprzed zbudowania okna zajely pasek do OKNO_GOTOWE
            self.stan = napis
            self.postep = max(self.postep, OKNO_GOTOWE + (1.0 - OKNO_GOTOWE) * ulamek)
            self.update()

        zegar.timeout.connect(sprawdz)
        zegar.start()
        sprawdz()

    def zakoncz(self, okno) -> None:
        """Chowa ekran po minimalnym czasie, zeby start nie byl tylko mignieciem."""
        zostalo = MINIMUM_MS - (time.monotonic() - self._pokazany) * 1000
        if zostalo <= 0:
            self.finish(okno)
        else:
            QTimer.singleShot(int(zostalo), lambda: self.finish(okno))

    def drawContents(self, p: QPainter) -> None:  # noqa: N802 - nazwa z Qt
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        self._logo.render(p, QRectF(24, 232, 64, 64))

        nazwa = _czcionka(40, gruba=True)
        p.setFont(nazwa)
        p.setPen(QColor("#e8e8ea"))
        p.drawText(102, 282, "Punctum")
        p.setPen(FIOLET_JASNY)
        p.drawText(102 + QFontMetricsF(nazwa).horizontalAdvance("Punctum"), 282, ".")

        p.setFont(_czcionka(13))
        p.setPen(QColor("#a2a2aa"))
        p.drawText(104, 306, t(self.haslo))

        male = _czcionka(11)
        p.setFont(male)
        p.setPen(QColor("#6a6a72"))
        wersja = t("wersja {numer}", numer=__version__)
        p.drawText(SZEROKOSC - 24 - QFontMetricsF(male).horizontalAdvance(wersja), 30, wersja)

        p.setFont(_czcionka(12))
        p.setPen(QColor("#8a8a90"))
        p.drawText(24, 356, self.stan)

        p.fillRect(QRectF(0, 372, SZEROKOSC, 3), QColor(255, 255, 255, 15))
        p.fillRect(QRectF(0, 372, SZEROKOSC * self.postep, 3), FIOLET)
