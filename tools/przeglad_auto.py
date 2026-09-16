"""Przeglad automatu na prawdziwych zdjeciach.

Sklada arkusz porownawczy "przed / po" z probki plikow RAW rozrzuconej po
calym zbiorze, zeby zobaczyc automat na scenach, ktorych nikt nie dobieral
pod niego specjalnie. Uzycie:

    python tools/przeglad_auto.py <katalog> [ile] [plik_wyjsciowy]
"""

from __future__ import annotations

import os
import random
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, load_raw
from punctum.core.auto import analyse, auto_tone_from
from punctum.core.pipeline import apply_tone

RAW_SUFFIXES = (".rw2", ".raw", ".arw", ".cr2", ".nef", ".dng")
TILE_WIDTH = 420


def collect(root: str, count: int) -> list[str]:
    """Probka rozrzucona po katalogach - po jednym pliku z kazdego."""
    by_folder: dict[str, list[str]] = {}
    for folder, _, names in os.walk(root):
        picked = [n for n in names if n.lower().endswith(RAW_SUFFIXES)]
        if picked:
            by_folder[folder] = sorted(picked)
    rng = random.Random(7)
    folders = sorted(by_folder)
    rng.shuffle(folders)
    for names in by_folder.values():
        rng.shuffle(names)

    # Po kolei z kazdego katalogu, dopiero potem drugie okrazenie - probka
    # rozklada sie na rozne wyjazdy i pory roku nawet wtedy, gdy katalogow
    # jest mniej niz zdjec do pokazania.
    chosen: list[str] = []
    for round_index in range(max(len(v) for v in by_folder.values())):
        for folder in folders:
            names = by_folder[folder]
            if round_index < len(names):
                chosen.append(os.path.join(folder, names[round_index]))
                if len(chosen) >= count:
                    return chosen
    return chosen


def render(raw, params: EditParams) -> np.ndarray:
    """Maly podglad calego kadru, bez geometrii i odszumiania."""
    source = raw.camera_linear
    h, w = source.shape[:2]
    scale = TILE_WIDTH / float(w)
    small = cv2.resize(source, (TILE_WIDTH, max(1, int(h * scale))),
                       interpolation=cv2.INTER_AREA)
    rgb = apply_tone(small, raw, params)
    return (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]


def label(tile: np.ndarray, text: str) -> np.ndarray:
    """Pasek opisowy pod kafelkiem - tylko ASCII, bo cv2 nie zna ogonkow."""
    bar = np.full((22, tile.shape[1], 3), 24, dtype=np.uint8)
    cv2.putText(bar, text, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (235, 235, 235), 1, cv2.LINE_AA)
    return np.vstack([tile, bar])


def main() -> None:
    root = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    out_path = sys.argv[3] if len(sys.argv) > 3 else "out/przeglad_auto.jpg"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    paths = collect(root, count)
    print(f"{'plik':<22}{'klucz':<11}{'ciemne':>7}{'zakres':>7}{'EV':>7}"
          f"{'L* med':>8}{'swiat':>7}{'cien':>6}{'biele':>7}{'czern':>7}"
          f"{'kontr':>7}{'nasyc':>7}")
    print("-" * 110)

    rows: list[np.ndarray] = []
    for path in paths:
        try:
            raw = load_raw(path)
            scene = analyse(raw)
            values = auto_tone_from(scene)
        except Exception as error:  # plik uszkodzony nie moze zatrzymac calosci
            print(f"{os.path.basename(path):<22}  blad: {error}")
            continue

        params = EditParams(**{k: v for k, v in values.items()})
        gain = 2.0 ** values["exposure"]
        from punctum.core.auto import linear_to_lstar
        median_after = float(linear_to_lstar(scene.p50 * gain))
        name = os.path.basename(path)
        print(f"{name:<22}{scene.key:<11}{scene.dark_share:>7.2f}"
              f"{scene.range_ev:>7.1f}{values['exposure']:>7.2f}{median_after:>8.1f}"
              f"{values['highlights']:>7.0f}{values['shadows']:>6.0f}"
              f"{values['whites']:>7.0f}{values['blacks']:>7.0f}"
              f"{values['contrast']:>7.0f}{values['vibrance']:>7.0f}")

        before = label(render(raw, EditParams()), f"{name}  oryginal")
        after = label(render(raw, params),
                      f"EV{values['exposure']:+.2f}  s{values['highlights']:+.0f}"
                      f"  c{values['shadows']:+.0f}  k{values['contrast']:+.0f}"
                      f"  [{scene.key}]")
        height = min(before.shape[0], after.shape[0])
        rows.append(np.hstack([before[:height], after[:height]]))

    width = max(row.shape[1] for row in rows)
    padded = [np.pad(row, ((0, 0), (0, width - row.shape[1]), (0, 0)),
                     constant_values=24) for row in rows]
    sheet = np.vstack([np.pad(row, ((0, 8), (0, 0), (0, 0)), constant_values=24)
                       for row in padded])
    cv2.imwrite(out_path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"\narkusz: {os.path.abspath(out_path)}  ({sheet.shape[1]}x{sheet.shape[0]})")


if __name__ == "__main__":
    main()
