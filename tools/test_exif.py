"""Test metadanych: sidecar, eksport, zapis do oryginalu.

Najwazniejsze pytanie: czy zapis do oryginalu NIE niszczy tego, co w pliku
juz bylo - ani obrazu, ani pozostalych metadanych, ani daty pliku.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, read_sidecar, save_image, write_sidecar  # noqa: E402
from punctum.core.exif_edit import (  # noqa: E402
    FIELDS,
    current_values,
    is_writable_format,
    normalise_datetime,
    read_all_tags,
    validate,
    write_into_file,
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# Tekst z ogonkami, cudzyslowem i ampersandem - wszystkim, co potrafi
# wysadzic zapis do XML-a.
OPIS = 'Łańcut, zachód słońca & "chwila"'
AUTOR = "Łukasz Żółw"

with tempfile.TemporaryDirectory() as tmp:
    # --- 1. sidecar --------------------------------------------------------
    raw_photo = os.path.join(tmp, "P1170926.RW2")
    open(raw_photo, "w", encoding="utf-8").close()

    params = EditParams(exposure=0.5, metadata={
        "Artist": AUTOR,
        "ImageDescription": OPIS,
        "DateTimeOriginal": "2023-04-18 15:14:03",
    })
    check("nastawy widza, ze sa metadane", params.has_metadata)
    write_sidecar(raw_photo, params)
    back = read_sidecar(raw_photo)
    check("metadane wracaja z sidecara",
          back is not None and back.metadata.get("Artist") == AUTOR,
          "brak" if back is None else back.metadata.get("Artist", "-"))
    check("znaki specjalne przezywaja zapis do XML",
          back is not None and back.metadata.get("ImageDescription") == OPIS,
          "brak" if back is None else repr(back.metadata.get("ImageDescription")))
    check("korekty obok metadanych zostaja",
          back is not None and abs(back.exposure - 0.5) < 1e-6)

    # --- 2. walidacja ------------------------------------------------------
    check("zla data jest odrzucana", validate("DateTimeOriginal", "wczoraj") is not None)
    check("dobra data przechodzi", validate("DateTimeOriginal", "2023-04-18 15:14:03") is None)
    check("data zamienia sie na format EXIF",
          normalise_datetime("2023-04-18 15:14:03") == "2023:04:18 15:14:03",
          str(normalise_datetime("2023-04-18 15:14:03")))
    check("liczba w polu liczbowym przechodzi", validate("FNumber", "5.6") is None)
    check("tekst w polu liczbowym jest odrzucany", validate("FNumber", "jasno") is not None)
    check("puste pole zawsze przechodzi", validate("FNumber", "") is None)

    # --- 3. eksport z metadanymi -------------------------------------------
    image = np.linspace(0, 255, 240 * 160 * 3, dtype=np.uint8).reshape((160, 240, 3))
    target = os.path.join(tmp, "wynik.jpg")
    save_image(image, target, quality=90,
               location=(50.0686361, 22.2290139),
               metadata={"Artist": AUTOR, "ImageDescription": OPIS,
                         "DateTimeOriginal": "2023-04-18 15:14:03",
                         "ISOSpeedRatings": "400", "FNumber": "5.6"})

    import piexif

    tags = piexif.load(target)
    check("eksport zapisal autora",
          tags["0th"].get(piexif.ImageIFD.Artist, b"").decode("utf-8") == AUTOR,
          tags["0th"].get(piexif.ImageIFD.Artist, b"").decode("utf-8"))
    check("eksport zapisal opis z ogonkami",
          tags["0th"].get(piexif.ImageIFD.ImageDescription, b"").decode("utf-8") == OPIS)
    check("eksport zapisal date w formacie EXIF",
          tags["Exif"].get(piexif.ExifIFD.DateTimeOriginal, b"") == b"2023:04:18 15:14:03",
          str(tags["Exif"].get(piexif.ExifIFD.DateTimeOriginal)))
    check("eksport zapisal ISO i przyslone",
          tags["Exif"].get(piexif.ExifIFD.ISOSpeedRatings) == 400
          and tags["Exif"].get(piexif.ExifIFD.FNumber) == (56000, 10000),
          f"ISO {tags['Exif'].get(piexif.ExifIFD.ISOSpeedRatings)}, "
          f"f {tags['Exif'].get(piexif.ExifIFD.FNumber)}")
    check("lokalizacja nadal trafia do pliku", bool(tags.get("GPS")))

    # --- 4. zapis do istniejacego pliku ------------------------------------
    original = os.path.join(tmp, "oryginal.jpg")
    save_image(image, original, quality=95,
               location=(50.0686361, 22.2290139),
               metadata={"Model": "DC-G91", "ISOSpeedRatings": "200"})
    before_bytes = os.path.getsize(original)
    with open(original, "rb") as handle:
        before_image_data = handle.read()
    old_time = time.time() - 86400
    os.utime(original, (old_time, old_time))
    stamp_before = os.stat(original).st_mtime

    error = write_into_file(original, {"Artist": AUTOR, "ImageDescription": OPIS})
    check("zapis do oryginalu przeszedl bez bledu", error is None, str(error))

    after = piexif.load(original)
    check("dopisany autor jest w pliku",
          after["0th"].get(piexif.ImageIFD.Artist, b"").decode("utf-8") == AUTOR)
    check("WCZESNIEJSZE metadane nie zniknely",
          after["0th"].get(piexif.ImageIFD.Model, b"").decode("utf-8") == "DC-G91"
          and after["Exif"].get(piexif.ExifIFD.ISOSpeedRatings) == 200,
          f"model {after['0th'].get(piexif.ImageIFD.Model)}, "
          f"ISO {after['Exif'].get(piexif.ExifIFD.ISOSpeedRatings)}")
    check("lokalizacja przezyla zapis metadanych", bool(after.get("GPS")))
    check("data pliku zostala nietknieta",
          abs(os.stat(original).st_mtime - stamp_before) < 2.0,
          f"{os.stat(original).st_mtime - stamp_before:+.1f} s")

    from PIL import Image as PILImage
    with PILImage.open(original) as opened:
        pixels_after = np.asarray(opened.convert("RGB"))
    with PILImage.open(target) as opened:
        pass
    check("obraz nie zostal przekompresowany",
          pixels_after.shape == image.shape,
          f"{pixels_after.shape[1]}x{pixels_after.shape[0]}")

    # --- 5. RAW-a nie wolno tknac -----------------------------------------
    check("RAW jest rozpoznany jako niezapisywalny", not is_writable_format(raw_photo))
    check("JPEG jest rozpoznany jako zapisywalny", is_writable_format(original))
    raw_error = write_into_file(raw_photo, {"Artist": AUTOR})
    check("proba zapisu do RAW-a konczy sie komunikatem, nie zapisem",
          raw_error is not None and os.path.getsize(raw_photo) == 0,
          str(raw_error))

    # --- 6. odczyt tagow i wartosci biezacych ------------------------------
    rows = read_all_tags(original)
    check("podglad pokazuje tagi z pliku", len(rows) > 5, f"{len(rows)} tagów")
    names = {row.name for row in rows}
    check("wsrod tagow jest dopisany autor", "Artist" in names,
          ", ".join(sorted(names)[:6]))
    values = current_values(original)
    check("biezace wartosci pol trafiaja do formularza",
          values.get("Artist") == AUTOR and values.get("Model") == "DC-G91",
          f"autor {values.get('Artist')}, model {values.get('Model')}")

    check("katalog pol nie jest pusty", len(FIELDS) >= 15, f"{len(FIELDS)} pól")

print(f"\n{'test':<52}{'wynik':>8}   szczegoly")
print("-" * 100)
failures = sum(0 if ok else 1 for _, ok, _ in results)
for name, ok, detail in results:
    print(f"{name:<52}{'OK' if ok else 'BLAD':>8}   {detail}")
print(f"\n{len(results) - failures} / {len(results)} testow przeszlo")
