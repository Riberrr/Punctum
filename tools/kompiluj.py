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
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEJSCIA = os.path.join(REPO, "tools", "wejscia")
sys.path.insert(0, REPO)

from punctum import __version__  # noqa: E402

IKONA = os.path.join(REPO, "punctum", "assets", "punctum.ico")


def _wersja_czworka(wersja: str) -> str:
    # Pola wersji w zasobie Windows to zawsze cztery liczby.
    czesci = [c for c in wersja.split(".") if c.isdigit()][:4]
    return ".".join(czesci + ["0"] * (4 - len(czesci)))


def _polecenie(wyjscie: str, szybko: bool) -> list[str]:
    wersja = _wersja_czworka(__version__)
    tlumaczenia = os.path.join(os.path.dirname(__import__("PySide6").__file__), "translations")
    polecenie = [
        sys.executable, "-m", "nuitka",
        "--mode=standalone",
        "--assume-yes-for-downloads",
        f"--output-dir={wyjscie}",
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
        polecenie.append(f"--include-data-files={plik}=PySide6/translations/{os.path.basename(plik)}")
    # Przegladarka mapy (QtWebEngine) szuka swoich plikow jezykowych obok
    # tlumaczen Qt; --noinclude-qt-translations wycina i je.
    for jezyk in ("pl", "en-US"):
        plik = os.path.join(tlumaczenia, "qtwebengine_locales", f"{jezyk}.pak")
        polecenie.append(f"--include-data-files={plik}=PySide6/translations/qtwebengine_locales/{jezyk}.pak")
    # Dwa punkty wejscia w jednej kompilacji (multidist): Punctum.exe
    # i PunctumMCP.exe to ten sam program, wybierajacy wejscie po nazwie pliku.
    # Osobna kompilacja mostka (bez Qt) dawala z Nuitka 4.2.2 + Python 3.14
    # plik, ktory padal na starcie: "Frozen object named 'encodings' is
    # invalid" - tak samo jak dwulinijkowy `import json`, choc pelny program
    # dzialal. Mostek i tak nie laduje Qt, wiec startuje szybko.
    # Nazwy plikow startowych malymi literami: Nuitka 4.2.2 porownuje nazwe
    # uruchomionego .exe po os.path.normcase (na Windows male litery)
    # z nazwa skryptu wzieta doslownie - "Punctum" nigdy by nie pasowalo.
    polecenie += [f"--main={os.path.join(WEJSCIA, n)}" for n in ("punctum.py", "punctummcp.py")]
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
    gotowy = os.path.join(wyjscie, "Punctum")
    if not _wolny(gotowy):
        return 1

    _uruchom(_polecenie(roboczy, szybko))

    if not _wolny(gotowy):
        return 1
    shutil.rmtree(gotowy)
    shutil.copytree(os.path.join(roboczy, "punctum.dist"), gotowy)
    # Jeden plik, dwa wejscia: nazwa .exe wybiera, ktore sie uruchomi.
    exe = os.path.join(gotowy, "punctum.exe")
    shutil.copy2(exe, os.path.join(gotowy, "PunctumMCP.exe"))
    os.replace(exe, os.path.join(gotowy, "Punctum.exe"))
    rozmiar = sum(os.path.getsize(os.path.join(k, p)) for k, _, pp in os.walk(gotowy) for p in pp)
    print(f"gotowe: {gotowy} ({rozmiar / 2**20:.0f} MB)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
