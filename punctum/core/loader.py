"""Jedno wejscie dla wszystkich obslugiwanych formatow.

Reszta programu nie powinna wiedziec, czy otwiera RW2 czy JPEG-a - i nie wie.
Wszystko, co dalej, dostaje `RawImage`: liniowy float32 z macierzami barw,
a skad sie wzial, mowi tylko pole `source_format`. Dzieki temu tor tonalny,
shader, kadrowanie, odszumianie i eksport nie maja ani jednej galezi "jesli
to JPEG" - poza jedna rzecza, ktorej nie da sie zatrzec: opisem balansu
bieli, ktory przy JPEG-u jest wzgledny (patrz jpeg_loader).
"""

from __future__ import annotations

import os

import numpy as np

from .jpeg_loader import JPEG_EXTENSIONS, jpeg_thumbnail, load_jpeg
from .raw_loader import RawImage, load_raw, load_thumbnail

RAW_EXTENSIONS = (
    ".rw2", ".raw", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".dng", ".raf", ".pef",
)
PHOTO_EXTENSIONS = RAW_EXTENSIONS + JPEG_EXTENSIONS

FORMAT_ALL = "all"
FORMAT_RAW = "raw"
FORMAT_JPEG = "jpeg"
FORMAT_LABELS = {
    FORMAT_ALL: "Wszystkie",
    FORMAT_RAW: "Tylko RAW",
    FORMAT_JPEG: "Tylko JPEG",
}


def is_raw(path: str) -> bool:
    return path.lower().endswith(RAW_EXTENSIONS)


def is_jpeg(path: str) -> bool:
    return path.lower().endswith(JPEG_EXTENSIONS)


def is_photo(path: str) -> bool:
    return path.lower().endswith(PHOTO_EXTENSIONS)


def matches_filter(path: str, format_filter: str) -> bool:
    if format_filter == FORMAT_RAW:
        return is_raw(path)
    if format_filter == FORMAT_JPEG:
        return is_jpeg(path)
    return is_photo(path)


def load_photo(path: str) -> RawImage:
    """Wczytuje zdjecie dowolnego obslugiwanego formatu."""
    return load_jpeg(path) if is_jpeg(path) else load_raw(path)


def load_preview(path: str) -> np.ndarray | None:
    """Miniatura do paska: z RAW-a podglad wbudowany, z JPEG-a pomniejszony plik."""
    return jpeg_thumbnail(path) if is_jpeg(path) else load_thumbnail(path)


def count_formats(paths: list[str]) -> tuple[int, int]:
    """Ile w katalogu RAW-ow, a ile JPEG-ow - do opisu w pasku stanu."""
    raw_count = sum(1 for p in paths if is_raw(p))
    return raw_count, sum(1 for p in paths if is_jpeg(p))


def folder_photos(folder: str) -> list[str]:
    """Wszystkie zdjecia w katalogu, posortowane po nazwie."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        raise
    return [os.path.join(folder, name) for name in names if is_photo(name)]
