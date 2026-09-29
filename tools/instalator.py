"""Instalator Windows z gotowej kompilacji (punkt 18, etap 2).

    python tools/instalator.py [katalog_kompilacji]

Najpierw `tools/kompiluj.py` (domyslnie `../kompilacja`), potem ten skrypt:
bierze `<katalog>/Punctum/`, sklada go Inno Setupem wedlug
`tools/punctum.iss` i zapisuje `<katalog>/Punctum-<wersja>-setup.exe`.

Inno Setup 6 nie jest w requirements.txt - to program Windows
(`winget install JRSoftware.InnoSetup`). ISCC szukamy w PATH i w typowych
miejscach instalacji (dla uzytkownika i dla wszystkich).

Lista rozszerzen do skojarzen powstaje tutaj z `core/loader.py` i trafia do
pliku dolaczanego przez punctum.iss - dzieki temu nowy format RAW
w programie od razu dostaje skojarzenie, bez recznej zmiany skryptu.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from punctum import __version__  # noqa: E402
from punctum.core.jpeg_loader import JPEG_EXTENSIONS  # noqa: E402
from punctum.core.loader import RAW_EXTENSIONS  # noqa: E402
from kompiluj import _wersja_czworka  # noqa: E402

SKRYPT = os.path.join(REPO, "tools", "punctum.iss")
# Tla i znak kreatora - generuje tools/make_assets.py.
GRAFIKA = os.path.join(REPO, "tools", "instalator_grafika")


def znajdz_iscc() -> str | None:
    kandydaci = [shutil.which("iscc")]
    for baza in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        katalog = os.environ.get(baza)
        if katalog:
            sub = os.path.join("Programs", "Inno Setup 6") if baza == "LOCALAPPDATA" else "Inno Setup 6"
            kandydaci.append(os.path.join(katalog, sub, "ISCC.exe"))
    return next((k for k in kandydaci if k and os.path.isfile(k)), None)


def wpisy_rozszerzen() -> list[str]:
    """Linie sekcji [Registry] dla kazdego rozszerzenia."""
    linie = []
    for ext, progid, domyslny in (
        [(e, "Punctum.RAW", True) for e in RAW_EXTENSIONS]
        + [(e, "Punctum.JPEG", False) for e in JPEG_EXTENSIONS]
    ):
        klasa = f"Software\\Classes\\{ext}"
        # OpenWithProgids: Punctum w "Otworz za pomoca" dla tego typu;
        # usuwana tylko nasza wartosc, reszta klucza nalezy do innych programow.
        linie.append(f'Root: HKA; Subkey: "{klasa}\\OpenWithProgids"; ValueType: string; '
                     f'ValueName: "{progid}"; ValueData: ""; Flags: uninsdeletevalue')
        linie.append(f'Root: HKA; Subkey: "Software\\Classes\\Applications\\Punctum.exe\\SupportedTypes"; '
                     f'ValueType: string; ValueName: "{ext}"; ValueData: ""')
        linie.append(f'Root: HKA; Subkey: "Software\\Punctum\\Capabilities\\FileAssociations"; '
                     f'ValueType: string; ValueName: "{ext}"; ValueData: "{progid}"')
        if domyslny:
            # Domyslny program tylko dla RAW i tylko z zadaniem. Wybor
            # uzytkownika w Windows (UserChoice) i tak ma pierwszenstwo.
            linie.append(f'Root: HKA; Subkey: "{klasa}"; ValueType: string; ValueName: ""; '
                         f'ValueData: "{progid}"; Flags: uninsdeletevalue; Tasks: skojarz_raw')
    return linie


def main() -> int:
    argumenty = sys.argv[1:]
    katalog = os.path.abspath(argumenty[0] if argumenty else os.path.join(REPO, "..", "kompilacja"))
    zrodlo = os.path.join(katalog, "Punctum")
    for plik in ("Punctum.exe", "PunctumMCP.exe"):
        if not os.path.isfile(os.path.join(zrodlo, plik)):
            print(f"brak {plik} w {zrodlo} - najpierw tools/kompiluj.py")
            return 1
    wynikowy = os.path.join(katalog, f"Punctum-{__version__}-setup.exe")
    try:
        # Otwarty kreator trzyma swoj plik - ISCC padlby dopiero po
        # kompresji z mniej czytelnym bledem 32.
        if os.path.exists(wynikowy):
            open(wynikowy, "r+b").close()
    except OSError:
        print(f"{wynikowy} jest otwarty - zamknij okno instalatora")
        return 1
    iscc = znajdz_iscc()
    if not iscc:
        print("nie znaleziono ISCC.exe - winget install JRSoftware.InnoSetup")
        return 1

    with tempfile.TemporaryDirectory(prefix="punctum-instalator-") as generowane:
        with open(os.path.join(generowane, "rozszerzenia.iss"), "w", encoding="utf-8-sig") as f:
            f.write("\n".join(wpisy_rozszerzen()) + "\n")
        polecenie = [
            iscc, "/Q",
            f"/DWersja={__version__}",
            f"/DWersja4={_wersja_czworka(__version__)}",
            f"/DZrodlo={zrodlo}",
            f"/DWyjscie={katalog}",
            f"/DRepo={REPO}",
            f"/DGenerowane={generowane}",
            f"/DGrafika={GRAFIKA}",
            SKRYPT,
        ]
        start = time.time()
        wynik = subprocess.run(polecenie)
    if wynik.returncode:
        print(f"ISCC zakonczyl sie kodem {wynik.returncode}")
        return wynik.returncode
    plik = os.path.join(katalog, f"Punctum-{__version__}-setup.exe")
    print(f"gotowe: {plik} ({os.path.getsize(plik) / 2**20:.0f} MB, {time.time() - start:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
