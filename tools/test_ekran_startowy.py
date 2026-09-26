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
ekran.zakoncz(okno)
app.processEvents()
check("zakoncz: ekran schowany", not ekran.isVisible())
okno.close()

sys.exit(wypisz(results))
