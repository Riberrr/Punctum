"""Odszumianie widziane przy powiekszeniu - tak, jak oglada je uzytkownik.

Kluczowy warunek poprawnosci: przy powiekszeniu 400 % suwak musi robic
widoczna roznice. Wczesniej tor liczyl odszumianie PO powiekszeniu, wiec
ziarno bylo czterokrotnie wieksze niz zasieg filtra i suwak nie robil nic.
"""

from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, develop_region, load_raw

path = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "out/zoom"
os.makedirs(out_dir, exist_ok=True)

raw = load_raw(path)
ZOOM = 4.0
# fragment nieba nad budynkami - tam szum widac najlepiej
RECT = (1500, 700, 320, 220)


def noise_level(rgb: np.ndarray) -> float:
    y = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    return float((y - cv2.GaussianBlur(y, (0, 0), 9.0)).std())


print(f"powiekszenie {ZOOM * 100:.0f} %, fragment {RECT[2]}x{RECT[3]} px natywnych")
print(f"\n{'suwak luminancji':>18}{'szum':>9}{'czas ms':>10}")
print("-" * 37)

for slider in (0, 25, 50, 75, 100):
    params = EditParams(exposure=1.0, shadows=30, noise_luminance=slider, noise_color=60)
    start = time.perf_counter()
    image = develop_region(raw, params, RECT, scale=ZOOM, denoise=True, quality="balanced")
    elapsed = (time.perf_counter() - start) * 1000
    # szum mierzymy na obrazie zmniejszonym do skali natywnej, zeby liczba
    # opisywala dane, a nie stopien powiekszenia
    native = cv2.resize(image, (RECT[2], RECT[3]), interpolation=cv2.INTER_AREA)
    print(f"{slider:>18}{noise_level(native):>9.2f}{elapsed:>10.0f}")
    cv2.imwrite(f"{out_dir}/luminancja_{slider:03d}.png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))

print("\n--- koszt przy roznych powiekszeniach (suwak 60) ---")
params = EditParams(exposure=1.0, shadows=30, noise_luminance=60, noise_color=60)
for zoom, rect in ((1.0, (1500, 700, 1280, 880)), (2.0, (1500, 700, 640, 440)),
                   (4.0, (1500, 700, 320, 220)), (8.0, (1500, 700, 160, 110))):
    start = time.perf_counter()
    develop_region(raw, params, rect, scale=zoom, denoise=True, quality="balanced")
    print(f"  {zoom * 100:>5.0f} %  okno 1280x880 ekranu  ->  "
          f"{(time.perf_counter() - start) * 1000:>5.0f} ms")

print(f"\nobrazy w {out_dir}")
