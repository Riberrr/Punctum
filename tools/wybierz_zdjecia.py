"""Wybiera zdjecia do testow z interfejsem i wypisuje je w jednej linii.

Testy potrzebuja trzech plikow: jednego RAW-a i dwoch JPEG-ow. Wczesniej ich
nazwy staly wprost w `tools/testy.bat`, razem ze sciezka do prywatnego katalogu
ze zdjeciami - w publicznym repozytorium nie ma to czego szukac, a na cudzym
komputerze i tak nie zadziala. Teraz katalog podaje sie z zewnatrz, a pliki
znajduja sie same.

Uzycie:  python tools/wybierz_zdjecia.py <katalog>
Wypisuje:  "<raw>" "<jpeg>" "<jpeg>"   (albo nic i kod wyjscia 1)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core.loader import JPEG_EXTENSIONS, RAW_EXTENSIONS  # noqa: E402


def pick(folder: str) -> list[str]:
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    raws, jpegs = [], []
    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        suffix = os.path.splitext(name)[1].lower()
        if suffix in RAW_EXTENSIONS:
            raws.append(path)
        elif suffix in JPEG_EXTENSIONS:
            jpegs.append(path)
    if not raws or len(jpegs) < 2:
        return []
    return [raws[0], jpegs[0], jpegs[1]]


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    chosen = pick(sys.argv[1])
    if not chosen:
        return 1
    print(" ".join(f'"{path}"' for path in chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
