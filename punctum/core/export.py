"""Zapis gotowego obrazu do pliku."""

from __future__ import annotations

import os

import numpy as np
from PIL import Image

from .metadata import PhotoMetadata


def save_image(
    rgb8: np.ndarray,
    out_path: str,
    quality: int = 92,
    max_side: int | None = None,
    meta: PhotoMetadata | None = None,
) -> str:
    """Zapisuje obraz RGB uint8 jako JPEG, PNG lub TIFF (wg rozszerzenia)."""
    img = Image.fromarray(rgb8, mode="RGB")

    if max_side:
        w, h = img.size
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            img = img.resize(
                (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS
            )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    ext = os.path.splitext(out_path)[1].lower()

    if ext in (".jpg", ".jpeg"):
        img.save(out_path, "JPEG", quality=quality, subsampling=0, optimize=True)
    elif ext == ".png":
        img.save(out_path, "PNG", compress_level=6)
    elif ext in (".tif", ".tiff"):
        img.save(out_path, "TIFF")
    else:
        raise ValueError(f"Nieobslugiwane rozszerzenie: {ext}")

    return out_path


def output_path_for(raw_path: str, out_dir: str, ext: str = ".jpg") -> str:
    stem = os.path.splitext(os.path.basename(raw_path))[0]
    return os.path.join(out_dir, stem + ext)
