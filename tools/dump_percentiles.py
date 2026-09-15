"""Rozklad jasnosci w danych liniowych - podstawa do kalibracji automatu."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import load_raw
from punctum.core.auto import _analysis_image
from punctum.core.params import EditParams
from punctum.core.pipeline import LUMA

LEVELS = [0.2, 2, 10, 25, 50, 75, 90, 99, 99.8]

print(f"{'plik':<14}" + "".join(f"{f'p{v:g}':>9}" for v in LEVELS))
for path in sys.argv[1:]:
    raw = load_raw(path)
    img = _analysis_image(raw, EditParams())
    lum = np.maximum(img @ LUMA, 0.0).ravel()
    values = np.percentile(lum, LEVELS)
    stem = os.path.splitext(os.path.basename(path))[0]
    print(f"{stem:<14}" + "".join(f"{v:>9.4f}" for v in values))

    # ile dzialek EV trzeba dodac, zeby dany percentyl trafil w szarosc 18%
    ev = np.log2(0.18 / np.maximum(values, 1e-6))
    print(f"{'  EV do 0.18':<14}" + "".join(f"{v:>+9.2f}" for v in ev))
