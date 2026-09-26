"""Skroty uruchamiajace Punctum: na pulpicie i w menu Start (Windows).

Uzycie:  .venv\\Scripts\\python.exe tools\\utworz_skroty.py [--bez-pulpitu]

Skrot uruchamia pythonw.exe z `-m punctum` - bez okna konsoli, z ikona
programu. Przeciagniety na skrot folder ze zdjeciami otwiera sie od razu
(Windows dopisuje go jako argument). Skrot dostaje ten sam identyfikator
programu (APP_ID) co okno, wiec skrot przypiety do paska zadan i uruchomiony
program to jedna ikona, a nie dwie.

Sciezki liczone na miejscu, z polozenia tego pliku - skrypt dziala na
kazdym komputerze i nie zapisuje nic do repozytorium. Uruchomic ponownie po
przeniesieniu katalogu programu.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import uuid
from ctypes import wintypes

KATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KATALOG)

from punctum import APP_ID  # noqa: E402

PYTHONW = os.path.join(KATALOG, ".venv", "Scripts", "pythonw.exe")
IKONA = os.path.join(KATALOG, "punctum", "assets", "punctum.ico")
OPIS = "Punctum — edytor zdjęć RAW i JPEG"


def folder_specjalny(nazwa: str) -> str:
    """Pulpit i menu Start z Windows, nie z %USERPROFILE% - pulpit bywa
    przeniesiony do OneDrive i zgadywana sciezka trafilaby obok."""
    wynik = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"[Environment]::GetFolderPath('{nazwa}')"],
        capture_output=True, text=True, check=True,
    )
    return wynik.stdout.strip()


def utworz_skrot(sciezka: str) -> None:
    # WScript.Shell z PowerShella: najprostsza droga do .lnk bez pywin32.
    # Apostrofy podwojone, bo sciezki ida w cudzyslowach PowerShella.
    def ps(tekst: str) -> str:
        return "'" + tekst.replace("'", "''") + "'"

    polecenie = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + ps(sciezka) + ");"
        f"$s.TargetPath = {ps(PYTHONW)};"
        "$s.Arguments = '-m punctum';"
        f"$s.WorkingDirectory = {ps(KATALOG)};"
        f"$s.IconLocation = {ps(IKONA + ',0')};"
        f"$s.Description = {ps(OPIS)};"
        "$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", polecenie], check=True)


# --- identyfikator programu w skrocie (IPropertyStore przez ctypes) --------


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def z_tekstu(cls, tekst: str) -> "GUID":
        u = uuid.UUID(tekst)
        g = cls(u.time_low, u.time_mid, u.time_hi_version)
        g.Data4[:] = list(u.bytes[8:])
        return g


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    # wariant uproszczony: typ + wskaznik na napis; 24 bajty jak w Windows x64
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort), ("wskaznik", ctypes.c_void_p), ("zapas", ctypes.c_void_p)]


VT_LPWSTR = 31
GPS_READWRITE = 2
IID_IPropertyStore = GUID.z_tekstu("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")
PKEY_AppUserModel_ID = PROPERTYKEY(GUID.z_tekstu("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"), 5)


def ustaw_app_id(sciezka: str, app_id: str) -> None:
    ole32, shell32 = ctypes.windll.ole32, ctypes.windll.shell32
    ole32.CoInitialize(None)
    magazyn = ctypes.c_void_p()
    hr = shell32.SHGetPropertyStoreFromParsingName(
        ctypes.c_wchar_p(sciezka), None, GPS_READWRITE,
        ctypes.byref(IID_IPropertyStore), ctypes.byref(magazyn),
    )
    if hr != 0:
        raise OSError(f"SHGetPropertyStoreFromParsingName: 0x{hr & 0xFFFFFFFF:08x}")
    # Tabela metod IPropertyStore: 0-2 IUnknown, 6 SetValue, 7 Commit.
    tabela = ctypes.cast(ctypes.cast(magazyn, ctypes.POINTER(ctypes.c_void_p))[0],
                         ctypes.POINTER(ctypes.c_void_p))
    set_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY),
                                   ctypes.POINTER(PROPVARIANT))(tabela[6])
    commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(tabela[7])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(tabela[2])
    napis = ctypes.create_unicode_buffer(app_id)
    wartosc = PROPVARIANT(vt=VT_LPWSTR, wskaznik=ctypes.cast(napis, ctypes.c_void_p).value)
    try:
        for nazwa, wynik in (("SetValue", set_value(magazyn, ctypes.byref(PKEY_AppUserModel_ID),
                                                     ctypes.byref(wartosc))),
                             ("Commit", commit(magazyn))):
            if wynik != 0:
                raise OSError(f"{nazwa}: 0x{wynik & 0xFFFFFFFF:08x}")
    finally:
        release(magazyn)


def main() -> int:
    if sys.platform != "win32":
        print("Skroty .lnk sa tylko na Windows. Na innych systemach: python -m punctum")
        return 1
    if not os.path.isfile(PYTHONW):
        print(f"Brak {PYTHONW} - najpierw utworz srodowisko .venv (README).")
        return 1
    cele = [os.path.join(folder_specjalny("Programs"), "Punctum.lnk")]
    if "--bez-pulpitu" not in sys.argv:
        cele.append(os.path.join(folder_specjalny("Desktop"), "Punctum.lnk"))
    for cel in cele:
        utworz_skrot(cel)
        try:
            ustaw_app_id(cel, APP_ID)
            dopisek = ""
        except OSError as blad:  # skrot i tak dziala, gorzej tylko z przypinaniem
            dopisek = f"  (bez identyfikatora programu: {blad})"
        print(f"skrot: {cel}{dopisek}")
    print("Gotowe. Punctum uruchomisz z pulpitu albo z menu Start; "
          "skrot z menu Start mozna przypiac do paska zadan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
