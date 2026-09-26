"""Ekran startowy: przeklad hasel i napisow, losowanie, rysowanie, zamkniecie.

Bez zdjec i bez glownego okna - chodzi w serii --szybkie.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from wspolne import wypisz  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from punctum import przeklad  # noqa: E402
from punctum.app import ekran_startowy as es  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# Lekkosc: ekran ma sie pokazac, zanim zaladuje sie tor obrobki i glowne okno.
check("start: bez rawpy i OpenCV", "rawpy" not in sys.modules and "cv2" not in sys.modules,
      ", ".join(m for m in ("rawpy", "cv2") if m in sys.modules))
check("start: bez glownego okna", "punctum.app.main_window" not in sys.modules)

check("pliki: tlo 1x i 2x, logo",
      all(os.path.isfile(os.path.join(es.ASSETS, n))
          for n in ("ekran-startowy.png", "ekran-startowy@2x.png", "logo.svg", "punctum.ico")))
check("hasla: co najmniej 8, bez powtorzen", len(es.HASLA) >= 8 and len(set(es.HASLA)) == len(es.HASLA))

przeklad.ustaw_jezyk("en")
bez = [h for h in es.HASLA if przeklad.t(h) == h]
check("en: kazde haslo przetlumaczone", not bez, "; ".join(bez))
check("en: wersja", przeklad.t("wersja {numer}", numer="1.0") == "version 1.0")
ekran = es.EkranStartowy()
from PySide6.QtCore import Qt  # noqa: E402

check("okno: zawsze na wierzchu (glowne okno go nie przykryje)",
      bool(ekran.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
check("en: stan poczatkowy po angielsku", ekran.stan == "Starting…", ekran.stan)
obraz = ekran.grab()
check("en: rysuje sie w rozmiarze tla", obraz.width() == es.SZEROKOSC and obraz.height() == es.WYSOKOSC,
      f"{obraz.width()}x{obraz.height()}")

przeklad.ustaw_jezyk("pl")
ekran = es.EkranStartowy()
check("pl: stan poczatkowy", ekran.stan == "Uruchamianie…", ekran.stan)
wylosowane = {es.EkranStartowy().haslo for _ in range(60)}
check("losowanie: rozne hasla przy kolejnych startach", len(wylosowane) >= 4, str(len(wylosowane)))

ekran.show()
ekran.krok("etap", 1.7)
check("krok: postep przyciety do 1", ekran.postep == 1.0)
okno = QWidget()
okno.show()
es.MINIMUM_MS = 0
es.PO_GOTOWOSCI_MS = 300
ekran.zakoncz(okno)
app.processEvents()
check("zakoncz: ekran schowany", not ekran.isVisible())

# Ekran ma czekac na gotowosc okna (pierwsze zdjecie, miniatury), a nie
# znikac zaraz po jego zbudowaniu.
import time  # noqa: E402

ekran = es.EkranStartowy()
ekran.show()
kolejne = iter([("zdjecie", 0.0), ("miniatury", 0.5), ("miniatury", 0.2)])
postepy = []
gotowe_o = None


def stan():
    global gotowe_o
    postepy.append(ekran.postep)
    wynik = next(kolejne, None)
    if wynik is None and gotowe_o is None:
        gotowe_o = time.monotonic()
    return wynik


ekran.czekaj_na(okno, stan)
check("czekaj_na: zostaje, dopoki trwa ladowanie", ekran.isVisible() and ekran.stan == "zdjecie", ekran.stan)
koniec = time.monotonic() + 3
while ekran.isVisible() and time.monotonic() < koniec:
    app.processEvents()
    time.sleep(0.02)
check("czekaj_na: schodzi po gotowosci", not ekran.isVisible())
check("czekaj_na: zostaje chwile po gotowosci", time.monotonic() - gotowe_o >= 0.28,
      f"{time.monotonic() - gotowe_o:.2f} s")
check("czekaj_na: pasek nie cofa sie", postepy == sorted(postepy), str(postepy))
check("czekaj_na: na koniec Gotowe i pelny pasek", ekran.stan == "Gotowe" and ekran.postep == 1.0)
okno.close()

sys.exit(wypisz(results))
