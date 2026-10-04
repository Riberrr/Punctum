"""Odszumianie koloru na karcie (app/gpu_kolor.py) wobec wersji z procesora.

Punkt 32: podglad z karty dostaje odszumiony kolor od razu, zamiast po
chwili z procesora - inaczej barwy przeskakiwaly przy kazdym zatrzymaniu
suwaka. Warunek: wynik karty prawie rowny `apply_noise_reduction` (tej samej
funkcji co eksport), na podgladzie parzystym i nieparzystym oraz na wycinku
1:1 i powiekszonym 2x (wobec `develop_region`).

Uzycie: python tools/test_gpu_kolor.py <zdjecia...>
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import replace

import numpy as np
from PySide6.QtGui import QGuiApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wspolne import wypisz, zdjecia  # noqa: E402

app = QGuiApplication.instance() or QGuiApplication(sys.argv)

from punctum.app.gpu_renderer import GpuRenderer  # noqa: E402
from punctum.core import default_params_for, develop_region, geometry_size, is_jpeg, load_photo  # noqa: E402
from punctum.core.denoise import apply_noise_reduction  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def porownaj(nazwa: str, a: np.ndarray, b: np.ndarray, srednia: float, ponad2: float) -> None:
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    udzial = float((d > 2).mean()) * 100.0
    check(nazwa, a.shape == b.shape and float(d.mean()) < srednia and udzial < ponad2,
          f"srednia {d.mean():.3f}, max {d.max()}, >2: {udzial:.3f} %")


renderer = GpuRenderer()
if not renderer.available or not renderer.kolor_dostepny:
    check("odszumianie koloru na karcie", True,
          f"brak GPU - pominiete ({renderer.error or renderer._kolor_blad})")
else:
    path = next(p for p in zdjecia() if not is_jpeg(p))
    raw = load_photo(path)
    p = replace(default_params_for(path), noise_color=40.0)
    renderer.set_source(raw.camera_linear)
    W, H = geometry_size(raw, p)
    for szer, opis in ((2560, "parzysty"), (1279, "nieparzysty")):
        s = szer / float(W)
        wys = max(1, round(H * s))
        bez = renderer.render(raw, p, szer, wys, region=(0, 0, W, H), scale=s)
        start = time.perf_counter()
        z = renderer.render(raw, p, szer, wys, region=(0, 0, W, H), scale=s, kolor=p.noise_color)
        ms = (time.perf_counter() - start) * 1000.0
        cpu = apply_noise_reduction(bez, 0.0, p.noise_color)
        porownaj(f"podglad {opis} {szer} px = procesor ({ms:.0f} ms)", z, cpu, 0.5, 1.0)
        roznica = float(np.abs(bez.astype(np.int16) - cpu).mean())
        check(f"podglad {opis}: odszumianie cos zmienia", roznica > 1.0,
              f"bez odszumiania srednio {roznica:.2f}")
    rect = (W // 3, H // 3, 900, 650)
    q = replace(p, noise_luminance=0.0, sharpen_amount=0.0)
    for skala in (1.0, 2.0):
        z = renderer.render(raw, p, round(rect[2] * skala), round(rect[3] * skala),
                            region=rect, scale=skala, kolor=p.noise_color)
        porownaj(f"wycinek x{skala:g} = develop_region", z, develop_region(raw, q, rect, skala), 0.6, 1.0)
    zero = renderer.render(raw, p, 640, round(H * 640 / W), region=(0, 0, W, H), scale=640 / W, kolor=0.0)
    gola = renderer.render(raw, p, 640, round(H * 640 / W), region=(0, 0, W, H), scale=640 / W)
    check("kolor=0 nie rusza obrazu", np.array_equal(zero, gola))

sys.exit(wypisz(results))
