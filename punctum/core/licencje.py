"""Licencje zewnetrzne: skladniki dolaczane do programu i ich warunki (punkt 18, etap 3).

Punctum nie ma licencji open source, ale biblioteki w paczce wymagaja
dolaczenia swoich tekstow (Qt/PySide6 - LGPL, LibRaw, OpenCV, Python...).
Zrodlo prawdy to metadane zainstalowanych pakietow (dist-info): nowa
zaleznosc w requirements.txt sama trafia do pliku, razem z zaleznosciami
zaleznosci. W kompilacji dist-info juz nie ma, dlatego tools/kompiluj.py
zapisuje gotowy plik obok Punctum.exe, a program czyta go stamtad.
"""

from __future__ import annotations

import os
import platform
import re
import sys
from dataclasses import dataclass, field

NAZWA_PLIKU = "THIRD-PARTY-LICENSES.txt"
# Tak jak CHANGELOG: w repo katalog glowny, w kompilacji katalog z exe -
# w obu przypadkach trzy poziomy nad tym modulem.
KATALOG_GLOWNY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KATALOG_TEKSTOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "assets", "licencje")
REQUIREMENTS = os.path.join(KATALOG_GLOWNY, "requirements.txt")

QT = {"pyside6", "pyside6-essentials", "pyside6-addons", "shiboken6"}
# Kolo wheeli PySide6 maja w dist-info tylko odsylacz do licencji handlowej
# Qt - nas dotyczy LGPL, ktorej tekst trzymamy sami (assets/licencje).
POMIJANE_PLIKI = re.compile(r"LicenseRef-Qt-Commercial", re.I)

# To, czego nie ma w metadanych: biblioteki wszyte w pakiety i obowiazki
# LGPL (wymienialne biblioteki, skad wziac zrodla).
UWAGI = {
    "pyside6": (
        "Qt 6 and Qt for Python are used under the GNU Lesser General Public License v3 "
        "(full text below, together with the GNU GPL v3 it refers to). The Qt libraries "
        "are shipped as separate DLL files in the program folder and are not modified; "
        "you may replace them with your own compatible build. Source code: "
        "https://download.qt.io/official_releases/qt/ and "
        "https://code.qt.io/cgit/pyside/pyside-setup.git/ . Qt WebEngine (used for the map) "
        "contains Chromium and other third-party code, listed at "
        "https://doc.qt.io/qt-6/qtwebengine-licensing.html ."
    ),
    "rawpy": "rawpy contains LibRaw, used under the GNU LGPL v2.1 or CDDL v1.0 (see LICENSE.LibRaw below).",
    "opencv-python": "The OpenCV wheel bundles further libraries, listed in LICENSE-3RD-PARTY.txt below.",
    "pillow": "The Pillow wheel bundles further libraries (libjpeg-turbo, libpng, zlib and others), listed below.",
    "numpy": "The NumPy wheel bundles OpenBLAS and other code, listed below.",
}
# Pakiety bez nazwy licencji w metadanych (sprawdzone w ich tekscie licencji).
ZNANE = {"exifread": "BSD-3-Clause"}
LEAFLET = (
    "Leaflet 1.9.4 (BSD-2-Clause, https://leafletjs.com/) and map tiles from OpenStreetMap "
    "(data (c) OpenStreetMap contributors, ODbL) are loaded from the internet when the map "
    "is shown; they are not part of this package."
)


@dataclass
class Skladnik:
    nazwa: str
    wersja: str
    licencja: str
    teksty: list[tuple[str, str]] = field(default_factory=list)  # (tytul, tresc)
    uwaga: str = ""


def _klucz(nazwa: str) -> str:
    return re.sub(r"[-_.]+", "-", nazwa).lower()


def _wymagania() -> list[str]:
    nazwy = []
    with open(REQUIREMENTS, encoding="utf-8") as f:
        for linia in f:
            linia = linia.split("#")[0].strip()
            if linia:
                nazwy.append(re.split(r"[<>=!~;\[ ]", linia, maxsplit=1)[0])
    return nazwy


def _licencja(meta) -> str:
    wyrazenie = meta.get("License-Expression")
    if wyrazenie:
        return wyrazenie
    klasyfikatory = [c.rsplit("::", 1)[-1].strip() for c in (meta.get_all("Classifier") or [])
                     if c.startswith("License ::")]
    if klasyfikatory:
        return ", ".join(klasyfikatory)
    # Pole License bywa calym tekstem licencji (ExifRead: sama nota
    # o prawach autorskich) - wtedy nazwy w nim nie ma, odsylamy do tekstu.
    pole = (meta.get("License") or "").strip()
    if not pole or "\n" in pole or len(pole) > 120 or pole.lower().startswith("copyright"):
        return ZNANE.get(_klucz(meta["Name"]), "see text below")
    return pole


def _teksty(dystrybucja) -> list[tuple[str, str]]:
    wynik = []
    for plik in dystrybucja.files or []:
        sciezka = str(plik).replace("\\", "/")
        nazwa = sciezka.rsplit("/", 1)[-1]
        # Tylko pliki z dist-info: te same teksty leza czesto drugi raz
        # w samym pakiecie (cv2/LICENSE.txt), a duplikatow nikt nie czyta.
        if ".dist-info/" not in sciezka or POMIJANE_PLIKI.search(nazwa):
            continue
        if not re.search(r"LICEN[CS]E|COPYING|NOTICE", nazwa, re.I):
            continue
        pelna = dystrybucja.locate_file(plik)
        try:
            with open(pelna, encoding="utf-8", errors="replace") as f:
                tytul = sciezka.split(".dist-info/", 1)[1]
                wynik.append((tytul, f.read().strip()))
        except OSError:
            pass
    return wynik


def _zaleznosci(meta) -> list[str]:
    nazwy = []
    for wpis in meta.get_all("Requires-Dist") or []:
        # Dodatki opcjonalne (extra == ...) nie sa instalowane z programem.
        if ";" in wpis and "extra" in wpis.split(";", 1)[1]:
            continue
        nazwy.append(re.split(r"[<>=!~;\[ (]", wpis.strip(), maxsplit=1)[0])
    return nazwy


def skladniki(nuitka: bool = False) -> list[Skladnik]:
    """Pakiety z requirements.txt i ich zaleznosci, plus Python i (w kompilacji) Nuitka."""
    import importlib.metadata as md

    lista = [Skladnik("Python", platform.python_version(), "PSF-2.0",
                      _python_teksty())]
    widziane: set[str] = set()
    kolejka = _wymagania()
    while kolejka:
        nazwa = kolejka.pop(0)
        klucz = _klucz(nazwa)
        if klucz in widziane:
            continue
        widziane.add(klucz)
        try:
            d = md.distribution(nazwa)
        except md.PackageNotFoundError:
            continue
        lista.append(Skladnik(d.metadata["Name"], d.version, _licencja(d.metadata),
                              _teksty(d), UWAGI.get(klucz, "")))
        kolejka += _zaleznosci(d.metadata)
    if any(_klucz(s.nazwa) in QT for s in lista):
        lista.append(Skladnik("GNU licenses for Qt", "", "LGPL-3.0, GPL-3.0", [
            (n, open(os.path.join(KATALOG_TEKSTOW, n), encoding="utf-8").read().strip())
            for n in ("LGPL-3.0.txt", "GPL-3.0.txt")]))
    if nuitka:
        try:
            d = md.distribution("nuitka")
            teksty = [(t, s) for t, s in _teksty(d) if "RUNTIME" in t.upper()]
            # Wyjatek dla runtime pozwala rozpowszechniac skompilowany program
            # na dowolnych warunkach - AGPL dotyczy tylko samego kompilatora.
            lista.append(Skladnik("Nuitka runtime", d.version,
                                  "AGPL-3.0 with Nuitka Runtime Library Exception", teksty,
                                  "Punctum is compiled with Nuitka. Only the Nuitka runtime "
                                  "library is part of the program, under the exception below."))
        except md.PackageNotFoundError:
            pass
    return lista


def _python_teksty() -> list[tuple[str, str]]:
    # Windows trzyma licencje Pythona w katalogu glownym instalacji, macOS
    # i Linux obok biblioteki standardowej (lib/python3.X/LICENSE.txt).
    kandydaci = [os.path.join(sys.base_prefix, "LICENSE.txt"),
                 os.path.join(sys.base_prefix, "LICENSE"),
                 os.path.join(os.path.dirname(os.__file__), "LICENSE.txt")]
    sciezka = next((k for k in kandydaci if os.path.isfile(k)), kandydaci[0])
    try:
        with open(sciezka, encoding="utf-8", errors="replace") as f:
            return [("LICENSE.txt", f.read().strip())]
    except OSError:
        return []


KRESKA = "=" * 78


def zbuduj(nuitka: bool = False) -> str:
    """Pelny plik: spis skladnikow, potem teksty licencji po kolei."""
    from .. import __version__

    lista = skladniki(nuitka)
    czesci = [
        f"Punctum {__version__} - third-party software",
        "",
        "Punctum includes the components listed below. Each is distributed under its own",
        "license; the full texts follow the list.",
        "",
    ]
    for s in lista:
        czesci.append(f"  {s.nazwa} {s.wersja}".rstrip() + f"  -  {s.licencja}")
    czesci += ["", LEAFLET, ""]
    for s in lista:
        czesci += [KRESKA, f"{s.nazwa} {s.wersja}".rstrip(), KRESKA, ""]
        if s.uwaga:
            czesci += [s.uwaga, ""]
        for tytul, tresc in s.teksty:
            czesci += [f"--- {tytul} ---", "", tresc, ""]
    return "\n".join(czesci) + "\n"


def zapisz(katalog: str, nuitka: bool = False) -> str:
    sciezka = os.path.join(katalog, NAZWA_PLIKU)
    with open(sciezka, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(zbuduj(nuitka))
    return sciezka


def tekst() -> str:
    """Dla okna w programie: gotowy plik z kompilacji albo, ze zrodel, liczony na miejscu."""
    sciezka = os.path.join(KATALOG_GLOWNY, NAZWA_PLIKU)
    if os.path.isfile(sciezka):
        with open(sciezka, encoding="utf-8") as f:
            return f.read()
    return zbuduj()


def spis(nuitka: bool = True) -> list[str]:
    """Linie "nazwa wersja - licencja" na strone kreatora instalacji.

    Zdania wokol spisu (pl/en) sklada tools/instalator.py - ten modul nie
    ma napisow ekranowych.
    """
    return [f"  \u2022 {s.nazwa} {s.wersja} \u2014 {s.licencja}" for s in skladniki(nuitka) if s.wersja]
