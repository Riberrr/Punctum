"""Macierze przeksztalcen geometrycznych.

Jedno miejsce, w ktorym powstaje odwzorowanie "piksel obrazu wynikowego ->
piksel danych zrodlowych". Korzystaja z niego oba tory - numpy i GPU - dzieki
czemu nie da sie ich niechcacy rozjechac.
"""

from __future__ import annotations

import numpy as np

from .params import EditParams


def orientation_steps(orientation: int) -> int:
    return int(round(orientation / 90.0)) % 4


def oriented_size(width: int, height: int, orientation: int) -> tuple[int, int]:
    return (height, width) if orientation_steps(orientation) % 2 else (width, height)


def _orientation_matrix(steps: int, src_w: int, src_h: int) -> np.ndarray:
    """Z ukladu obrazu obroconego o 90 stopni z powrotem do ukladu zrodla.

    Odpowiada dokladnie `np.rot90(a, k=-steps)`: dla steps=1 piksel (x, y)
    obrazu obroconego lezy w zrodle pod (y, src_h - 1 - x).
    """
    if steps == 0:
        return np.eye(3)
    if steps == 1:
        return np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, src_h - 1.0], [0.0, 0.0, 1.0]])
    if steps == 2:
        return np.array([[-1.0, 0.0, src_w - 1.0], [0.0, -1.0, src_h - 1.0], [0.0, 0.0, 1.0]])
    return np.array([[0.0, -1.0, src_w - 1.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


def _rotation_matrix(angle: float, width: int, height: int) -> np.ndarray:
    """Obrot wokol srodka obrazu, w konwencji cv2.getRotationMatrix2D."""
    if abs(angle) < 1e-9:
        return np.eye(3)
    radians = np.deg2rad(angle)
    cos, sin = np.cos(radians), np.sin(radians)
    cx, cy = width / 2.0, height / 2.0
    return np.array(
        [
            [cos, sin, (1.0 - cos) * cx - sin * cy],
            [-sin, cos, sin * cx + (1.0 - cos) * cy],
            [0.0, 0.0, 1.0],
        ]
    )


def output_to_source(
    p: EditParams,
    src_w: int,
    src_h: int,
    region: tuple[int, int, int, int] | None = None,
    scale: float = 1.0,
) -> np.ndarray:
    """Macierz 3x3: piksel obrazu wynikowego -> piksel danych zrodlowych.

    `region` wskazuje fragment obrazu wynikowego (po kadrowaniu), a `scale`
    stopien jego powiekszenia. Zlozenie wszystkiego w jedna macierz pozwala
    policzyc wylacznie widoczny wycinek, niezaleznie od rozmiaru zdjecia.
    """
    steps = orientation_steps(p.orientation)
    ori_w, ori_h = oriented_size(src_w, src_h, p.orientation)

    left, top, _, _ = p.crop
    offset_x = left * ori_w + (region[0] if region else 0.0)
    offset_y = top * ori_h + (region[1] if region else 0.0)

    # 1. z pikseli ekranu na piksele obrazu wynikowego
    unscale = np.array(
        [[1.0 / scale, 0.0, 0.0], [0.0, 1.0 / scale, 0.0], [0.0, 0.0, 1.0]]
    )
    # 2. przesuniecie o poczatek kadru i wycinka
    translate = np.array([[1.0, 0.0, offset_x], [0.0, 1.0, offset_y], [0.0, 0.0, 1.0]])
    # 3. cofniecie plynnego obrotu
    inverse_rotation = np.linalg.inv(_rotation_matrix(p.rotation, ori_w, ori_h))
    # 4. cofniecie obrotu o wielokrotnosc 90 stopni
    inverse_orientation = _orientation_matrix(steps, src_w, src_h)

    return inverse_orientation @ inverse_rotation @ translate @ unscale


def output_size(p: EditParams, src_w: int, src_h: int) -> tuple[int, int]:
    """Rozmiar obrazu po geometrii, jako (szerokosc, wysokosc)."""
    ori_w, ori_h = oriented_size(src_w, src_h, p.orientation)
    left, top, right, bottom = p.crop
    return (
        max(1, int(round((right - left) * ori_w))),
        max(1, int(round((bottom - top) * ori_h))),
    )
