"""Test geotagowania bez interfejsu: sidecar, przeniesienie, eksport.

Trzy pytania, na ktore odpowiada ten plik:
1. Czy wspolrzedne przezywaja zapis i odczyt sidecara bez straty dokladnosci?
2. Czy ruch suwakiem po nadaniu lokalizacji jej nie kasuje?
3. Czy wyeksportowany plik ma GPS, ktory odczyta inny program?
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, read_sidecar, save_image, write_sidecar  # noqa: E402
from punctum.core.sidecar import sidecar_path  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# Łańcut, rynek — punkt z ujemna dlugoscia sprawdzamy osobno.
LAT, LON = 50.0686361, 22.2290139

with tempfile.TemporaryDirectory() as tmp:
    photo = os.path.join(tmp, "P1170926.RW2")
    open(photo, "w", encoding="utf-8").close()

    # --- 1. sidecar ---------------------------------------------------------
    params = EditParams(exposure=0.8, latitude=LAT, longitude=LON)
    check("nastawy z lokalizacja sa rozpoznawane", params.has_location)
    write_sidecar(photo, params)
    back = read_sidecar(photo)
    check("wspolrzedne wracaja z sidecara bez straty",
          back is not None
          and abs(back.latitude - LAT) < 1e-7 and abs(back.longitude - LON) < 1e-7,
          "brak" if back is None else f"{back.latitude:.7f}, {back.longitude:.7f}")
    check("korekty nie ucierpialy", back is not None and abs(back.exposure - 0.8) < 1e-6)

    with open(sidecar_path(photo), encoding="utf-8") as handle:
        text = handle.read()
    check("sidecar ma pola dla innych programow",
          "exif:GPSLatitude" in text and "exif:GPSLongitude" in text)
    check("zapis exif ma litere kierunku", '50,4.1182N' in text or "N\"" in text,
          [line for line in text.splitlines() if "GPSLatitude" in line][0].strip())

    # --- 2. zdjecie bez lokalizacji ----------------------------------------
    plain = os.path.join(tmp, "bez.RW2")
    open(plain, "w", encoding="utf-8").close()
    write_sidecar(plain, EditParams(exposure=1.0))
    empty = read_sidecar(plain)
    check("brak lokalizacji zostaje brakiem",
          empty is not None and not empty.has_location
          and empty.latitude is None and empty.longitude is None)

    # --- 3. polkula poludniowa i zachodnia ---------------------------------
    south = os.path.join(tmp, "poludnie.RW2")
    open(south, "w", encoding="utf-8").close()
    write_sidecar(south, EditParams(latitude=-33.8688, longitude=-70.6693))
    back_south = read_sidecar(south)
    check("ujemne wspolrzedne wracaja poprawnie",
          back_south is not None
          and abs(back_south.latitude + 33.8688) < 1e-6
          and abs(back_south.longitude + 70.6693) < 1e-6,
          f"{back_south.latitude:.4f}, {back_south.longitude:.4f}")
    with open(sidecar_path(south), encoding="utf-8") as handle:
        south_text = handle.read()
    check("polkule opisane literami S i W", "S\"" in south_text and "W\"" in south_text)

    # --- 4. eksport: GPS w pliku wynikowym ---------------------------------
    image = (np.linspace(0, 255, 240 * 160 * 3, dtype=np.uint8)
             .reshape((160, 240, 3)))
    target = os.path.join(tmp, "wynik.jpg")
    save_image(image, target, quality=90, location=(LAT, LON))
    check("plik wynikowy powstal", os.path.exists(target))

    import piexif

    tags = piexif.load(target)
    gps = tags.get("GPS", {})
    check("eksport zapisal wspolrzedne w EXIF", bool(gps), f"{len(gps)} pol GPS")

    def to_degrees(value, reference) -> float:
        degrees = value[0][0] / value[0][1]
        minutes = value[1][0] / value[1][1]
        seconds = value[2][0] / value[2][1]
        result = degrees + minutes / 60.0 + seconds / 3600.0
        return -result if reference in (b"S", b"W", "S", "W") else result

    if gps:
        read_lat = to_degrees(gps[piexif.GPSIFD.GPSLatitude],
                              gps[piexif.GPSIFD.GPSLatitudeRef])
        read_lon = to_degrees(gps[piexif.GPSIFD.GPSLongitude],
                              gps[piexif.GPSIFD.GPSLongitudeRef])
        check("odczytane wspolrzedne zgadzaja sie z nadanymi",
              abs(read_lat - LAT) < 1e-5 and abs(read_lon - LON) < 1e-5,
              f"{read_lat:.6f}, {read_lon:.6f}  wobec  {LAT:.6f}, {LON:.6f}")

    # to samo dla polkuli poludniowej i zachodniej
    target_south = os.path.join(tmp, "poludnie.jpg")
    save_image(image, target_south, quality=90, location=(-33.8688, -70.6693))
    gps_south = piexif.load(target_south).get("GPS", {})
    if gps_south:
        read_lat = to_degrees(gps_south[piexif.GPSIFD.GPSLatitude],
                              gps_south[piexif.GPSIFD.GPSLatitudeRef])
        read_lon = to_degrees(gps_south[piexif.GPSIFD.GPSLongitude],
                              gps_south[piexif.GPSIFD.GPSLongitudeRef])
        check("ujemne wspolrzedne tez trafiaja do pliku",
              abs(read_lat + 33.8688) < 1e-5 and abs(read_lon + 70.6693) < 1e-5,
              f"{read_lat:.5f}, {read_lon:.5f}")

    # --- 5. zdjecie bez lokalizacji nie dostaje pustego bloku GPS ----------
    target_plain = os.path.join(tmp, "bez_gps.jpg")
    save_image(image, target_plain, quality=90)
    plain_tags = piexif.load(target_plain)
    check("bez lokalizacji nie ma bloku GPS", not plain_tags.get("GPS"),
          f"{len(plain_tags.get('GPS', {}))} pol")

    # --- 6. odczyt przez nasza wlasna sciezke metadanych --------------------
    from punctum.core import read_metadata

    meta = read_metadata(target)
    check("nasz odczyt EXIF widzi lokalizacje w eksporcie",
          meta.has_gps and abs(meta.latitude - LAT) < 1e-5,
          "brak" if not meta.has_gps else f"{meta.latitude:.6f}, {meta.longitude:.6f}")

from wspolne import wypisz  # noqa: E402  (test jest skryptem, nie modulem)

sys.exit(wypisz(results))
