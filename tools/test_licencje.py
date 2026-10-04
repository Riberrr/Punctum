"""Licencje zewnetrzne i wydanie w GitHub Actions (punkt 18, etap 3).

Pilnuje tego, co latwo zgubic przy zmianie zaleznosci: kazdy pakiet
z requirements.txt ma wpis z tekstem licencji, Qt ma pelny tekst LGPL,
kompilacja i instalator dolaczaja plik, a workflow wydania ma przypiete
wersje wszystkich pakietow programu. Okno sprawdzane offscreen.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, REPO)
sys.path.insert(0, TOOLS)

from wspolne import wypisz  # noqa: E402

from punctum import __version__  # noqa: E402
from punctum.core import licencje  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def czytaj(*czesci: str) -> str:
    with open(os.path.join(REPO, *czesci), encoding="utf-8-sig") as f:
        return f.read()


lista = licencje.skladniki(nuitka=True)
klucze = {licencje._klucz(s.nazwa): s for s in lista}
wymagane = [licencje._klucz(n) for n in licencje._wymagania()]
brak = [n for n in wymagane if n not in klucze]
check("kazdy pakiet z requirements.txt w spisie", not brak, str(brak))
bez_tekstu = [s.nazwa for s in lista if not s.teksty and licencje._klucz(s.nazwa) not in licencje.QT]
check("kazdy skladnik (poza Qt) z tekstem licencji", not bez_tekstu, str(bez_tekstu))
bez_nazwy = [s.nazwa for s in lista if s.licencja == "see text below"]
check("kazdy skladnik z nazwa licencji", not bez_nazwy, str(bez_nazwy))
check("Python z tekstem PSF", "python" in klucze
      and any("PYTHON SOFTWARE FOUNDATION" in t.upper() for _, t in klucze["python"].teksty))
pelny = licencje.zbuduj(nuitka=True)
check("pelny tekst LGPL v3 i GPL v3 (Qt)",
      "GNU LESSER GENERAL PUBLIC LICENSE" in pelny and "GNU GENERAL PUBLIC LICENSE" in pelny
      and "Version 3, 29 June 2007" in pelny)
check("LibRaw w tekstach rawpy", any("LibRaw" in tytul for tytul, _ in klucze["rawpy"].teksty))
check("runtime Nuitki w kompilacji", any(s.nazwa == "Nuitka runtime" and s.teksty for s in lista))
check("naglowek z numerem wersji", f"Punctum {__version__}" in pelny.splitlines()[0])
dom = os.path.expanduser("~")
check("bez sciezek z dysku w pliku", dom not in pelny and sys.base_prefix not in pelny)

with tempfile.TemporaryDirectory() as tmp:
    sciezka = licencje.zapisz(tmp, nuitka=True)
    check("zapis pliku do katalogu kompilacji",
          os.path.basename(sciezka) == licencje.NAZWA_PLIKU and os.path.getsize(sciezka) > 100_000)
    stary = licencje.KATALOG_GLOWNY
    licencje.KATALOG_GLOWNY = tmp
    with open(sciezka, "w", encoding="utf-8") as f:
        f.write("gotowy plik z kompilacji")
    check("program czyta gotowy plik obok exe", licencje.tekst() == "gotowy plik z kompilacji")
    licencje.KATALOG_GLOWNY = stary
check("ze zrodel liczony na miejscu", "GNU LESSER" in licencje.tekst())

import instalator  # noqa: E402

for kod in ("pl", "en"):
    krotki = instalator.strona_licencji(kod)
    check(f"strona kreatora ({kod}): spis i odeslanie do pliku",
          licencje.NAZWA_PLIKU in krotki and "PySide6" in krotki and "LGPL" in krotki)

kompiluj = czytaj("tools", "kompiluj.py")
check("kompilacja zapisuje plik licencji", "licencje.zapisz(gotowy, nuitka=True)" in kompiluj)
instalator = czytaj("tools", "instalator.py")
check("instalator wymaga pliku i generuje strone", "licencje.NAZWA_PLIKU" in instalator
      and "strona_licencji(kod)" in instalator)
iss = czytaj("tools", "punctum.iss")
check("strona licencji w kreatorze w obu jezykach",
      all(f'InfoBeforeFile: "{{#Generowane}}\\licencje.{k}.txt"' in iss for k in ("pl", "en")))

# Workflow wydania: przypiete wersje kazdego pakietu programu.
przypiete = {licencje._klucz(m.group(1)) for m in
             re.finditer(r"^([\w.-]+)==", czytaj("tools", "wymagania-kompilacji.txt"), re.M)}
check("wymagania-kompilacji: kazdy pakiet przypiety",
      set(wymagane) <= przypiete and "nuitka" in przypiete, str(set(wymagane) - przypiete))
wf = czytaj(".github", "workflows", "wydanie.yml")
check("workflow: tag v*, sprawdzenie main, sumy, Releases",
      'tags: ["v*"]' in wf and "merge-base --is-ancestor" in wf and "SHA256" in wf
      and "gh release create" in wf and "opis_wydania.py" in wf and "testy.bat --szybkie" in wf)

import opis_wydania  # noqa: E402

opis = opis_wydania.opis(__version__)
check("opis wydania z CHANGELOG.md", len(opis) > 100 and "## " not in opis.split("\n")[0], opis[:60])
check("brak sekcji = pusto", opis_wydania.sekcja("0.0.0") == "")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
from punctum.app.pomoc import OknoPomocy  # noqa: E402

okno = OknoPomocy("", "x", zwykly=pelny)
check("okno pokazuje teksty licencji", "GNU LESSER" in okno.przegladarka.toPlainText())
okno.close()

sys.exit(wypisz(results))
