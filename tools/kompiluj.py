"""Kompilacja Punctum Nuitka do katalogu z plikami .exe (punkt 18).

    python tools/kompiluj.py [katalog_wyjsciowy] [--szybko]

Wymaga `pip install nuitka` w venv (poza requirements.txt - program go
nie potrzebuje). --szybko wylacza LTO: ~2 min zamiast kilku przy powtorce.

Domyslnie buduje do `../kompilacja` obok repozytorium - wynik jest duzy
(kilkaset MB) i nie ma prawa trafic do gita. Efekt: `<wyjscie>/Punctum/`
z Punctum.exe i PunctumMCP.exe (mostek dla klientow AI).

Dlaczego Nuitka, a nie PyInstaller: Python zamienia sie w kod maszynowy,
wiec z gotowego programu nie da sie latwo odtworzyc zrodel (PyInstaller
wklada `.pyc`, ktore sie dekompiluje). Tryb standalone (katalog, nie jeden
plik): onefile rozpakowuje sie przy kazdym starcie i daje dwa procesy.
Kompilator C Nuitka pobiera sama (Zig), Visual Studio nie jest potrzebne.

Na macOS (punkt 31 D) wynik to paczka `<wyjscie>/Punctum.app` - program
i mostek w Contents/MacOS, typy plikow w Info.plist ("Otworz za pomoca"),
podpis ad hoc. Obraz .dmg robi z niej `tools/dmg.py`. Kompilator: clang
z Xcode Command Line Tools.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEJSCIA = os.path.join(REPO, "tools", "wejscia")
sys.path.insert(0, REPO)

from punctum import __version__  # noqa: E402
from punctum.core.jpeg_loader import JPEG_EXTENSIONS  # noqa: E402
from punctum.core.loader import RAW_EXTENSIONS  # noqa: E402

IKONA = os.path.join(REPO, "punctum", "assets", "punctum.ico")
IKONA_MAC = os.path.join(REPO, "punctum", "assets", "punctum.icns")
# Skrypty w tools/ moga pytac o system (test_platforma pilnuje tylko punctum/).
MACOS = sys.platform == "darwin"
# Identyfikator paczki - nie zmieniac po pierwszym wydaniu na Maca: system
# wiaze z nim uprawnienia do katalogow i skojarzenia plikow (jak AppId w .iss).
IDENTYFIKATOR = "org.punctum.Punctum"
MAC_MIN = "12.0"  # najnizszy macOS obslugiwany przez Qt 6.11


def typy_dokumentow() -> list[dict]:
    """CFBundleDocumentTypes: Punctum na liscie "Otworz za pomoca" w Finderze.

    Rozszerzenia z core/loader.py - nowy format trafia tu sam (jak do
    skojarzen instalatora Windows). Ranga Alternate: proponujemy sie, ale
    nie odbieramy plikow domyslnemu programowi bez pytania uzytkownika.
    """
    def typ(nazwa: str, rozszerzenia: tuple[str, ...]) -> dict:
        return {
            "CFBundleTypeName": nazwa,
            "CFBundleTypeRole": "Editor",
            "LSHandlerRank": "Alternate",
            "CFBundleTypeExtensions": [e.lstrip(".") for e in rozszerzenia],
        }
    # Bez LSItemContentTypes: przy nich system pomija liste rozszerzen,
    # a nie kazdy RAW (np. .raw, .rw2 starszych systemow) ma znany typ UTI.
    return [typ("RAW", RAW_EXTENSIONS), typ("JPEG", JPEG_EXTENSIONS)]


def _wersja_czworka(wersja: str) -> str:
    # Pola wersji w zasobie Windows to zawsze cztery liczby.
    czesci = [c for c in wersja.split(".") if c.isdigit()][:4]
    return ".".join(czesci + ["0"] * (4 - len(czesci)))


def _flagi_systemu() -> list[str]:
    if MACOS:
        return [
            # Paczka .app od Nuitki: frameworki Qt (z QtWebEngineProcess)
            # ulozone tak, jak ich szuka system; Info.plist dopisujemy potem.
            "--macos-create-app-bundle",
            "--macos-app-mode=gui",
            "--macos-app-name=Punctum",
            f"--macos-app-icon={IKONA_MAC}",
            f"--macos-app-version={__version__}",
            f"--macos-signed-app-name={IDENTYFIKATOR}",
        ]
    wersja = _wersja_czworka(__version__)
    return [
        # Okno bez konsoli; mostek tez - klient AI podaje mu potoki stdin/stdout,
        # a konsola wyskakiwalaby pustym oknem (jak python.exe zamiast pythonw).
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={IKONA}",
        # Opis pliku to nazwa procesu w Menedzerze zadan (punkt 29).
        "--product-name=Punctum",
        "--file-description=Punctum",
        f"--product-version={wersja}",
        f"--file-version={wersja}",
        "--copyright=Punctum",
    ]


def _wejscia(roboczy: str) -> list[str]:
    """Pliki startowe obu programow; ich nazwy wybieraja wejscie (multidist).

    Nuitka 4.2.2 porownuje nazwe uruchomionego pliku po os.path.normcase
    z nazwa skryptu wzieta doslownie. Na Windows normcase daje male litery,
    stad pliki w repo malymi literami (punctum.exe pasuje mimo "Punctum").
    Na macOS normcase niczego nie zmienia, a programy nazywaja sie Punctum
    i PunctumMCP - wiec kopie skryptow z tymi nazwami w katalogu roboczym.
    """
    nazwy = {"punctum.py": "Punctum.py", "punctummcp.py": "PunctumMCP.py"}
    if not MACOS:
        return [os.path.join(WEJSCIA, n) for n in nazwy]
    katalog = os.path.join(roboczy, "wejscia")
    os.makedirs(katalog, exist_ok=True)
    wynik = []
    for zrodlo, cel in nazwy.items():
        shutil.copy2(os.path.join(WEJSCIA, zrodlo), os.path.join(katalog, cel))
        wynik.append(os.path.join(katalog, cel))
    return wynik


def _polecenie(wyjscie: str, szybko: bool) -> list[str]:
    from PySide6.QtCore import QLibraryInfo

    # Tlumaczenia Qt leza w kazdym systemie gdzie indziej (Windows:
    # PySide6/translations, macOS: PySide6/Qt/translations) - w paczce
    # musza trafic w to samo miejsce wzgledem pakietu PySide6.
    tlumaczenia = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    pakiety = os.path.dirname(os.path.dirname(__import__("PySide6").__file__))

    def wzglednie(plik: str) -> str:
        return os.path.relpath(plik, pakiety).replace(os.sep, "/")

    polecenie = [
        sys.executable, "-m", "nuitka",
        "--mode=standalone",
        "--assume-yes-for-downloads",
        f"--output-dir={wyjscie}",
        *_flagi_systemu(),
        "--nofollow-import-to=*.tests,tkinter,unittest,pydoc",
        "--lto=no" if szybko else "--lto=auto",
        "--enable-plugin=pyside6",
        # Leniwe __getattr__ w punctum.core / punctum.app laduje podmoduly po
        # nazwie - Nuitka nie widzi ich w importach, wiec bierze caly pakiet.
        "--include-package=punctum",
        f"--include-data-dir={os.path.join(REPO, 'punctum', 'lang')}=punctum/lang",
        f"--include-data-dir={os.path.join(REPO, 'punctum', 'assets')}=punctum/assets",
        # Historia zmian dla Pomoc > Co nowego: obok exe, tak jak w repo
        # obok pakietu (app/pomoc.py szuka jej trzy poziomy nad soba).
        f"--include-data-files={os.path.join(REPO, 'CHANGELOG.md')}=CHANGELOG.md",
        f"--include-data-files={os.path.join(REPO, 'CHANGELOG.pl.md')}=CHANGELOG.pl.md",
        # Wtyczka pyside6 dolacza wszystkie tlumaczenia Qt; interfejs ma dwa jezyki.
        "--noinclude-qt-translations",
        # Zbedny balast (~110 MB): narzedzia deweloperskie przegladarki mapy
        # i ffmpeg z OpenCV (Punctum nie czyta filmow).
        "--noinclude-data-files=qtwebengine_devtools_resources*",
        "--noinclude-dlls=cv2/opencv_videoio_ffmpeg*",
    ]
    # Przeklad okien Qt (przyciski OK/Anuluj w oknach systemowych Qt) - tylko
    # qtbase i tylko jezyki interfejsu.
    for jezyk in ("pl", "en"):
        plik = os.path.join(tlumaczenia, f"qtbase_{jezyk}.qm")
        polecenie.append(f"--include-data-files={plik}={wzglednie(plik)}")
    # Przegladarka mapy (QtWebEngine) szuka swoich plikow jezykowych obok
    # tlumaczen Qt; --noinclude-qt-translations wycina i je. Na macOS leza
    # w zasobach frameworka QtWebEngineCore, ktory wchodzi do paczki caly.
    for jezyk in ("pl", "en-US"):
        plik = os.path.join(tlumaczenia, "qtwebengine_locales", f"{jezyk}.pak")
        if MACOS and not os.path.isfile(plik):
            continue
        polecenie.append(f"--include-data-files={plik}={wzglednie(plik)}")
    # Dwa punkty wejscia w jednej kompilacji (multidist): Punctum.exe
    # i PunctumMCP.exe to ten sam program, wybierajacy wejscie po nazwie pliku.
    # Osobna kompilacja mostka (bez Qt) dawala z Nuitka 4.2.2 + Python 3.14
    # plik, ktory padal na starcie: "Frozen object named 'encodings' is
    # invalid" - tak samo jak dwulinijkowy `import json`, choc pelny program
    # dzialal. Mostek i tak nie laduje Qt, wiec startuje szybko.
    polecenie += [f"--main={p}" for p in _wejscia(wyjscie)]
    return polecenie


def _uruchom(polecenie: list[str]) -> None:
    start = time.time()
    # Pakiet punctum lezy w katalogu repozytorium, a skrypty startowe w tools/.
    srodowisko = dict(os.environ, PYTHONPATH=REPO)
    wynik = subprocess.run(polecenie, cwd=REPO, env=srodowisko)
    print(f"== Nuitka: kod {wynik.returncode}, {time.time() - start:.0f} s", flush=True)
    if wynik.returncode:
        raise SystemExit(wynik.returncode)


def _wolny(katalog: str) -> bool:
    """Czy poprzednia kompilacja da sie usunac w calosci.

    Proba przemianowania katalogu: Windows jej odmawia, gdy dziala z niego
    Punctum.exe albo mostek MCP. Wczesniej rmtree(ignore_errors) kasowalo
    polowe plikow dzialajacego programu i dopiero kopiowanie padalo.
    """
    if not os.path.exists(katalog):
        return True
    proba = katalog + "-sprawdzenie"
    try:
        os.rename(katalog, proba)
        os.rename(proba, katalog)
        return True
    except OSError:
        print(f"{katalog} jest w uzyciu - zamknij Punctum (i klienta AI z mostkiem MCP)")
        return False


def main() -> int:
    argumenty = [a for a in sys.argv[1:] if not a.startswith("--")]
    szybko = "--szybko" in sys.argv
    wyjscie = os.path.abspath(argumenty[0] if argumenty else os.path.join(REPO, "..", "kompilacja"))
    roboczy = os.path.join(wyjscie, "_nuitka")
    os.makedirs(roboczy, exist_ok=True)
    gotowy = os.path.join(wyjscie, "Punctum.app" if MACOS else "Punctum")
    if not _wolny(gotowy):
        return 1

    _uruchom(_polecenie(roboczy, szybko))

    if not _wolny(gotowy):
        return 1
    # Pierwsza kompilacja w czystym katalogu (GitHub Actions) nie ma czego
    # usuwac - rmtree bez sprawdzenia wywracal tam cale wydanie 0.10.0.
    if os.path.exists(gotowy):
        shutil.rmtree(gotowy)
    if MACOS:
        return _paczka_macos(roboczy, gotowy)
    shutil.copytree(os.path.join(roboczy, "punctum.dist"), gotowy)
    # Jeden plik, dwa wejscia: nazwa .exe wybiera, ktore sie uruchomi.
    exe = os.path.join(gotowy, "punctum.exe")
    shutil.copy2(exe, os.path.join(gotowy, "PunctumMCP.exe"))
    os.replace(exe, os.path.join(gotowy, "Punctum.exe"))
    # Licencje bibliotek z paczki (punkt 18, etap 3). Liczone tutaj, bo
    # skompilowany program nie ma juz metadanych pakietow, z ktorych powstaja.
    from punctum.core import licencje

    licencje.zapisz(gotowy, nuitka=True)
    rozmiar = sum(os.path.getsize(os.path.join(k, p)) for k, _, pp in os.walk(gotowy) for p in pp)
    print(f"gotowe: {gotowy} ({rozmiar / 2**20:.0f} MB)")
    return 0


def _paczka_macos(roboczy: str, gotowy: str) -> int:
    """Punctum.app od Nuitki -> paczka do wydania (punkt 31 D)."""
    from punctum.core import licencje

    paczki = [n for n in os.listdir(roboczy) if n.endswith(".app")]
    if len(paczki) != 1:
        print(f"oczekiwana jedna paczka .app w {roboczy}, jest: {paczki}")
        return 1
    # Przeniesienie, nie kopia: frameworki Qt sa pelne dowiazan, ktore
    # copytree bez symlinks=True zamienilby w kopie (i zepsul podpis).
    shutil.move(os.path.join(roboczy, paczki[0]), gotowy)
    programy = os.path.join(gotowy, "Contents", "MacOS")
    # Plik wykonywalny nazywa sie jak pierwszy skrypt startowy; pewnosci,
    # ze multidist z paczka nie zmieni tego w kolejnej wersji Nuitki, nie ma.
    glowny = [n for n in os.listdir(programy)
              if n.lower() == "punctum" and os.path.isfile(os.path.join(programy, n))]
    if len(glowny) != 1:
        print(f"brak pliku wykonywalnego Punctum w {programy}")
        return 1
    if glowny[0] != "Punctum":
        os.replace(os.path.join(programy, glowny[0]), os.path.join(programy, "Punctum"))
    # Mostek MCP: ten sam plik pod druga nazwa (jak PunctumMCP.exe).
    mostek = os.path.join(programy, "PunctumMCP")
    if not os.path.exists(mostek):
        shutil.copy2(os.path.join(programy, "Punctum"), mostek)

    plist = os.path.join(gotowy, "Contents", "Info.plist")
    with open(plist, "rb") as f:
        dane = plistlib.load(f)
    dane.update({
        "CFBundleExecutable": "Punctum",
        "CFBundleName": "Punctum",
        "CFBundleDisplayName": "Punctum",
        "CFBundleIdentifier": IDENTYFIKATOR,
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": MAC_MIN,
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": typy_dokumentow(),
    })
    with open(plist, "wb") as f:
        plistlib.dump(dane, f)

    licencje.zapisz(programy, nuitka=True)
    # Podpis ad hoc po wszystkich zmianach: na Apple Silicon niepodpisany
    # plik w ogole sie nie uruchomi, a zmieniony Info.plist uniewaznia
    # podpis Nuitki. Developer ID i notaryzacja to etap 31 E.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", gotowy], check=True)
    # Sprawdzenie tylko do dziennika: o tym, czy paczka dziala, rozstrzyga
    # proba startu (tools/proba_paczki.py), nie surowosc codesign.
    weryfikacja = subprocess.run(["codesign", "--verify", "--deep", "--strict", gotowy])
    print(f"codesign --verify: kod {weryfikacja.returncode}")
    rozmiar = sum(os.path.getsize(os.path.join(k, p)) for k, _, pp in os.walk(gotowy) for p in pp
                  if not os.path.islink(os.path.join(k, p)))
    print(f"gotowe: {gotowy} ({rozmiar / 2**20:.0f} MB)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
