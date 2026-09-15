"""Porownanie algorytmow odszumiania luminancji.

Dobry algorytm ma usunac szum z gladkiego nieba i jednoczesnie zostawic
krawedzie okien i latarni. Mierzymy wiec dwie rzeczy naraz - sam spadek szumu
nic nie znaczy, bo rozmycie gaussowskie wygrywa kazdy taki ranking i niszczy
zdjecie.

Metryka krawedzi wymaga ostroznosci. Wariancja laplasjanu na zdjeciu ISO 3200
mierzy przede wszystkim SZUM, nie szczegoly - dlatego maske realnych krawedzi
wyznaczamy na obrazie mocno rozmytym (szum znika, krawedzie zostaja) i dopiero
w niej porownujemy gradienty.

Fragmenty testowe wybieramy automatycznie: okno o najmniejszej i najwiekszej
strukturze. Reczne wspolrzedne latwo trafiaja w puste niebo.
"""

from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, develop, develop_region, load_raw

path = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "out/denoise"
os.makedirs(out_dir, exist_ok=True)

raw = load_raw(path)
params = EditParams(exposure=1.0, shadows=30)
WINDOW = (900, 600)


def luma(rgb):
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)[..., 0]


def pick_regions() -> tuple[tuple, tuple]:
    """Znajduje okno najgladsze i najbardziej urozmaicone."""
    small = develop(raw.proxy(900), params, denoise=False)
    grey = cv2.GaussianBlur(luma(small).astype(np.float32), (0, 0), 2.5)
    gx = cv2.Sobel(grey, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(grey, cv2.CV_32F, 0, 1, ksize=3)
    energy = cv2.boxFilter(np.hypot(gx, gy), -1, (61, 61))

    scale = raw.shape[1] / small.shape[1]
    win_w = int(WINDOW[0] / scale / 2) * 2
    win_h = int(WINDOW[1] / scale / 2) * 2
    inner = energy[win_h // 2 : -win_h // 2, win_w // 2 : -win_w // 2]

    flat_y, flat_x = np.unravel_index(np.argmin(inner), inner.shape)
    busy_y, busy_x = np.unravel_index(np.argmax(inner), inner.shape)

    def to_full(cx, cy):
        return (
            int(cx * scale), int(cy * scale), WINDOW[0], WINDOW[1],
        )

    return to_full(flat_x, flat_y), to_full(busy_x, busy_y)


FLAT, BUSY = pick_regions()
print(f"fragment gladki      : {FLAT}")
print(f"fragment ze szczegol.: {BUSY}\n")

flat = develop_region(raw, params, FLAT, scale=1.0, denoise=False)
busy = develop_region(raw, params, BUSY, scale=1.0, denoise=False)
cv2.imwrite(f"{out_dir}/00_gladki.png", cv2.cvtColor(flat, cv2.COLOR_RGB2BGR))
cv2.imwrite(f"{out_dir}/00_szczegoly.png", cv2.cvtColor(busy, cv2.COLOR_RGB2BGR))


def noise_level(y: np.ndarray) -> float:
    """Odchylenie standardowe po odjeciu wolnozmiennego tla."""
    f = y.astype(np.float32)
    return float((f - cv2.GaussianBlur(f, (0, 0), 9.0)).std())


def _gradient(y: np.ndarray, sigma: float) -> np.ndarray:
    f = cv2.GaussianBlur(y.astype(np.float32), (0, 0), sigma)
    return np.hypot(
        cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    )


EDGE_MASK = _gradient(luma(busy), 2.5)
EDGE_MASK = EDGE_MASK > np.percentile(EDGE_MASK, 98.0)
BASE_EDGE = float(_gradient(luma(busy), 1.0)[EDGE_MASK].mean())


def edge_retention(y: np.ndarray) -> float:
    """Ile procent sily realnych krawedzi przetrwalo odszumianie."""
    return 100.0 * float(_gradient(y, 1.0)[EDGE_MASK].mean()) / BASE_EDGE


# --------------------------------------------------------------- kandydaci

METHODS = {
    "bilateralny wąski (obecny)": lambda y, s: cv2.bilateralFilter(
        y, 5, 6.0 + s * 45.0, 2.0 + s * 6.0
    ),
    "bilateralny szeroki": lambda y, s: cv2.bilateralFilter(
        y, 9, 10.0 + s * 70.0, 4.0 + s * 12.0
    ),
    "NLM szybki (5/11)": lambda y, s: cv2.fastNlMeansDenoising(y, None, 2.0 + s * 16.0, 5, 11),
    "NLM średni (7/15)": lambda y, s: cv2.fastNlMeansDenoising(y, None, 2.0 + s * 16.0, 7, 15),
    "NLM pełny (7/21)": lambda y, s: cv2.fastNlMeansDenoising(y, None, 2.0 + s * 16.0, 7, 21),
}

y_flat, y_busy = luma(flat), luma(busy)
print(f"{'metoda':<28}{'szum':>7}{'krawędzie %':>13}{'czas ms':>9}")
print(f"{'bez odszumiania':<28}{noise_level(y_flat):>7.2f}{100.0:>13.1f}{0:>9}")
print("-" * 57)

for name, method in METHODS.items():
    start = time.perf_counter()
    out_flat = method(y_flat, 1.0)
    elapsed = (time.perf_counter() - start) * 1000
    out_busy = method(y_busy, 1.0)
    print(f"{name:<28}{noise_level(out_flat):>7.2f}{edge_retention(out_busy):>13.1f}{elapsed:>9.0f}")

    ycrcb = cv2.cvtColor(busy, cv2.COLOR_RGB2YCrCb)
    ycrcb[..., 0] = out_busy
    slug = name.split()[0].lower().replace("ł", "l")
    cv2.imwrite(
        f"{out_dir}/{slug}_szczegoly.png",
        cv2.cvtColor(cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB), cv2.COLOR_RGB2BGR),
    )

print("\n--- NLM pełny: dobór siły suwaka ---")
print(f"{'suwak':>7}{'h':>7}{'szum':>8}{'krawędzie %':>13}")
for slider in (0, 20, 40, 60, 80, 100):
    h = 2.0 + (slider / 100.0) * 16.0
    if slider == 0:
        print(f"{slider:>7}{h:>7.1f}{noise_level(y_flat):>8.2f}{100.0:>13.1f}")
        continue
    a = cv2.fastNlMeansDenoising(y_flat, None, h, 7, 21)
    b = cv2.fastNlMeansDenoising(y_busy, None, h, 7, 21)
    print(f"{slider:>7}{h:>7.1f}{noise_level(a):>8.2f}{edge_retention(b):>13.1f}")

print(f"\nobrazy w {out_dir}")
