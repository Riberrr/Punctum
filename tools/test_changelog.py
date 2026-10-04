"""Historia zmian (punkt 36): pliki CHANGELOG, Pomoc > Co nowego, pokaz po aktualizacji.

Pilnuje zasady wydania: bez wpisu dla biezacego `__version__` w obu
jezykach nie ma czego scalac do main. Okno sprawdzane na platformie
offscreen - bez pokazywania czegokolwiek uzytkownikowi.
"""

from __future__ import annotations

import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, REPO)
sys.path.insert(0, TOOLS)

from wspolne import wypisz  # noqa: E402

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from punctum import __version__  # noqa: E402
from punctum.app import pomoc  # noqa: E402
from punctum.core.settings import Settings  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


WERSJA = re.compile(r"^## (\d+\.\d+\.\d+) — \d{4}-\d{2}-\d{2}$", re.M)
PLIKI = {"en": ("CHANGELOG.md", "## Unreleased"), "pl": ("CHANGELOG.pl.md", "## Nieopublikowane")}

wersje = {}
roboczy = {}
for kod, (nazwa, naglowek) in PLIKI.items():
    sciezka = os.path.join(REPO, nazwa)
    check(f"{nazwa} jest", os.path.isfile(sciezka))
    tekst = open(sciezka, encoding="utf-8").read() if os.path.isfile(sciezka) else ""
    wersje[kod] = WERSJA.findall(tekst)
    roboczy[kod] = naglowek in tekst
    check(f"{nazwa}: wpis dla {__version__}", __version__ in wersje[kod], str(wersje[kod]))
    check(f"{nazwa}: w jezyku {kod} dla Co nowego", pomoc.plik_zmian(kod) == sciezka,
          str(pomoc.plik_zmian(kod)))
check("te same wersje w obu jezykach", wersje["en"] == wersje["pl"], str(wersje))
check("sekcja robocza w obu albo w zadnym", roboczy["en"] == roboczy["pl"], str(roboczy))
check("inny jezyk -> angielska", pomoc.plik_zmian("de") == os.path.join(REPO, "CHANGELOG.md"))

kompiluj = open(os.path.join(TOOLS, "kompiluj.py"), encoding="utf-8").read()
check("kompilacja dolacza oba pliki obok exe",
      all(f"'{n}')}}={n}" in kompiluj for n, _ in PLIKI.values()))

app = QApplication.instance() or QApplication(sys.argv)


class Okno(QWidget):
    def __init__(self, ostatnia: str):
        super().__init__()
        self.settings = Settings(last_seen_version=ostatnia)
        self.zapisy = 0
        self.settings.save = self._zapisz  # bez dotykania prawdziwych ustawien

    def _zapisz(self, *a, **k) -> bool:
        self.zapisy += 1
        return True


nowe = Okno("")
pomoc.co_nowego_po_aktualizacji(nowe)
check("pierwszy start: bez okna, wersja zapamietana",
      not hasattr(nowe, "_okno_zmian") and nowe.settings.last_seen_version == __version__
      and nowe.zapisy == 1)

ta_sama = Okno(__version__)
pomoc.co_nowego_po_aktualizacji(ta_sama)
check("ta sama wersja: nic", not hasattr(ta_sama, "_okno_zmian") and ta_sama.zapisy == 0)

po_aktualizacji = Okno("0.0.1")
pomoc.co_nowego_po_aktualizacji(po_aktualizacji)
okno = getattr(po_aktualizacji, "_okno_zmian", None)
check("po aktualizacji: okno zmian otwarte raz",
      okno is not None and okno.isVisible() and po_aktualizacji.settings.last_seen_version == __version__)
if okno is not None:
    tekst = okno.przegladarka.toPlainText()
    check("okno pokazuje historie", __version__ in tekst and len(tekst) > 200, tekst[:60])
    okno.close()

sys.exit(wypisz(results))
