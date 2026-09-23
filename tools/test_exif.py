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
    layer_metadata,
    merge_keywords,
    normalise_datetime,
    read_all_tags,
    source_metadata,
    validate,
    write_into_file,
)
from punctum.core.export import ExportOptions, export_metadata  # noqa: E402
from punctum.core.settings import Settings  # noqa: E402

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

    # --- 7. pola Windows, komentarz i orientacja wracaja jako tekst ---------
    # exifread oddaje XPKeywords jako liste liczb, UserComment pomija bez
    # details, a orientacje opisuje slowami - formularz dostawal krzaki.
    KOMENTARZ = "Zachód słońca nad Łańcutem"
    source = os.path.join(tmp, "zrodlo.jpg")
    save_image(image, source, quality=90, location=(49.2992, 19.9496), metadata={
        "Make": "Panasonic", "Model": "DC-G91",
        "DateTimeOriginal": "2026-03-01 13:09:06", "ISOSpeedRatings": "3200",
        "FNumber": "1.7", "ExposureTime": "1/200", "Software": "Aparat 1.0",
        "Artist": "Aparat", "XPKeywords": "Tatry; zima", "UserComment": KOMENTARZ,
        "Orientation": "6",
    })
    values = current_values(source)
    check("slowa kluczowe Windows czytane jako tekst",
          values.get("XPKeywords") == "Tatry; zima", repr(values.get("XPKeywords")))
    check("komentarz z ogonkami czytany poprawnie",
          values.get("UserComment") == KOMENTARZ, repr(values.get("UserComment")))
    check("orientacja czytana jako liczba", values.get("Orientation") == "6",
          repr(values.get("Orientation")))

    # --- 8. warstwy: plik < zdjecie < okno eksportu -------------------------
    check("slowa kluczowe bez powtorek, przecinek tez dzieli",
          merge_keywords("Tatry; zima", "tatry, Wakacje 2026") == "Tatry; zima; Wakacje 2026",
          merge_keywords("Tatry; zima", "tatry, Wakacje 2026"))
    layered = layer_metadata(
        {"Artist": "Aparat", "Make": "Panasonic", "XPKeywords": "Tatry",
         "Orientation": "6", "Software": "Aparat 1.0"},
        {"Artist": "Kolega", "XPSubject": "Temat zdjęcia", "XPKeywords": "Tatry; zima"},
        {"Artist": AUTOR, "XPKeywords": "Wakacje 2026; zima"},
        software="Punctum 0.1.0",
    )
    check("autor z okna eksportu wygrywa ze zdjeciem", layered.get("Artist") == AUTOR,
          layered.get("Artist", "-"))
    check("pole zdjecia wygrywa z plikiem", layered.get("XPSubject") == "Temat zdjęcia")
    check("dane aparatu zostaja", layered.get("Make") == "Panasonic")
    check("slowa kluczowe zdjecia i serii sie sumuja",
          layered.get("XPKeywords") == "Tatry; zima; Wakacje 2026", layered.get("XPKeywords", "-"))
    check("orientacja wyniku zawsze normalna (piksele juz obrocone)",
          layered.get("Orientation") == "1")
    check("program zapisujacy to Punctum", layered.get("Software") == "Punctum 0.1.0")

    # --- 9. pola okna eksportu ---------------------------------------------
    overrides = ExportOptions(
        add_author=False, author="Ktoś", add_copyright=True, copyright="© 2026 X",
        keywords=" Wakacje ",
    ).metadata_overrides()
    check("odznaczony autor nie trafia do pliku", "Artist" not in overrides, str(overrides))
    check("zaznaczone prawa autorskie trafiaja", overrides.get("Copyright") == "© 2026 X")
    check("puste pola pomijane, reszta przycieta",
          "XPSubject" not in overrides and overrides.get("XPKeywords") == "Wakacje",
          str(overrides))

    # --- 10. eksport z danymi aparatu, we wszystkich formatach --------------
    series = ExportOptions(add_author=True, author=AUTOR, keywords="Wakacje 2026")
    fields, location = export_metadata(source, EditParams(metadata={"XPSubject": "Temat"}),
                                       series)
    check("GPS aparatu przechodzi, gdy nie nadano lokalizacji",
          location is not None and abs(location[0] - 49.2992) < 1e-4, str(location))
    _, own_location = export_metadata(source, EditParams(latitude=50.0, longitude=20.0), series)
    check("lokalizacja z mapy wygrywa z GPS aparatu", own_location == (50.0, 20.0),
          str(own_location))
    for ext in (".jpg", ".png", ".tif"):
        out = os.path.join(tmp, "seria" + ext)
        save_image(image, out, location=location, metadata=fields)
        got = current_values(out)
        check(f"{ext}: data wykonania z aparatu",
              got.get("DateTimeOriginal") == "2026:03:01 13:09:06", got.get("DateTimeOriginal", "-"))
        check(f"{ext}: autor z okna eksportu, temat ze zdjecia",
              got.get("Artist") == AUTOR and got.get("XPSubject") == "Temat",
              f"{got.get('Artist')} / {got.get('XPSubject')}")
        check(f"{ext}: slowa kluczowe pliku i serii",
              got.get("XPKeywords") == "Tatry; zima; Wakacje 2026", got.get("XPKeywords", "-"))
        check(f"{ext}: orientacja 1, ISO z aparatu",
              got.get("Orientation") == "1" and got.get("ISOSpeedRatings") == "3200",
              f"{got.get('Orientation')} / {got.get('ISOSpeedRatings')}")
        _, written_location = source_metadata(out)
        check(f"{ext}: GPS w pliku",
              written_location is not None and abs(written_location[1] - 19.9496) < 1e-4,
              str(written_location))

    # --- 11. ustawienia: autor zapamietany, jednorazowa zmiana nie -----------
    settings_file = os.path.join(tmp, "settings.json")
    Settings(export_author=" Jan ", export_add_author=True,
             export_copyright="© J").save(settings_file)
    loaded = Settings.load(settings_file)
    check("autor w ustawieniach przezywa zapis",
          loaded.export_author == "Jan" and loaded.export_add_author
          and loaded.export_copyright == "© J")

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from types import SimpleNamespace

    from PySide6.QtWidgets import QApplication

    qt_app = QApplication.instance() or QApplication([])
    from punctum.app.export_dialog import ExportDialog
    from punctum.app.main_window import MainWindow

    # Atrapa okna: _remember_export_options zapisuje ustawienia, a test nie
    # ma prawa ruszyc ustawien uzytkownika - stad save zaslepione.
    fake = SimpleNamespace(settings=Settings(export_author="Jan"))
    fake.settings.save = lambda *args, **kwargs: True
    MainWindow._remember_export_options(
        fake, ExportOptions(add_author=True, author="Ktoś inny", keywords="Tatry")
    )
    again = MainWindow._export_options(fake)
    check("pamietane zaznaczenie autora, ale nie jego jednorazowa zmiana",
          again.add_author and again.author == "Jan", f"{again.add_author} / {again.author}")
    check("slowa kluczowe nie wracaja przy kolejnym eksporcie", again.keywords == "")

    # --- 12. okno eksportu -------------------------------------------------
    dialog = ExportDialog(ExportOptions(folder=tmp, author=AUTOR, add_author=False,
                                        copyright="© 2026 X", add_copyright=True), [source])
    check("autor z ustawien wpisany, pole wylaczone",
          dialog.author_edit.text() == AUTOR and not dialog.author_edit.isEnabled())
    dialog.author_box.setChecked(True)
    check("zaznaczenie wlacza pole autora", dialog.author_edit.isEnabled())
    dialog.author_edit.setText("Inny Autor")
    dialog.keywords_edit.setText("Tatry")
    collected = dialog.collect().metadata_overrides()
    check("okno oddaje poprawionego autora, prawa i tagi",
          collected.get("Artist") == "Inny Autor" and collected.get("XPKeywords") == "Tatry"
          and collected.get("Copyright") == "© 2026 X", str(collected))
    dialog.deleteLater()

from wspolne import wypisz  # noqa: E402  (test jest skryptem, nie modulem)

sys.exit(wypisz(results))
