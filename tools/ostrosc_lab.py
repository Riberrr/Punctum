"""Kalibracja wyostrzania wzgledem wzorca z innego programu.

Uzycie: python tools/ostrosc_lab.py <RAW> <wzorzec JPG bez odszumiania jasnosci> <wyjscie>

Miara ostrosci: srednia |laplasjanu| po rozmyciu 1,5 px (widzi krawedzie,
a nie pojedyncze ziarno) podzielona przez odchylenie jasnosci - zeby rozny
kontrast obu obrazow nie udawal roznicy ostrosci. Liczona w kilku oknach
o najwiekszej strukturze, wybranych automatycznie.
"""

from __future__ import annotations

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from punctum.core import EditParams, load_raw  # noqa: E402
from punctum.core import pipeline as pl  # noqa: E402
from punctum.core import sharpen as sh  # noqa: E402
from punctum.core.auto import auto_tone  # noqa: E402
from szum_lab import luma, match_exposure  # noqa: E402

OFFSET = 8
WIN = 400


def windows(y: np.ndarray, n: int = 6) -> list[tuple[int, int]]:
    g = cv2.GaussianBlur(y.astype(np.float32), (0, 0), 2.0)
    e = cv2.boxFilter(np.abs(cv2.Laplacian(g, cv2.CV_32F)), -1, (WIN, WIN))
    out = []
    for _ in range(n):
        yy, xx = np.unravel_index(np.argmax(e), e.shape)
        x0 = int(np.clip(xx - WIN // 2, 0, y.shape[1] - WIN))
        y0 = int(np.clip(yy - WIN // 2, 0, y.shape[0] - WIN))
        out.append((x0, y0))
        e[max(0, yy - WIN):yy + WIN, max(0, xx - WIN):xx + WIN] = 0
    return out


def sharpness(y: np.ndarray) -> float:
    """Energia pasma drobnego (0,7-1,5 px) wzgledem pasma grubszego (1,5-4 px).

    Stosunek pasm nie zalezy od kontrastu obrazu, a wyostrzanie o promieniu
    ~1 px podnosi wlasnie pasmo drobne. Laplasjan po rozmyciu 1,5 px sie do
    tego nie nadawal - rozmycie zjadalo caly efekt wyostrzania.
    """
    f = y.astype(np.float32)
    b07, b15, b40 = (cv2.GaussianBlur(f, (0, 0), s) for s in (0.7, 1.5, 4.0))
    return float(np.mean(np.abs(b07 - b15))) / max(1e-3, float(np.mean(np.abs(b15 - b40))))


def main() -> None:
    path, ref_path, out_dir = sys.argv[1:4]
    os.makedirs(out_dir, exist_ok=True)
    raw = load_raw(path)
    ref = cv2.imread(ref_path)[..., ::-1].copy()
    base = EditParams(**auto_tone(raw))
    ev = match_exposure(raw, float(np.median(luma(ref))), base)
    p = EditParams(**{**base.__dict__, "exposure": base.exposure + ev})
    ours = pl._to_uint8(pl.apply_tone(raw.camera_linear, raw, p))
    ours = pl.apply_noise_reduction(ours, 0, 25, "high")
    y_ref = luma(ref)
    wins = windows(y_ref)

    def score(img) -> float:
        y = luma(img)
        return float(np.mean([sharpness(y[b + OFFSET:b + OFFSET + WIN, a + OFFSET:a + OFFSET + WIN])
                              for a, b in wins]))

    target = float(np.mean([sharpness(y_ref[b:b + WIN, a:a + WIN]) for a, b in wins]))
    print(f"wzorzec: {target:.4f}   bez wyostrzania: {score(ours):.4f}")
    for amount in (0, 20, 40, 60, 80):
        s = score(sh.sharpen(ours, amount))
        print(f"ilosc {amount:3d}: {s:.4f}  ({100 * s / target:.0f} % wzorca)")
    a, b = wins[0]
    tiles = [ours[b + OFFSET:b + OFFSET + WIN, a + OFFSET:a + OFFSET + WIN],
             sh.sharpen(ours, 40)[b + OFFSET:b + OFFSET + WIN, a + OFFSET:a + OFFSET + WIN],
             ref[b:b + WIN, a:a + WIN]]
    cv2.imwrite(os.path.join(out_dir, "ostrosc.png"), np.hstack(tiles)[..., ::-1])


if __name__ == "__main__":
    main()
