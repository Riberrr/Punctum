"""Wszystko, co zalezy od systemu operacyjnego, w jednym miejscu (punkt 31).

Reszta programu nie pyta sama o `sys.platform` - pyta tutaj. Dzieki temu
wersja na macOS to jedna linia kodu z Windows, a nie osobna galaz, w ktorej
kazda poprawke trzeba by przenosic drugi raz.

Modul nie zalezy od Qt (korzysta z niego `core` i przeklad napisow).
"""

from __future__ import annotations

import os
import subprocess
import sys

APP_NAME = "Punctum"

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
LINUX = not (WINDOWS or MACOS)


# ------------------------------------------------------------------ katalogi

def katalog_danych_aplikacji() -> str:
    """Odpowiednik %APPDATA%: tam programy trzymaja ustawienia uzytkownika.

    Na macOS klienci AI (Claude Desktop, VS Code) tez pisza konfiguracje
    do ~/Library/Application Support - wiec ten sam katalog sluzy do
    szukania ich plikow w `mcp/klienci.py`.
    """
    if WINDOWS:
        return os.environ.get("APPDATA") or os.path.expanduser("~")
    if MACOS:
        return os.path.expanduser("~/Library/Application Support")
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def katalog_ustawien() -> str:
    return os.path.join(katalog_danych_aplikacji(), APP_NAME)


# ------------------------------------------------------------------ pisma

# Pisma interfejsu w kolejnosci preferencji. Qt bierze pierwsze dostepne,
# wiec lista dziala tez wtedy, gdy ktoregos kroju w systemie brak.
# ".AppleSystemUIFont" to nazwa, pod ktora Qt widzi San Francisco - pisma
# systemowego macOS nie da sie wybrac nazwa "San Francisco".
if MACOS:
    PISMA_INTERFEJSU = (".AppleSystemUIFont", "Helvetica Neue", "Helvetica")
    PISMA_POGRUBIONE = (".AppleSystemUIFont", "Helvetica Neue")
    PISMA_STALE = ("Menlo", "Monaco")
    # Pliki dla Pillow (znak wodny). Pelne sciezki: Pillow przeszukuje
    # katalogi pism rekurencyjnie przy kazdej probie, a Segoe UI na Macu
    # nie ma - lista z Windows kosztowalaby kilka przeszukan na darmo.
    CZCIONKI_ZNAKU = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    )
elif WINDOWS:
    PISMA_INTERFEJSU = ("Segoe UI",)
    # Na Windows polgruby kroj to osobna rodzina; sama waga DemiBold
    # dawala zwykly Segoe UI i nazwa wygladala blado.
    PISMA_POGRUBIONE = ("Segoe UI Semibold", "Segoe UI")
    PISMA_STALE = ("Consolas",)
    CZCIONKI_ZNAKU = ("seguisb.ttf", "segoeui.ttf", "arial.ttf")
else:
    PISMA_INTERFEJSU = ("Segoe UI", "Noto Sans", "DejaVu Sans")
    PISMA_POGRUBIONE = PISMA_INTERFEJSU
    PISMA_STALE = ("DejaVu Sans Mono",)
    CZCIONKI_ZNAKU = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf")


def pisma_css(pisma: tuple[str, ...], zapasowe: str = "sans-serif") -> str:
    """Lista pism dla arkusza stylow Qt albo CSS strony mapy."""
    return ", ".join([f'"{p}"' for p in pisma] + [zapasowe])


# ------------------------------------------------------------------ skroty

# Kolejnosc ma znaczenie: Ctrl przed Shift/Alt, bo "Ctrl+Shift+Z"
# ma dac "⌘⇧Z", a nie "⌘Shift+Z".
_SKROTY_MACOS = (("Ctrl+", "⌘"), ("Shift+", "⇧"), ("Alt+", "⌥"))


def skroty_w_tekscie(tekst: str) -> str:
    """Zapis skrotow w napisach i dymkach tak, jak pokazuje go system.

    Qt sam zamienia Ctrl na Cmd w `QKeySequence` (akcje w menu dzialaja
    i podpisuja sie dobrze), ale napisy w dymkach i pasku stanu sa zwyklym
    tekstem z plikow przekladu - stad zamiana tutaj, w jednym miejscu.
    """
    if not MACOS or "+" not in tekst:
        return tekst
    for windows, mac in _SKROTY_MACOS:
        tekst = tekst.replace(windows, mac)
    return tekst


# ------------------------------------------------------------------ sprzet

def sysctl(nazwa: str) -> str:
    """Wartosc z `sysctl -n` (macOS); pusty napis, gdy sie nie uda."""
    try:
        wynik = subprocess.run(["sysctl", "-n", nazwa], capture_output=True,
                               text=True, timeout=3, check=False)
        return wynik.stdout.strip()
    except Exception:
        return ""


# ------------------------------------------------------------------ interpreter

def interpreter_mostka(prefix: str, executable: str) -> str:
    """Interpreter, ktorym klient AI uruchomi mostek MCP ze zrodel.

    Windows: pythonw z katalogu Scripts venv - python.exe otwieralby puste
    okno konsoli, a program startowany przez Punctum.exe (punkt 29) ma
    sys.executable w .venv\\Punctum. macOS/Linux: bin/python3 venv (tam nie
    ma okien konsoli ani pythonw).
    """
    if WINDOWS:
        katalogi = (os.path.join(prefix, "Scripts"), os.path.dirname(executable))
        nazwy = ("pythonw.exe", "python.exe")
    else:
        katalogi = (os.path.join(prefix, "bin"), os.path.dirname(executable))
        nazwy = ("python3", "python")
    for katalog in katalogi:
        for nazwa in nazwy:
            kandydat = os.path.join(katalog, nazwa)
            if os.path.isfile(kandydat):
                return kandydat
    return executable


def nazwa_mostka_skompilowanego() -> str:
    return "PunctumMCP.exe" if WINDOWS else "PunctumMCP"
