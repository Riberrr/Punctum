"""Wplyw demozaikowania LibRaw na szum przy wysokim ISO.

Uzycie: python tools/szum_demozaik.py <plik RAW> <katalog wyjsciowy> <wzorzec JPG>

Kolorowe "iskry" na zdjeciach ISO 6400 moga nie byc szumem czujnika, tylko
artefaktem interpolacji (AHD wzmacnia pojedyncze zaszumione piksele w
barwne plamki). Porownujemy warianty tego samego pliku bez zadnego odszumiania.
"""

from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np
import rawpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, load_raw  # noqa: E402
from punctum.core import pipeline as pl  # noqa: E402
from szum_lab import luma, match_exposure, mosaic, print_curves, CROPS  # noqa: E402

D = rawpy.DemosaicAlgorithm
VARIANTS = {
    "AHD (dzis)": {},
    "DHT": {"demosaic_algorithm": D.DHT},
    "AAHD": {"demosaic_algorithm": D.AAHD},
    "DCB": {"demosaic_algorithm": D.DCB},
    "AHD+FBDD": {"fbdd_noise_reduction": rawpy.FBDDNoiseReductionMode.Full},
    "AHD+median2": {"median_filter_passes": 2},
    "DHT+median2": {"demosaic_algorithm": D.DHT, "median_filter_passes": 2},
}


def decode(path: str, extra: dict) -> np.ndarray:
    with rawpy.imread(path) as r:
        rgb16 = r.postprocess(
            output_color=rawpy.ColorSpace.raw, use_camera_wb=True, no_auto_bright=True,
            gamma=(1.0, 1.0), output_bps=16, highlight_mode=rawpy.HighlightMode.Clip,
            user_flip=-1, **extra,
        )
    return rgb16.astype(np.float32) / 65535.0


def main() -> None:
    path, out_dir, ref = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    raw = load_raw(path)
    ref_img = cv2.imread(ref)[..., ::-1].copy()
    ev = match_exposure(raw, float(np.median(luma(ref_img))))
    named = []
    for name, extra in VARIANTS.items():
        t = time.perf_counter()
        try:
            lin = decode(path, extra)
        except Exception as exc:  # starsze LibRaw nie maja wszystkich algorytmow
            print(f"{name}: niedostepne ({exc})")
            continue
        print(f"{name}: {time.perf_counter() - t:.2f} s")
        named.append((name, pl._to_uint8(pl.apply_tone(lin, raw, EditParams(exposure=ev)))))
    named.append(("LR 50", ref_img))
    print_curves(named)
    for key, rect in CROPS.items():
        cv2.imwrite(os.path.join(out_dir, f"demozaik_{key}.png"), mosaic(named, rect)[..., ::-1])


if __name__ == "__main__":
    main()
