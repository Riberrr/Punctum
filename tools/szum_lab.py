"""Laboratorium odszumiania: pomiar szumu, czasu i porownanie z wzorcem.

Uzycie: python tools/szum_lab.py <plik RAW> <katalog wyjsciowy> [wzorce JPG...]

Wzorce to eksporty tego samego zdjecia z innego programu z roznymi
ustawieniami odszumiania. Dla kazdego obrazu liczymy krzywa szumu
sigma(jasnosc) na dwoch skalach: drobnej (pojedyncze piksele) i grubej
(obraz pomniejszony 2x - tam widac "plamisty" szum, ktorego filtr
pikselowy nie lapie). Do oka sklejamy mozaike wycinkow 1:1.
"""

from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, load_raw  # noqa: E402
from punctum.core import pipeline as pl  # noqa: E402

# Filtr Immerkaera: odpowiedz na plaskie tlo i liniowe gradienty jest zerowa,
# zostaje sam szum. Norma L2 jadra wynosi 6.
IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
BINS = np.array([0, 8, 16, 32, 48, 64, 96, 128, 176, 256])


def sigma_in(r: np.ndarray, m: np.ndarray) -> float:
    """Sigma szumu z odpowiedzi filtra w masce, odporna na krawedzie.

    Srednia z |N(0,s)| to s*sqrt(2/pi); odciecie 10 % najwiekszych
    odpowiedzi (krawedzie) zaniza ja o ok. 16 % - stala, poprawiamy wprost.
    """
    v = r[m]
    if v.size < 2000:
        return float("nan")
    v = v[v <= np.percentile(v, 90)]
    return float(v.mean()) * np.sqrt(np.pi / 2) / 6.0 / 0.84


def noise_curve(y: np.ndarray, bins=BINS) -> list[float]:
    yf = y.astype(np.float32)
    r = np.abs(cv2.filter2D(yf, -1, IMMERKAER))
    mean = cv2.blur(yf, (7, 7))
    return [sigma_in(r, (mean >= lo) & (mean < hi)) for lo, hi in zip(bins[:-1], bins[1:])]


def luma(rgb8: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb8, cv2.COLOR_RGB2YCrCb)[..., 0]


def print_curves(named: list[tuple[str, np.ndarray]]) -> None:
    for label, factor in (("drobna skala", 1.0), ("gruba skala (1/2)", 0.5)):
        print(f"-- sigma szumu, {label}")
        print("jasnosc  " + "".join(f"{n[:11]:>12}" for n, _ in named))
        curves = []
        for _, img in named:
            y = luma(img)
            if factor != 1.0:
                y = cv2.resize(y, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
            curves.append(noise_curve(y))
        for i, lo in enumerate(BINS[:-1]):
            print(f"{lo:3d}-{BINS[i+1]:3d}  " + "".join(f"{c[i]:12.2f}" for c in curves))


# ------------------------------------------------------------ przebieg

# Wycinki (x, y, szer, wys) we wspolrzednych wzorca; nasz obraz jest o 8 px
# wiekszy z kazdej strony (LibRaw nie przycina brzegu matrycy).
CROPS = {"chlopiec": (2560, 1860, 640, 480), "sufit": (1080, 640, 640, 480)}
OFFSET = 8


def match_exposure(raw, target_median: float) -> float:
    small = cv2.resize(raw.camera_linear, None, fx=0.2, fy=0.2, interpolation=cv2.INTER_AREA)
    lo, hi = -1.0, 5.0
    for _ in range(18):
        mid = (lo + hi) / 2
        y = luma(pl._to_uint8(pl.apply_tone(small, raw, EditParams(exposure=mid))))
        lo, hi = (mid, hi) if np.median(y) < target_median else (lo, mid)
    return (lo + hi) / 2


def mosaic(named, rect, cols=3) -> np.ndarray:
    x, y, w, h = rect
    tiles = []
    for name, img in named:
        dx = OFFSET if img.shape[1] > 5190 else 0
        t = img[y + dx : y + dx + h, x + dx : x + dx + w].copy()
        cv2.putText(t, name, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        tiles.append(t)
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i : i + cols]) for i in range(0, len(tiles), cols)]
    return np.vstack(rows)


def main() -> None:
    path, out_dir, refs = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(out_dir, exist_ok=True)
    raw = load_raw(path)

    ref_imgs = [(os.path.splitext(os.path.basename(r))[0][-12:].strip(), cv2.imread(r)[..., ::-1].copy())
                for r in refs]
    target = float(np.median(luma(ref_imgs[len(ref_imgs) // 2][1]))) if ref_imgs else 60.0
    ev = match_exposure(raw, target)
    print(f"ekspozycja dopasowana do wzorca: {ev:+.2f} EV")
    rgb8 = pl._to_uint8(pl.apply_tone(raw.camera_linear, raw, EditParams(exposure=ev)))

    named = [("punctum 0", rgb8)]
    for lum, col in ((0, 25), (30, 25), (50, 25), (70, 25), (50, 0)):
        t = time.perf_counter()
        named.append((f"punctum {lum}/{col}", pl.apply_noise_reduction(rgb8, lum, col, "high")))
        print(f"punctum {lum}/{col}: {time.perf_counter() - t:.2f} s")
    named += ref_imgs
    print_curves(named)
    for key, rect in CROPS.items():
        cv2.imwrite(os.path.join(out_dir, f"mozaika_{key}.png"), mosaic(named, rect)[..., ::-1])


if __name__ == "__main__":
    main()
