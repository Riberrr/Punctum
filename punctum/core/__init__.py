"""Rdzen obrobki: dekodowanie RAW, tor tonalny, metadane, eksport.

Nazwy pakietu laduja sie leniwie (PEP 562). Samo `from punctum.core.settings
import Settings` wciagalo wczesniej rawpy, OpenCV i caly tor obrobki - ponad
pol sekundy przed pokazaniem ekranu startowego, ktory potrzebuje tylko
ustawien (jezyk). Teraz ciezkie moduly laduja sie przy pierwszym uzyciu.
"""

from __future__ import annotations

import importlib

_SKAD = {
    "params": ["EditParams"],
    "raw_loader": ["RawImage", "load_raw", "load_thumbnail"],
    "jpeg_loader": ["load_jpeg"],
    "loader": [
        "default_params_for", "FORMAT_ALL", "FORMAT_JPEG", "FORMAT_LABELS",
        "FORMAT_RAW", "JPEG_EXTENSIONS", "PHOTO_EXTENSIONS", "RAW_EXTENSIONS",
        "count_formats", "folder_photos", "is_jpeg", "is_raw", "load_photo",
        "load_preview", "matches_filter",
    ],
    "metadata": ["PhotoMetadata", "read_metadata"],
    "sidecar": ["edited_photos", "has_edits", "read_sidecar", "sidecar_path", "write_sidecar"],
    "pipeline": ["develop", "develop_region", "geometry_size", "histogram"],
    "auto": ["auto_tone"],
    "export": [
        "ExportOptions", "ExportPlan", "plan_export", "resolve_conflicts",
        "save_image", "output_path_for",
    ],
}
_MODUL = {nazwa: modul for modul, nazwy in _SKAD.items() for nazwa in nazwy}

__all__ = list(_MODUL)


def __getattr__(nazwa: str):
    modul = _MODUL.get(nazwa)
    if modul is None:
        raise AttributeError(nazwa)
    wartosc = getattr(importlib.import_module(f".{modul}", __name__), nazwa)
    globals()[nazwa] = wartosc  # nastepne siegniecie juz bez __getattr__
    return wartosc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
