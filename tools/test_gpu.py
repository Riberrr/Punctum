"""Zgodnosc i wydajnosc toru GPU wzgledem toru numpy.

Dwa tory liczace ten sam obraz to zawsze ryzyko, ze podglad zacznie pokazywac
co innego niz wyeksportowany plik. Dlatego porownujemy je piksel po pikselu
na kilku zestawach parametrow, lacznie z geometria.
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication(sys.argv)

from punctum.app.gpu_renderer import GpuRenderer  # noqa: E402
from punctum.core import EditParams, develop, geometry_size, load_raw  # noqa: E402

path = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "out/gpu"
os.makedirs(out_dir, exist_ok=True)

renderer = GpuRenderer()
print(f"OpenGL dostępny : {renderer.available}")
if not renderer.available:
    print(f"powód           : {renderer.error}")
    raise SystemExit(1)
print(f"karta           : {renderer.hardware}")

raw = load_raw(path)
proxy = raw.proxy(1600)
print(f"proxy           : {proxy.shape[1]}x{proxy.shape[0]}")

start = time.perf_counter()
renderer.set_source(proxy.camera_linear)
print(f"wgranie tekstury: {(time.perf_counter() - start) * 1000:.0f} ms (raz na zdjęcie)\n")

CASES = {
    "bez zmian": EditParams(),
    "podstawowe suwaki": EditParams(
        exposure=0.57, contrast=7, highlights=-76, shadows=28,
        whites=14, blacks=-19, vibrance=15, saturation=5,
    ),
    "balans bieli": EditParams(temperature=4200.0, tint=-30, exposure=0.4),
    "kadr": EditParams(exposure=0.5, crop=(0.15, 0.10, 0.85, 0.80)),
    "obrót płynny": EditParams(exposure=0.5, rotation=6.5),
    "obrót 90°": EditParams(exposure=0.5, orientation=90),
    "obrót 270° + kadr": EditParams(orientation=270, crop=(0.2, 0.1, 0.9, 0.95), contrast=20),
    "wszystko naraz": EditParams(
        temperature=6800.0, tint=12, exposure=0.8, contrast=15, highlights=-40,
        shadows=45, whites=10, blacks=-12, vibrance=20, saturation=-8,
        orientation=180, rotation=-3.2, crop=(0.05, 0.08, 0.92, 0.9),
    ),
}

print(f"{'przypadek':<22}{'różnica śr.':>13}{'maks.':>8}{'>2 poz.':>10}{'GPU ms':>9}{'CPU ms':>9}")
print("-" * 71)

worst = 0.0
for name, params in CASES.items():
    out_w, out_h = geometry_size(proxy, params)

    start = time.perf_counter()
    gpu = renderer.render(raw, params, out_w, out_h)
    gpu_ms = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    cpu = develop(proxy, params, denoise=False)
    cpu_ms = (time.perf_counter() - start) * 1000

    if gpu is None:
        print(f"{name:<22}{'BŁĄD RENDEROWANIA':>13}  {renderer.error}")
        continue
    if gpu.shape != cpu.shape:
        print(f"{name:<22}  rozmiary różne: GPU {gpu.shape} CPU {cpu.shape}")
        continue

    diff = np.abs(gpu.astype(np.int16) - cpu.astype(np.int16))
    # krawedzie kadru roznia sie sposobem probkowania poza obrazem - pomijamy 2 px
    inner = diff[2:-2, 2:-2]
    mean, maximum = float(inner.mean()), int(inner.max())
    over = 100.0 * float((inner > 2).mean())
    worst = max(worst, mean)
    print(f"{name:<22}{mean:>13.3f}{maximum:>8}{over:>9.2f}%{gpu_ms:>9.1f}{cpu_ms:>9.0f}")

    import cv2
    cv2.imwrite(f"{out_dir}/gpu_{name[:12].replace(' ', '_')}.png",
                cv2.cvtColor(gpu, cv2.COLOR_RGB2BGR))

print(f"\nnajgorsza średnia różnica: {worst:.3f} poziomu jasności "
      f"-> {'OK' if worst < 1.5 else 'ZA DUŻO'}")

print("\n--- wydajność przy powtarzanych zmianach suwaka ---")
params = EditParams(exposure=0.5, contrast=10, shadows=30)
out_w, out_h = geometry_size(proxy, params)
renderer.render(raw, params, out_w, out_h)  # rozgrzewka
times = []
for i in range(30):
    params.exposure = 0.3 + i * 0.02
    start = time.perf_counter()
    renderer.render(raw, params, out_w, out_h)
    times.append((time.perf_counter() - start) * 1000)
times = np.array(times)
print(f"  mediana {np.median(times):.1f} ms, najgorszy {times.max():.1f} ms "
      f"-> {'PŁYNNIE' if np.median(times) < 16 else 'ZA WOLNO'}")
print(f"  odpowiednik w klatkach na sekundę: {1000 / np.median(times):.0f}")

print(f"\nobrazy w {out_dir}")
