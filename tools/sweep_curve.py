"""Dobor krzywej suwaka odszumiania.

Non-local means nasyca sie bardzo szybko: przy sile 25 usuwa juz prawie caly
szum, wiec liniowe odwzorowanie suwaka na parametr h daje martwy zakres
od 30 do 100. Szukamy krzywej, przy ktorej kolejne kroki suwaka daja
rownomierne przyrosty efektu.
"""

from __future__ import annotations

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, develop_region, load_raw

raw = load_raw(sys.argv[1])
RECT = (1500, 700, 500, 340)
params = EditParams(exposure=1.0, shadows=30)
base = develop_region(raw, params, RECT, scale=1.0, denoise=False)
y_base = cv2.cvtColor(base, cv2.COLOR_RGB2YCrCb)[..., 0]


def noise(y: np.ndarray) -> float:
    f = y.astype(np.float32)
    return float((f - cv2.GaussianBlur(f, (0, 0), 9.0)).std())


CURVES = {
    "liniowa  2+20s": lambda s: 2.0 + 20.0 * s,
    "kwadrat  1.5+16s^2": lambda s: 1.5 + 16.0 * s**2,
    "potega   1.5+15s^1.8": lambda s: 1.5 + 15.0 * s**1.8,
    "szescian 1.0+18s^3": lambda s: 1.0 + 18.0 * s**3,
}

start = noise(y_base)
steps = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
print(f"szum wyjsciowy: {start:.2f}\n")
print(f"{'krzywa':<22}" + "".join(f"{s:>6}" for s in steps))
print("-" * (22 + 6 * len(steps)))

for name, curve in CURVES.items():
    row = []
    for step in steps:
        if step == 0:
            row.append(start)
            continue
        h = curve(step / 100.0)
        row.append(noise(cv2.fastNlMeansDenoising(y_base, None, h, 5, 11)))
    print(f"{name:<22}" + "".join(f"{v:>6.2f}" for v in row))
    # rownomiernosc: odchylenie przyrostow miedzy kolejnymi krokami
    diffs = np.diff(row)
    print(f"{'  rownomiernosc':<22}{np.std(diffs) / max(abs(np.mean(diffs)), 1e-6):>6.2f}"
          "  (mniej = lepiej)")
