"""Instalator (punkt 18, etap 2): skrypt Inno Setup, skojarzenia, argument pliku.

Nie buduje instalatora (to minuty i wymaga kompilacji) - sprawdza to, co
latwo zepsuc przy zmianach: liste rozszerzen, kodowanie skryptu i otwieranie
zdjecia podanego przez Eksplorator.
"""

from __future__ import annotations

import os
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)

from wspolne import wypisz  # noqa: E402

import instalator  # noqa: E402
from punctum.__main__ import rozpoznaj_argument  # noqa: E402
from punctum.core.jpeg_loader import JPEG_EXTENSIONS  # noqa: E402
from punctum.core.loader import RAW_EXTENSIONS  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


linie = instalator.wpisy_rozszerzen()
for ext in RAW_EXTENSIONS + JPEG_EXTENSIONS:
    if not any(f'ValueName: "{ext}"' in l for l in linie):
        check(f"rozszerzenie {ext} w skojarzeniach", False)
domyslne = [l for l in linie if 'ValueName: ""' in l]
check("domyslny program: kazdy RAW, zaden JPEG",
      len(domyslne) == len(RAW_EXTENSIONS)
      and all("Punctum.RAW" in l and "Tasks: skojarz_raw" in l for l in domyslne),
      str(len(domyslne)))
check("OpenWithProgids dla wszystkich typow",
      sum("OpenWithProgids" in l for l in linie) == len(RAW_EXTENSIONS) + len(JPEG_EXTENSIONS))

with open(instalator.SKRYPT, "rb") as f:
    dane = f.read()
check("punctum.iss w UTF-8 z BOM (inaczej ISCC psuje polskie napisy)", dane.startswith(b"\xef\xbb\xbf"))
tekst = dane.decode("utf-8-sig")
check("stale AppId", "AppId={{6A0F7C52-3D1B-4E8A-9C44-5B1E2F7D8A31}" in tekst)
check("instalacja bez administratora z wyborem", "PrivilegesRequired=lowest" in tekst
      and "PrivilegesRequiredOverridesAllowed=dialog" in tekst)
check("dolacza wygenerowane rozszerzenia", 'rozszerzenia.iss"' in tekst)
check("oba jezyki kreatora", "Polish.isl" in tekst and "Default.isl" in tekst)

with tempfile.TemporaryDirectory() as tmp:
    zdjecie = os.path.join(tmp, "a.rw2")
    open(zdjecie, "wb").close()
    check("argument = zdjecie -> jego katalog + zdjecie",
          rozpoznaj_argument(zdjecie) == (tmp, zdjecie), str(rozpoznaj_argument(zdjecie)))
    check("argument = katalog -> bez zdjecia", rozpoznaj_argument(tmp) == (tmp, ""))
check("bez argumentu", rozpoznaj_argument("") == ("", ""))

sys.exit(wypisz(results))
