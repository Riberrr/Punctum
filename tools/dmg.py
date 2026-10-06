"""Obraz .dmg z paczki Punctum.app (punkt 31 D), tylko na macOS.

    python tools/dmg.py [katalog_kompilacji]

Po `tools/kompiluj.py` (domyslnie `../kompilacja`). W oknie obrazu leza
Punctum.app i skrot do Aplikacji - instalacja to przeciagniecie.
hdiutil jest w kazdym macOS; create-dmg (tlo, polozenie ikon) steruje
Finderem przez AppleScript, a ten na maszynie CI bez sesji graficznej
bywa zawodny.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from punctum import __version__  # noqa: E402


def nazwa_obrazu() -> str:
    # Architektura w nazwie: maszyna CI (macos-15) buduje na Apple Silicon;
    # paczka dla Maca z Intelem bylaby osobnym plikiem.
    return f"Punctum-{__version__}-macos-{platform.machine()}.dmg"


def _hdiutil(tresc: str, obraz: str) -> None:
    polecenie = ["hdiutil", "create", "-volname", f"Punctum {__version__}",
                 "-srcfolder", tresc, "-fs", "HFS+", "-format", "UDZO", "-ov", obraz]
    # hdiutil na maszynach CI potrafi raz na jakis czas odpowiedziec
    # "Resource busy" - to nie blad paczki, wystarczy chwila i ponowienie.
    for proba in range(3):
        if subprocess.run(polecenie).returncode == 0:
            return
        time.sleep(10 * (proba + 1))
    raise SystemExit("hdiutil create nie powiodl sie")


def main() -> int:
    argumenty = [a for a in sys.argv[1:] if not a.startswith("--")]
    kompilacja = os.path.abspath(argumenty[0] if argumenty else os.path.join(REPO, "..", "kompilacja"))
    paczka = os.path.join(kompilacja, "Punctum.app")
    if not os.path.isdir(paczka):
        print(f"brak {paczka} - najpierw tools/kompiluj.py")
        return 1
    obraz = os.path.join(kompilacja, nazwa_obrazu())
    with tempfile.TemporaryDirectory() as tymczasowy:
        tresc = os.path.join(tymczasowy, "Punctum")
        os.makedirs(tresc)
        # ditto zachowuje dowiazania frameworkow, atrybuty i podpis.
        subprocess.run(["ditto", paczka, os.path.join(tresc, "Punctum.app")], check=True)
        os.symlink("/Applications", os.path.join(tresc, "Applications"))
        _hdiutil(tresc, obraz)
    print(f"gotowe: {obraz} ({os.path.getsize(obraz) / 2**20:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
