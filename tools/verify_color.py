"""Weryfikacja matematyki koloru na realnym pliku.

Test kluczowy: mnozniki policzone przez nas dla iluminantu D65 musza
zgadzac sie z `daylight_whitebalance` zapisanym w pliku przez LibRaw.
Jesli te liczby sie rozjezdzaja, macierz kolorow jest zle uzyta i cala
reszta toru bedzie mialy przekrecone barwy.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import rawpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import whitebalance as wb  # noqa: E402

path = sys.argv[1]
with rawpy.imread(path) as raw:
    cam_xyz = np.asarray(raw.rgb_xyz_matrix, dtype=np.float64)
    daylight = np.asarray(raw.daylight_whitebalance, dtype=np.float64)[:3]
    cam_wb = np.asarray(raw.camera_whitebalance, dtype=np.float64)

ours = wb.daylight_multipliers(cam_xyz)
print("TEST 1 - mnozniki dla D65")
print(f"  z pliku LibRaw : {np.round(daylight, 4)}")
print(f"  nasze obliczone: {np.round(ours, 4)}")
err = float(np.max(np.abs(ours - daylight) / daylight)) * 100.0
print(f"  maks. roznica  : {err:.4f} %  -> {'OK' if err < 0.5 else 'BLAD'}")

print("\nTEST 2 - odtworzenie temperatury z nastawy aparatu")
temp, tint = wb.estimate_temp_tint(cam_xyz, cam_wb)
print(f"  mnozniki z aparatu : {np.round(cam_wb[:3] / cam_wb[1], 4)}")
back = wb.camera_multipliers(cam_xyz, temp, tint)
print(f"  po odtworzeniu     : {np.round(back, 4)}")
print(f"  wynik              : {temp:.0f} K, odcien {tint:+.1f}")
err2 = float(np.max(np.abs(back - cam_wb[:3] / cam_wb[1]) / back)) * 100.0
print(f"  maks. roznica      : {err2:.3f} %  -> {'OK' if err2 < 3.0 else 'BLAD'}")

print("\nTEST 3 - biel pozostaje biala po konwersji do sRGB")
mat = wb.camera_to_srgb_matrix(cam_xyz)
white = mat @ np.array([1.0, 1.0, 1.0])
print(f"  neutralny piksel aparatu -> sRGB: {np.round(white, 5)}")
dev = float(np.max(np.abs(white - 1.0)))
print(f"  odchylka od bieli  : {dev:.6f}  -> {'OK' if dev < 1e-6 else 'BLAD'}")

print("\nTEST 4 - sensownosc skali kelwinow")
for t in (2800, 4000, 5500, 6500, 9000):
    m = wb.camera_multipliers(cam_xyz, t, 0.0)
    print(f"  {t:>5} K -> R={m[0]:.3f} G={m[1]:.3f} B={m[2]:.3f}")
print("  (przy wzroscie temperatury R ma rosnac, B malec)")
