"""Odczyt metadanych EXIF z plikow RAW."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

import exifread


# Panasonic zapisuje ISO poza standardowym EXIF-em, we wlasnych polach RW2.
# Bez tego zdjecia z G91 pokazywalyby "ISO -" mimo poprawnej reszty metadanych.
VENDOR_ISO_TAGS = ("Image Tag 0x0017", "Image Tag 0x0037")


@dataclass
class PhotoMetadata:
    camera: str = ""
    lens: str = ""
    iso: int | None = None
    focal_length: float | None = None  # mm
    exposure_time: float | None = None  # sekundy
    aperture: float | None = None  # liczba przyslony
    exposure_bias: float | None = None  # korekta ekspozycji w EV
    shot_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def shutter_text(self) -> str:
        if self.exposure_time is None:
            return "-"
        if self.exposure_time >= 1.0:
            return f"{self.exposure_time:g} s"
        return f"1/{round(1.0 / self.exposure_time)} s"

    @property
    def aperture_text(self) -> str:
        return "-" if self.aperture is None else f"f/{self.aperture:g}"

    @property
    def focal_text(self) -> str:
        return "-" if self.focal_length is None else f"{self.focal_length:g} mm"

    @property
    def iso_text(self) -> str:
        return "-" if self.iso is None else f"ISO {self.iso}"

    @property
    def bias_text(self) -> str:
        return "-" if self.exposure_bias is None else f"{self.exposure_bias:+.2f} EV"

    @property
    def has_gps(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def summary(self) -> str:
        """Jednolinijkowy opis do paska informacji: ogniskowa, czas, przyslona, ISO."""
        return "  ".join(
            (self.focal_text, self.shutter_text, self.aperture_text, self.iso_text)
        )


def _ratio(tag) -> float | None:
    try:
        v = tag.values[0]
    except (AttributeError, IndexError, TypeError):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, Fraction):
        return float(v) if v.denominator else None
    num, den = getattr(v, "num", None), getattr(v, "den", None)
    if num is None or not den:
        return None
    return float(num) / float(den)


def _dms_to_degrees(tag, ref: str | None) -> float | None:
    try:
        parts = tag.values
        deg = float(Fraction(parts[0].num, parts[0].den))
        minute = float(Fraction(parts[1].num, parts[1].den))
        sec = float(Fraction(parts[2].num, parts[2].den))
    except (AttributeError, IndexError, TypeError, ZeroDivisionError):
        return None
    value = deg + minute / 60.0 + sec / 3600.0
    if ref and ref.upper() in ("S", "W"):
        value = -value
    return value


def read_metadata(path: str) -> PhotoMetadata:
    """Wyciaga najwazniejsze parametry zdjecia: ISO, ogniskowa, czas, przyslona, data, GPS."""
    meta = PhotoMetadata()
    try:
        with open(path, "rb") as fh:
            tags = exifread.process_file(fh, details=False)
    except OSError:
        return meta

    def text(key: str) -> str:
        tag = tags.get(key)
        return str(tag).strip() if tag is not None else ""

    make, model = text("Image Make"), text("Image Model")
    meta.camera = f"{make} {model}".strip() if make not in model else model
    meta.lens = text("EXIF LensModel") or text("MakerNote LensType")

    iso_keys = ("EXIF ISOSpeedRatings", "EXIF PhotographicSensitivity", *VENDOR_ISO_TAGS)
    for key in iso_keys:
        tag = tags.get(key)
        if tag is None:
            continue
        try:
            value = tag.values[0] if isinstance(tag.values, (list, tuple)) else tag.values
            value = int(value)
        except (IndexError, TypeError, ValueError):
            continue
        if 25 <= value <= 1_000_000:  # odsiewamy pola o tym samym numerze, ale innym znaczeniu
            meta.iso = value
            break

    if "EXIF ExposureBiasValue" in tags:
        meta.exposure_bias = _ratio(tags["EXIF ExposureBiasValue"])

    for key in ("EXIF FocalLength", "Image FocalLength"):
        if key in tags:
            meta.focal_length = _ratio(tags[key])
            break
    for key in ("EXIF ExposureTime", "Image ExposureTime"):
        if key in tags:
            meta.exposure_time = _ratio(tags[key])
            break
    for key in ("EXIF FNumber", "Image FNumber"):
        if key in tags:
            meta.aperture = _ratio(tags[key])
            break

    for key in ("EXIF DateTimeOriginal", "Image DateTime"):
        raw_date = text(key)
        if raw_date:
            try:
                meta.shot_at = datetime.strptime(raw_date, "%Y:%m:%d %H:%M:%S")
                break
            except ValueError:
                continue

    if "GPS GPSLatitude" in tags:
        meta.latitude = _dms_to_degrees(tags["GPS GPSLatitude"], text("GPS GPSLatitudeRef"))
    if "GPS GPSLongitude" in tags:
        meta.longitude = _dms_to_degrees(tags["GPS GPSLongitude"], text("GPS GPSLongitudeRef"))

    return meta
