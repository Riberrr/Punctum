"""Kod zalezny od systemu (punkt 31): `punctum/core/platforma.py`.

Na Windows sprawdza zachowanie dotychczasowe, a na maszynie macOS w CI
(`.github/workflows/testy.yml`) to, czego bez Maca nie da sie zobaczyc:
sysctl daje rdzenie i pamiec, pliki pism znaku wodnego istnieja,
interpreter mostka jest z venv. Do tego zasada: reszta programu nie pyta
sama o system.
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

from punctum.core import hardware, platforma, settings, znak_wodny  # noqa: E402
from punctum.mcp import klienci  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


check("dokladnie jeden system", [platforma.WINDOWS, platforma.MACOS, platforma.LINUX].count(True) == 1)
check("katalog ustawien przez platforme",
      settings.config_directory() == platforma.katalog_ustawien()
      and settings.config_directory().endswith("Punctum"), settings.config_directory())
if platforma.MACOS:
    check("macOS: ustawienia w Application Support",
          "/Library/Application Support/" in settings.config_directory())

# Skroty: zamiana tylko na macOS, ale sama zamiana sprawdzana wszedzie.
stary = platforma.MACOS
try:
    platforma.MACOS = True
    check("skroty macOS", platforma.skroty_w_tekscie("Ctrl+Shift+Z, Alt+klik") == "⌘⇧Z, ⌥klik",
          platforma.skroty_w_tekscie("Ctrl+Shift+Z, Alt+klik"))
    platforma.MACOS = False
    check("skroty Windows bez zmian", platforma.skroty_w_tekscie("Ctrl+O") == "Ctrl+O")
finally:
    platforma.MACOS = stary

# Sprzet: na Macu /proc nie ma - wczesniej wychodzilo tu 0.
cpu = hardware.detect_cpu()
check("rdzenie fizyczne > 0", cpu.cores_physical > 0, str(cpu.cores_physical))
check("pamiec > 0", cpu.memory_gb > 0, f"{cpu.memory_gb:.1f}")
check("nazwa procesora", bool(cpu.name), cpu.name)

# Znak wodny: co najmniej jedno pismo z listy platformy daje sie wczytac
# (inaczej zostaje mala czcionka zastepcza Pillow).
from PIL import ImageFont  # noqa: E402

ladowalne = []
for nazwa in platforma.CZCIONKI_ZNAKU:
    try:
        ImageFont.truetype(nazwa, 20)
        ladowalne.append(nazwa)
    except OSError:
        pass
check("pismo znaku wodnego z listy", bool(ladowalne), str(platforma.CZCIONKI_ZNAKU))
check("znak wodny bierze liste platformy",
      znak_wodny.CZCIONKI[:len(platforma.CZCIONKI_ZNAKU)] == platforma.CZCIONKI_ZNAKU)

# Mostek MCP ze zrodel: interpreter z tego samego venv, istnieje.
wpis = klienci.polecenie_mostka()
check("interpreter mostka istnieje", os.path.isfile(wpis["command"]), wpis["command"])
if not platforma.WINDOWS:
    check("bez pythonw.exe poza Windows", not wpis["command"].endswith(".exe"), wpis["command"])
check("nazwa skompilowanego mostka",
      platforma.nazwa_mostka_skompilowanego() == ("PunctumMCP.exe" if platforma.WINDOWS else "PunctumMCP"))

# Klienci MCP: Claude Desktop i VS Code w katalogu danych aplikacji systemu.
check("APPDATA klientow = katalog danych",
      klienci._kat("APPDATA") == platforma.katalog_danych_aplikacji()
      or "APPDATA" in klienci._KATALOGI)

# Zasada: o system pyta tylko platforma.py.
PYTANIE = re.compile(r"sys\.platform|platform\.system\(\)\s*==|os\.name\s*==")
winni = []
for katalog, _, pliki in os.walk(os.path.join(REPO, "punctum")):
    for nazwa in pliki:
        if not nazwa.endswith(".py") or nazwa == "platforma.py":
            continue
        sciezka = os.path.join(katalog, nazwa)
        with open(sciezka, encoding="utf-8") as plik:
            for nr, linia in enumerate(plik, 1):
                if PYTANIE.search(linia) and not linia.lstrip().startswith("#"):
                    winni.append(f"{os.path.relpath(sciezka, REPO)}:{nr}")
check("o system pyta tylko platforma.py", not winni, ", ".join(winni))

# Dwie serie testow (cmd i bash) maja te same listy - inaczej CI na macOS
# po cichu pomijaloby test dopisany tylko do testy.bat.
LISTA = re.compile(r"for (?:%%T in \(|T in )([a-z_ ]+)")
listy = {}
for nazwa in ("testy.bat", "testy.sh"):
    with open(os.path.join(TOOLS, nazwa), encoding="utf-8") as plik:
        listy[nazwa] = [m.split() for m in LISTA.findall(plik.read())]
check("testy.bat i testy.sh: te same testy",
      listy["testy.bat"] == listy["testy.sh"] and len(listy["testy.bat"]) == 2,
      str([len(x) for x in listy["testy.bat"]]) + " / " + str([len(x) for x in listy["testy.sh"]]))

sys.exit(wypisz(results))
