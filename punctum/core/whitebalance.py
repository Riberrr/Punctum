"""Balans bieli: przeliczanie kelwinow i odcienia na mnozniki kanalow RAW.

Uwaga o macierzach: rawpy udostepnia `rgb_xyz_matrix`, ktora mimo nazwy
jest macierza XYZ -> RGB aparatu (w LibRaw nazywa sie `cam_xyz`).
Sprawdzenie poprawnosci: mnozniki policzone dla iluminantu D65 musza
wyjsc identyczne jak `raw.daylight_whitebalance` z pliku.
"""

from __future__ import annotations

import numpy as np

# sRGB -> XYZ (D65), ta sama macierz, ktorej uzywa dcraw
XYZ_RGB = np.array(
    [
        [0.412453, 0.357580, 0.180423],
        [0.212671, 0.715160, 0.072169],
        [0.019334, 0.119193, 0.950227],
    ],
    dtype=np.float64,
)

TEMP_MIN, TEMP_MAX = 1667.0, 25000.0


def kelvin_to_xy(temp_k: float) -> tuple[float, float]:
    """Punkt na krzywej Plancka we wspolrzednych CIE xy (aproksymacja Kima)."""
    t = float(np.clip(temp_k, TEMP_MIN, TEMP_MAX))
    if t <= 4000.0:
        x = -0.2661239e9 / t**3 - 0.2343589e6 / t**2 + 0.8776956e3 / t + 0.179910
    else:
        x = -3.0258469e9 / t**3 + 2.1070379e6 / t**2 + 0.2226347e3 / t + 0.240390

    if t <= 2222.0:
        y = -1.1063814 * x**3 - 1.34811020 * x**2 + 2.18555832 * x - 0.20219683
    elif t <= 4000.0:
        y = -0.9549476 * x**3 - 1.37418593 * x**2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x**3 - 5.87338670 * x**2 + 3.75112997 * x - 0.37001483
    return float(x), float(y)


def _xy_to_uv(x: float, y: float) -> tuple[float, float]:
    d = -2.0 * x + 12.0 * y + 3.0
    return 4.0 * x / d, 6.0 * y / d


def _uv_to_xy(u: float, v: float) -> tuple[float, float]:
    d = 2.0 * u - 8.0 * v + 4.0
    return 3.0 * u / d, 2.0 * v / d


def temp_tint_to_xy(temp_k: float, tint: float) -> tuple[float, float]:
    """Kelwiny + odcien -> CIE xy.

    Odcien przesuwa punkt bieli prostopadle do krzywej Plancka
    (dodatni = w strone magenty, ujemny = w strone zieleni) - taka jest
    konwencja w programach do obrobki RAW.
    """
    x, y = kelvin_to_xy(temp_k)
    if abs(tint) < 1e-9:
        return x, y

    u, v = _xy_to_uv(x, y)
    # kierunek stycznej do krzywej wyznaczamy numerycznie
    x2, y2 = kelvin_to_xy(temp_k * 1.001 + 1.0)
    u2, v2 = _xy_to_uv(x2, y2)
    du, dv = u2 - u, v2 - v
    norm = float(np.hypot(du, dv)) or 1.0
    # normalna do stycznej
    nu, nv = -dv / norm, du / norm
    duv = -tint / 3000.0
    return _uv_to_xy(u + nu * duv, v + nv * duv)


def xy_to_xyz(x: float, y: float) -> np.ndarray:
    y = max(y, 1e-9)
    return np.array([x / y, 1.0, (1.0 - x - y) / y], dtype=np.float64)


def camera_multipliers(cam_xyz: np.ndarray, temp_k: float, tint: float) -> np.ndarray:
    """Mnozniki kanalow RAW dla zadanej temperatury barwowej.

    Zwraca trojke znormalizowana tak, ze kanal zielony = 1.0.
    """
    xyz = xy_to_xyz(*temp_tint_to_xy(temp_k, tint))
    response = cam_xyz[:3, :3] @ xyz
    response = np.where(np.abs(response) < 1e-9, 1e-9, response)
    mult = 1.0 / response
    return (mult / mult[1]).astype(np.float64)


def estimate_temp_tint(cam_xyz: np.ndarray, cam_wb: np.ndarray) -> tuple[float, float]:
    """Odtwarza temperature i odcien z mnoznikow zapisanych przez aparat.

    Aparat zapisuje tylko mnozniki, nie kelwiny - zeby pokazac uzytkownikowi
    "6100 K", trzeba przeszukac krzywa Plancka i znalezc
    temperature, ktora daje najbardziej zblizone mnozniki.
    """
    target = np.asarray(cam_wb, dtype=np.float64)[:3]
    if target[1] <= 0:
        return 5500.0, 0.0
    target = target / target[1]

    def err(temp: float, tint: float) -> float:
        m = camera_multipliers(cam_xyz, temp, tint)
        # Przy skrajnych temperaturach odpowiedz kanalu potrafi wyjsc ujemna -
        # zdarza sie to przy waskich prymarnych, np. gdy "aparatem" jest sRGB
        # (pliki JPEG). Taki punkt odrzucamy, zamiast liczyc logarytm z minusa.
        if np.any(m <= 0.0):
            return float("inf")
        return float(np.sum((np.log(m) - np.log(target)) ** 2))

    # zgrubnie: logarytmiczny skan calego zakresu
    best_t = 5500.0
    best_e = float("inf")
    for temp in np.geomspace(TEMP_MIN, TEMP_MAX, 220):
        e = err(float(temp), 0.0)
        if e < best_e:
            best_e, best_t = e, float(temp)

    # dokladnie: naprzemienne dopracowanie temperatury i odcienia
    best_tint = 0.0
    span = best_t * 0.25
    for _ in range(40):
        improved = False
        for cand_t in (best_t - span, best_t + span):
            cand_t = float(np.clip(cand_t, TEMP_MIN, TEMP_MAX))
            e = err(cand_t, best_tint)
            if e < best_e:
                best_e, best_t, improved = e, cand_t, True
        for cand_tint in (best_tint - span / 60.0, best_tint + span / 60.0):
            cand_tint = float(np.clip(cand_tint, -150.0, 150.0))
            e = err(best_t, cand_tint)
            if e < best_e:
                best_e, best_tint, improved = e, cand_tint, True
        if not improved:
            span *= 0.5
            if span < 0.5:
                break
    return round(best_t), round(best_tint, 1)


def camera_to_srgb_matrix(cam_xyz: np.ndarray) -> np.ndarray:
    """Macierz RGB aparatu -> liniowy sRGB, znormalizowana wzgledem bieli.

    Odwzorowuje procedure `cam_xyz_coeff` z dcraw: najpierw skladamy
    sRGB -> aparat, normalizujemy wiersze do sumy 1 (dzieki temu biel
    przechodzi w biel), a na koncu odwracamy.
    """
    srgb_to_cam = cam_xyz[:3, :3] @ XYZ_RGB
    row_sums = srgb_to_cam.sum(axis=1, keepdims=True)
    row_sums = np.where(np.abs(row_sums) < 1e-9, 1e-9, row_sums)
    srgb_to_cam = srgb_to_cam / row_sums
    return np.linalg.inv(srgb_to_cam)


def daylight_multipliers(cam_xyz: np.ndarray) -> np.ndarray:
    """Mnozniki dla D65 - sluza do weryfikacji macierzy wzgledem pliku."""
    srgb_to_cam = cam_xyz[:3, :3] @ XYZ_RGB
    return 1.0 / srgb_to_cam.sum(axis=1)
