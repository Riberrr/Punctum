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


# ------------------------------------------------------------ warianty


def variant(rgb8, t, h0, h1, w0, w1, sharp) -> np.ndarray:
    """Jasnosc jak w denoise._denoise_luma, ale z parametrami z zewnatrz:
    h = (h0 + h1*t) sigma, waga = w0 + w1*t, na koncu wyostrzenie calosci
    (promien 0,8 px) - jak domyslne wyostrzanie RAW w innych programach."""
    from punctum.core import denoise as dn

    ycc = cv2.cvtColor(rgb8, cv2.COLOR_RGB2YCrCb)
    dn._denoise_color(ycc, 0.25 * 16.0)
    y = ycc[..., 0]
    f = dn.vst_curve(y)
    scale = 250.0 / float(f[-1])
    zu = np.clip(f[y] * scale + 0.5, 0, 255).astype(np.uint8)
    zd = cv2.fastNlMeansDenoising(zu, None, (h0 + h1 * t) * scale, 5, 13).astype(np.float32) / scale
    yd = np.interp(zd, f, np.arange(256, dtype=np.float32)).astype(np.float32)
    yf = y.astype(np.float32)
    out = yf + min(1.0, w0 + w1 * t) * (yd - yf)
    if sharp > 0:
        out += sharp * (out - cv2.GaussianBlur(out, (0, 0), 0.8))
    ycc[..., 0] = np.clip(out + 0.5, 0, 255).astype(np.uint8)
    return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)


# ------------------------------------------------------------ przebieg

# Wycinki "nazwa:x,y" (lewy gorny rog, wspolrzedne wzorca) w zmiennej
# SZUM_KADRY, oddzielone srednikiem; wymiar wycinka staly. Nasz obraz jest
# o 8 px wiekszy z kazdej strony (LibRaw nie przycina brzegu matrycy).
CROP_SIZE = (640, 480)
OFFSET = 8
DEFAULT_CROPS = "srodek:2270,1700"


def crops() -> dict[str, tuple[int, int, int, int]]:
    out = {}
    for item in os.environ.get("SZUM_KADRY", DEFAULT_CROPS).split(";"):
        name, xy = item.split(":")
        x, y = (int(v) for v in xy.split(","))
        out[name] = (x, y, *CROP_SIZE)
    return out


def match_exposure(raw, target_median: float, base: EditParams) -> float:
    """Przesuniecie ekspozycji, przy ktorym mediana jasnosci trafia we wzorzec."""
    small = cv2.resize(raw.camera_linear, None, fx=0.2, fy=0.2, interpolation=cv2.INTER_AREA)
    lo, hi = -3.0, 5.0
    for _ in range(18):
        mid = (lo + hi) / 2
        p = EditParams(**{**base.__dict__, "exposure": base.exposure + mid})
        y = luma(pl._to_uint8(pl.apply_tone(small, raw, p)))
        lo, hi = (mid, hi) if np.median(y) < target_median else (lo, mid)
    return (lo + hi) / 2


def mosaic(named, rect, cols=4) -> np.ndarray:
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
    """SZUM_NASTAWY="0/25,30/25" - ktore ustawienia suwakow policzyc."""
    from punctum.core.auto import auto_tone

    path, out_dir, refs = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(out_dir, exist_ok=True)
    raw = load_raw(path)

    ref_imgs = [(os.path.splitext(os.path.basename(r))[0][-12:].strip(),
                 cv2.imread(r)[..., ::-1].copy()) for r in refs]
    # automat zbliza tonacje do wzorca (tez korygowanego automatycznie),
    # a przesuniecie ekspozycji wyrownuje mediane - szum zalezy od jasnosci
    base = EditParams(**auto_tone(raw))
    target = float(np.median(luma(ref_imgs[0][1]))) if ref_imgs else 60.0
    ev = match_exposure(raw, target, base)
    p = EditParams(**{**base.__dict__, "exposure": base.exposure + ev})
    print(f"ekspozycja: automat {base.exposure:+.2f} EV, dopasowanie {ev:+.2f} EV")
    rgb8 = pl._to_uint8(pl.apply_tone(raw.camera_linear, raw, p))

    named = []
    for item in os.environ.get("SZUM_NASTAWY", "0/0,0/25,30/25,50/25").split(","):
        lum, col = (float(v) for v in item.split("/"))
        t = time.perf_counter()
        named.append((f"P {item}", pl.apply_noise_reduction(rgb8, lum, col, "high")))
        print(f"punctum {item}: {time.perf_counter() - t:.2f} s")
    # warianty robocze: "h0,h1,w0,w1,ostrosc" dla suwaka 30 i 40
    for spec in filter(None, os.environ.get("SZUM_WARIANTY", "").split(";")):
        h0, h1, w0, w1, sharp = (float(v) for v in spec.split(","))
        for lum in (30, 40):
            named.append((f"W{spec} {lum}", variant(rgb8, lum / 100, h0, h1, w0, w1, sharp)))
    named += ref_imgs
    print_curves(named)
    for key, rect in crops().items():
        cv2.imwrite(os.path.join(out_dir, f"mozaika_{key}.png"), mosaic(named, rect)[..., ::-1])


if __name__ == "__main__":
    main()
