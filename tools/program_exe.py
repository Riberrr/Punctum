"""Wlasny plik Punctum.exe do uruchamiania programu ze zrodel (Windows, punkt 29).

Uzycie:  .venv\\Scripts\\python.exe tools\\program_exe.py
(wola go tez tools\\utworz_skroty.py, wiec zwykle nie trzeba osobno).

Dlaczego: skrot na .venv\\Scripts\\pythonw.exe daje w Menedzerze zadan grupe
"Python (2)" - pythonw z venv to tylko posrednik, ktory uruchamia drugi,
wlasciwy pythonw z instalacji Pythona. Nazwa "Python" i ikona procesu
pochodza z zasobow pliku .exe (VERSIONINFO, RT_GROUP_ICON), nie z okna,
wiec z kodu programu ich nie zmienimy.

Co robimy: kopiujemy bazowy pythonw.exe (z bibliotekami DLL, ktorych
potrzebuje) do .venv\\Punctum\\Punctum.exe i podmieniamy w kopii ikone oraz
opis pliku. Katalog nad kopia (.venv) ma pyvenv.cfg, a Python szuka go obok
programu i poziom wyzej - kopia startuje wiec od razu jako interpreter venv,
w jednym procesie. Kopia lezy w .venv, poza repozytorium, bo zalezy od
Pythona zainstalowanego na tym komputerze; po aktualizacji Pythona trzeba
ja zrobic na nowo (ponowne uruchomienie tego skryptu).

Podpis cyfrowy oryginalu po podmianie zasobow bylby niewazny, dlatego go
usuwamy - plik niepodpisany jest uczciwszy niz podpisany z bledem.
Po kompilacji (punkt 18) to samo zrobi PyInstaller/Nuitka i ten skrypt
przestanie byc potrzebny.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import struct
import sys
from ctypes import wintypes

KATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KATALOG not in sys.path:
    sys.path.insert(0, KATALOG)

from punctum import __version__  # noqa: E402

NAZWA = "Punctum"
IKONA = os.path.join(KATALOG, "punctum", "assets", "punctum.ico")
DOCELOWY = os.path.join(KATALOG, ".venv", NAZWA, NAZWA + ".exe")

RT_ICON, RT_GROUP_ICON, RT_VERSION = 3, 14, 16
JEZYK = 0x0409  # en-US, standardowy jezyk zasobow; tabela napisow 040904B0


# ------------------------------------------------------------ VERSIONINFO


def _wyrownaj(dane: bytes) -> bytes:
    return dane + b"\0" * (-len(dane) % 4)


def _wezel(klucz: str, wartosc: bytes = b"", *, tekst: bool, dlugosc: int = 0,
           dzieci: tuple[bytes, ...] = ()) -> bytes:
    """Jeden blok struktury VS_VERSIONINFO: naglowek, klucz, wartosc, dzieci.

    Kazdy element zaczyna sie na granicy 4 bajtow - Windows czyta te bloki
    po przesunieciach, wiec bez wyrownania VerQueryValue nie znajdzie pol.
    `dlugosc` to wValueLength: w znakach dla napisow, w bajtach dla danych.
    """
    tresc = _wyrownaj(struct.pack("<HHH", 0, 0, 0) + (klucz + "\0").encode("utf-16-le"))[6:]
    tresc += wartosc
    if dzieci:
        tresc = _wyrownaj(struct.pack("<HHH", 0, 0, 0) + tresc)[6:]
        tresc += b"".join(_wyrownaj(d) for d in dzieci)
    return struct.pack("<HHH", 6 + len(tresc), dlugosc, 1 if tekst else 0) + tresc


def _napis(klucz: str, wartosc: str) -> bytes:
    return _wezel(klucz, (wartosc + "\0").encode("utf-16-le"), tekst=True,
                  dlugosc=len(wartosc) + 1)


def _numer(wersja: str) -> tuple[int, int, int, int]:
    # "1.2.3b4" -> 1.2.3.0: liczy sie tylko poczatek kazdej czesci, bo
    # doklejenie cyfr z "3b4" daloby bzdurne 34
    czesci = [int(re.match(r"\d*", c).group() or 0) for c in wersja.split(".")]
    czesci = (czesci + [0, 0, 0, 0])[:4]
    return tuple(czesci)  # type: ignore[return-value]


def zasob_wersji(wersja: str = __version__) -> bytes:
    """Zasob RT_VERSION. FileDescription to nazwa, ktora Menedzer zadan
    pokazuje przy procesie i przy grupie w "Aplikacjach"."""
    a, b, c, d = _numer(wersja)
    stale = struct.pack(
        "<13I", 0xFEEF04BD, 0x00010000,
        (a << 16) | b, (c << 16) | d, (a << 16) | b, (c << 16) | d,
        0x3F, 0, 0x00040004, 1, 0, 0, 0,  # maska, flagi, VOS_NT_WINDOWS32, VFT_APP
    )
    napisy = (
        _napis("FileDescription", NAZWA),
        _napis("ProductName", NAZWA),
        _napis("FileVersion", wersja),
        _napis("ProductVersion", wersja),
        _napis("InternalName", NAZWA),
        _napis("OriginalFilename", NAZWA + ".exe"),
        _napis("Comments", "Photo editor for RAW and JPEG files"),
    )
    tabela = _wezel("040904B0", tekst=True, dzieci=napisy)
    pliki = _wezel("StringFileInfo", tekst=True, dzieci=(tabela,))
    tlumaczenie = _wezel("Translation", struct.pack("<HH", JEZYK, 1200), tekst=False, dlugosc=4)
    zmienne = _wezel("VarFileInfo", tekst=True, dzieci=(tlumaczenie,))
    return _wezel("VS_VERSION_INFO", stale, tekst=False, dlugosc=len(stale),
                  dzieci=(pliki, zmienne))


# ------------------------------------------------------------ ikona


def zasoby_ikony(sciezka: str = IKONA) -> tuple[list[bytes], bytes]:
    """Plik .ico -> obrazy RT_ICON (numery 1..n) i katalog RT_GROUP_ICON.

    W .ico wpis katalogu konczy sie przesunieciem do danych (4 bajty),
    w zasobie - numerem obrazu RT_ICON (2 bajty); reszta wpisu jest ta sama.
    """
    with open(sciezka, "rb") as plik:
        dane = plik.read()
    _, typ, ile = struct.unpack_from("<HHH", dane, 0)
    if typ != 1 or ile == 0:
        raise ValueError(f"to nie jest plik ikony: {sciezka}")
    obrazy, katalog = [], struct.pack("<HHH", 0, 1, ile)
    for i in range(ile):
        wpis = dane[6 + 16 * i: 6 + 16 * (i + 1)]
        rozmiar, przesuniecie = struct.unpack_from("<II", wpis, 8)
        obrazy.append(dane[przesuniecie: przesuniecie + rozmiar])
        katalog += wpis[:12] + struct.pack("<H", i + 1)
    return obrazy, katalog


# ------------------------------------------------------------ plik PE


def usun_podpis(sciezka: str) -> None:
    """Zeruje katalog certyfikatow (Security) i obcina podpis z konca pliku.

    Podpis Authenticode lezy za obrazem programu; po podmianie zasobow
    skrot pliku sie nie zgadza, a EndUpdateResource podpisu nie przelicza.
    """
    with open(sciezka, "r+b") as plik:
        dane = bytearray(plik.read())
        pe = struct.unpack_from("<I", dane, 0x3C)[0]
        if dane[pe:pe + 4] != b"PE\0\0":
            raise ValueError(f"to nie jest plik PE: {sciezka}")
        opcjonalny = pe + 24
        magia = struct.unpack_from("<H", dane, opcjonalny)[0]
        katalogi = opcjonalny + (112 if magia == 0x20B else 96)  # PE32+ / PE32
        wpis = katalogi + 4 * 8  # IMAGE_DIRECTORY_ENTRY_SECURITY
        przesuniecie, rozmiar = struct.unpack_from("<II", dane, wpis)
        if not rozmiar:
            return
        struct.pack_into("<II", dane, wpis, 0, 0)
        plik.seek(0)
        plik.write(dane[:przesuniecie])
        plik.truncate()


_k32 = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None
_NAZWY = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_ssize_t)
_JEZYKI = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.WORD, ctypes.c_ssize_t)


def _przygotuj_api() -> None:
    k = _k32
    k.LoadLibraryExW.restype = wintypes.HMODULE
    k.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    k.FreeLibrary.argtypes = [wintypes.HMODULE]
    k.EnumResourceNamesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, _NAZWY, ctypes.c_ssize_t]
    k.EnumResourceLanguagesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p,
                                         _JEZYKI, ctypes.c_ssize_t]
    k.BeginUpdateResourceW.restype = wintypes.HANDLE
    k.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    k.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    k.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]


def _zasoby_typu(sciezka: str, typ: int) -> list[tuple[object, int]]:
    """(nazwa, jezyk) wszystkich zasobow danego typu. Nazwa to liczba albo
    napis - zasoby moga miec nazwy tekstowe, a ich wskaznik zyje tylko
    w trakcie wyliczania, wiec napis kopiujemy od razu."""
    modul = _k32.LoadLibraryExW(sciezka, None, 0x2 | 0x20)  # jako dane i obraz zasobow
    if not modul:
        raise ctypes.WinError(ctypes.get_last_error())
    wynik: list[tuple[object, int]] = []

    def nazwa_z(wsk: int) -> object:
        return wsk if wsk < 0x10000 else ctypes.wstring_at(wsk)

    try:
        nazwy: list[object] = []
        _k32.EnumResourceNamesW(modul, typ, _NAZWY(lambda m, t, n, p: nazwy.append(nazwa_z(n)) or True), 0)
        for nazwa in nazwy:
            bufor = None if isinstance(nazwa, int) else ctypes.create_unicode_buffer(nazwa)
            wsk = nazwa if bufor is None else ctypes.addressof(bufor)
            _k32.EnumResourceLanguagesW(
                modul, typ, wsk, _JEZYKI(lambda m, t, n, j, p, x=nazwa: wynik.append((x, j)) or True), 0)
    finally:
        _k32.FreeLibrary(modul)
    return wynik


def podmien_zasoby(sciezka: str, wersja: str = __version__) -> None:
    """Usuwa ikony i opis pythonw, wpisuje nasze. Reszta zasobow (manifest
    z DPI i dlugimi sciezkami) zostaje - bez niej okno Qt skalowaloby sie
    inaczej niz przy zwyklym pythonw."""
    _przygotuj_api()
    stare = [(typ, nazwa, jezyk) for typ in (RT_ICON, RT_GROUP_ICON, RT_VERSION)
             for nazwa, jezyk in _zasoby_typu(sciezka, typ)]
    uchwyt = _k32.BeginUpdateResourceW(sciezka, False)
    if not uchwyt:
        raise ctypes.WinError(ctypes.get_last_error())
    trzymane = []  # bufory musza zyc do EndUpdateResource

    def zapisz(typ: int, nazwa: object, jezyk: int, dane: bytes | None) -> None:
        if isinstance(nazwa, str):
            bufor = ctypes.create_unicode_buffer(nazwa)
            trzymane.append(bufor)
            nazwa = ctypes.addressof(bufor)
        wsk, dlugosc = None, 0
        if dane is not None:
            blok = ctypes.create_string_buffer(dane, len(dane))
            trzymane.append(blok)
            wsk, dlugosc = ctypes.addressof(blok), len(dane)
        if not _k32.UpdateResourceW(uchwyt, typ, nazwa, jezyk, wsk, dlugosc):
            raise ctypes.WinError(ctypes.get_last_error())

    try:
        for typ, nazwa, jezyk in stare:
            zapisz(typ, nazwa, jezyk, None)  # brak danych = usun zasob
        obrazy, katalog = zasoby_ikony()
        for numer, obraz in enumerate(obrazy, start=1):
            zapisz(RT_ICON, numer, JEZYK, obraz)
        zapisz(RT_GROUP_ICON, 1, JEZYK, katalog)
        zapisz(RT_VERSION, 1, JEZYK, zasob_wersji(wersja))
    except BaseException:
        _k32.EndUpdateResourceW(uchwyt, True)  # porzuc zmiany
        raise
    if not _k32.EndUpdateResourceW(uchwyt, False):
        raise ctypes.WinError(ctypes.get_last_error())


def pliki_pythona() -> tuple[str, list[str]]:
    """Bazowy pythonw.exe i biblioteki, ktore laduje przy starcie z wlasnego
    katalogu (Windows szuka DLL najpierw obok programu)."""
    baza = sys.base_prefix
    dll = [f"python{sys.version_info.major}{sys.version_info.minor}.dll", "python3.dll",
           "vcruntime140.dll", "vcruntime140_1.dll"]
    return (os.path.join(baza, "pythonw.exe"),
            [os.path.join(baza, n) for n in dll if os.path.isfile(os.path.join(baza, n))])


def utworz_exe(cel: str = DOCELOWY) -> str:
    """Buduje Punctum.exe w katalogu `cel`. Najpierw plik tymczasowy, na
    koncu podmiana - dziala tez, gdy stary Punctum.exe jest uruchomiony
    (wtedy PermissionError z czytelnym opisem)."""
    if sys.platform != "win32":
        raise OSError("Punctum.exe jest tylko na Windows")
    if sys.prefix == sys.base_prefix:
        raise OSError("uruchom skrypt interpreterem z .venv - kopia ma startowac jako venv")
    katalog = os.path.dirname(cel)
    if not os.path.isfile(os.path.join(os.path.dirname(katalog), "pyvenv.cfg")):
        raise OSError(f"brak pyvenv.cfg nad {katalog}")
    os.makedirs(katalog, exist_ok=True)
    program, biblioteki = pliki_pythona()
    tymczasowy = cel + ".nowy"
    shutil.copyfile(program, tymczasowy)
    try:
        usun_podpis(tymczasowy)
        podmien_zasoby(tymczasowy)
        try:
            for dll in biblioteki:
                shutil.copyfile(dll, os.path.join(katalog, os.path.basename(dll)))
            os.replace(tymczasowy, cel)
        except PermissionError as blad:
            raise PermissionError(f"{blad.filename}: plik w uzyciu - zamknij Punctum i powtorz") from blad
    finally:
        if os.path.exists(tymczasowy):
            os.remove(tymczasowy)
    return cel


def main() -> int:
    try:
        print(f"program: {utworz_exe()}")
    except OSError as blad:
        print(f"Nie udalo sie zbudowac {NAZWA}.exe: {blad}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
