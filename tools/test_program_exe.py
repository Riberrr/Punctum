"""Punctum.exe (punkt 29): opis pliku, ikona, brak podpisu, start jako venv.

Buduje kopie w katalogu tymczasowym (nie rusza .venv\\Punctum), wiec moze
chodzic przy uruchomionym programie. Tylko Windows; gdzie indziej pomija.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wspolne import wypisz  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def pole_wersji(sciezka: str, pole: str) -> str:
    """Odczyt tak, jak robi to Windows (Menedzer zadan, Eksplorator)."""
    wersja = ctypes.windll.version
    rozmiar = wersja.GetFileVersionInfoSizeW(sciezka, None)
    bufor = ctypes.create_string_buffer(rozmiar)
    if not rozmiar or not wersja.GetFileVersionInfoW(sciezka, 0, rozmiar, bufor):
        return ""
    wsk, dlugosc = ctypes.c_void_p(), ctypes.c_uint()
    if not wersja.VerQueryValueW(bufor, f"\\StringFileInfo\\040904B0\\{pole}",
                                 ctypes.byref(wsk), ctypes.byref(dlugosc)):
        return ""
    return ctypes.wstring_at(wsk.value, max(0, dlugosc.value - 1))


if sys.platform != "win32":
    check("pominiete: tylko Windows", True)
    sys.exit(wypisz(results))

import program_exe as pe  # noqa: E402
from punctum import __version__  # noqa: E402
from punctum.mcp import klienci  # noqa: E402

check("numer wersji: 4 czesci", pe._numer("0.1.0") == (0, 1, 0, 0) and pe._numer("1.2.3b4") == (1, 2, 3, 0),
      str(pe._numer("1.2.3b4")))
zasob = pe.zasob_wersji("0.1.0")
check("VERSIONINFO: dlugosc w naglowku = rozmiar", struct.unpack_from("<H", zasob)[0] == len(zasob))
obrazy, katalog = pe.zasoby_ikony()
check("ikona: katalog RT_GROUP_ICON na kazdy obraz", len(katalog) == 6 + 14 * len(obrazy) and len(obrazy) >= 4,
      str(len(obrazy)))

tmp = tempfile.mkdtemp(prefix="punctum-exe-")
try:
    shutil.copyfile(os.path.join(sys.prefix, "pyvenv.cfg"), os.path.join(tmp, "pyvenv.cfg"))
    exe = pe.utworz_exe(os.path.join(tmp, "Punctum", "Punctum.exe"))
    check("opis pliku: Punctum (nazwa w Menedzerze zadan)", pole_wersji(exe, "FileDescription") == "Punctum",
          pole_wersji(exe, "FileDescription"))
    check("wersja pliku = __version__", pole_wersji(exe, "FileVersion") == __version__,
          pole_wersji(exe, "FileVersion"))
    pe._przygotuj_api()
    check("ikona: jedna grupa, nasze obrazy", pe._zasoby_typu(exe, pe.RT_GROUP_ICON) == [(1, pe.JEZYK)]
          and len(pe._zasoby_typu(exe, pe.RT_ICON)) == len(obrazy))
    check("manifest pythonw zostal", bool(pe._zasoby_typu(exe, 24)))
    with open(exe, "rb") as plik:
        dane = plik.read()
    naglowek = struct.unpack_from("<I", dane, 0x3C)[0]
    check("bez podpisu (a nie z niewaznym)", struct.unpack_from("<II", dane, naglowek + 24 + 112 + 32) == (0, 0))
    wynik = os.path.join(tmp, "wynik.txt")
    kod = ("import sys; open(sys.argv[1], 'w', encoding='utf-8')"
           ".write(sys.prefix + '|' + sys.executable)")
    subprocess.run([exe, "-c", kod, wynik], timeout=30, check=False)
    tresc = open(wynik, encoding="utf-8").read() if os.path.exists(wynik) else ""
    check("start: jeden proces jako venv (prefix = katalog z pyvenv.cfg)",
          tresc == f"{tmp}|{exe}", tresc)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

mostek = klienci.polecenie_mostka()["command"]
check("mostek MCP: pythonw z venv, nie Punctum.exe",
      os.path.normcase(mostek) == os.path.normcase(os.path.join(sys.prefix, "Scripts", "pythonw.exe")), mostek)

sys.exit(wypisz(results))
