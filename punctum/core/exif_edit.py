"""Podglad i edycja metadanych EXIF.

Dwie rzeczy, ktore trzeba rozdzielic, bo rzadza sie innymi prawami.

**Podglad** obejmuje wszystko, co w pliku jest. Czyta exifread, ten sam, ktory
obsluguje panel danych zdjecia - dziala na RW2 tak samo jak na JPEG-u.

**Edycja** obejmuje tylko to, co da sie zapisac z powrotem. Tu granica jest
ostra i wynika z formatu, nie z naszej wygody: blok EXIF potrafimy przepisac
w JPEG-u, bo to standardowy naglowek. W RW2 nie - to zamkniety format
Panasonica i majstrowanie w nim skonczyloby sie uszkodzonym plikiem.

Dlatego zmiany trzymamy w sidecarze (jak korekty i wspolrzedne), a do pliku
wpisujemy je w dwoch miejscach: zawsze w wyeksportowanym JPEG-u, a na zadanie
takze w oryginale - o ile oryginal jest JPEG-iem.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import exifread
from ..przeklad import N_, t


@dataclass(frozen=True)
class Field:
    """Jedno pole, ktore uzytkownik moze zmienic."""

    key: str  # nasza nazwa, uzywana w sidecarze
    label: str  # etykieta w interfejsie
    group: str
    kind: str = "text"  # text | multiline | datetime | number | choice
    hint: str = ""
    choices: tuple[tuple[str, str], ...] = ()


# Kolejnosc ma znaczenie - w takiej pojawia sie w panelu.
FIELDS: tuple[Field, ...] = (
    Field("Artist", N_("Autor"), N_("Autorstwo"),
          hint=N_("Kto zrobił zdjęcie. Trafia do pola Artist.")),
    Field("Copyright", N_("Prawa autorskie"), N_("Autorstwo"),
          hint=N_("np. © 2026 Imię Nazwisko")),
    Field("ImageDescription", N_("Tytuł / opis"), N_("Opis"), kind="multiline"),
    Field("UserComment", N_("Komentarz"), N_("Opis"), kind="multiline"),
    Field("XPKeywords", N_("Słowa kluczowe"), N_("Opis"),
          hint=N_("Oddzielone średnikiem — tak czyta je Windows.")),
    Field("XPSubject", N_("Temat"), N_("Opis")),
    Field("DateTimeOriginal", N_("Data wykonania"), N_("Czas"), kind="datetime",
          hint=N_("RRRR-MM-DD GG:MM:SS")),
    Field("DateTimeDigitized", N_("Data digitalizacji"), N_("Czas"), kind="datetime"),
    Field("DateTime", N_("Data modyfikacji"), N_("Czas"), kind="datetime"),
    Field("Make", N_("Producent"), N_("Sprzęt")),
    Field("Model", N_("Model aparatu"), N_("Sprzęt")),
    Field("LensModel", N_("Obiektyw"), N_("Sprzęt")),
    Field("BodySerialNumber", N_("Numer seryjny"), N_("Sprzęt")),
    Field("Software", N_("Oprogramowanie"), N_("Sprzęt")),
    Field("ISOSpeedRatings", N_("ISO"), N_("Naświetlenie"), kind="number"),
    Field("FNumber", N_("Przysłona"), N_("Naświetlenie"), kind="number",
          hint=N_("Sama liczba, np. 5.6")),
    Field("ExposureTime", N_("Czas naświetlania"), N_("Naświetlenie"),
          hint=N_("Ułamek albo sekundy, np. 1/250 lub 2")),
    Field("FocalLength", N_("Ogniskowa"), N_("Naświetlenie"), kind="number", hint=N_("w mm")),
    Field("Orientation", N_("Orientacja"), N_("Obraz"), kind="choice", choices=(
        ("1", N_("Normalna")),
        ("3", N_("Obrócone o 180°")),
        ("6", N_("Obrócone w prawo (90° CW)")),
        ("8", N_("Obrócone w lewo (90° CCW)")),
    )),
)

FIELDS_BY_KEY = {field.key: field for field in FIELDS}
GROUPS = tuple(dict.fromkeys(field.group for field in FIELDS))


def is_writable_format(path: str) -> bool:
    """Czy w TEN plik da sie wpisac metadane bez ryzyka jego uszkodzenia."""
    return os.path.splitext(path)[1].lower() in (".jpg", ".jpeg", ".jpe")


# ------------------------------------------------------------- podglad


@dataclass(frozen=True)
class TagRow:
    """Jeden wiersz w podgladzie wszystkich tagow."""

    group: str
    name: str
    value: str


_SKIP_PREFIXES = ("JPEGThumbnail", "TIFFThumbnail", "Thumbnail ")


def read_all_tags(path: str) -> list[TagRow]:
    """Wszystkie tagi zapisane w pliku, pogrupowane, do podgladu.

    Miniatury pomijamy: to kilkadziesiat kilobajtow danych binarnych, ktore
    w tabelce nie znacza nic, a potrafia ja zatkac.
    """
    try:
        with open(path, "rb") as handle:
            tags = exifread.process_file(handle, details=False)
    except OSError:
        return []

    rows: list[TagRow] = []
    for key in sorted(tags):
        if key.startswith(_SKIP_PREFIXES):
            continue
        group, _, name = key.partition(" ")
        text = str(tags[key]).strip()
        if len(text) > 300:  # dlugie ciagi binarne tez nie wnosza nic do tabelki
            text = text[:300] + "…"
        rows.append(TagRow(group or "EXIF", name or key, text))
    return rows


def _read_tags(path: str) -> dict:
    """Tagi pliku do edycji i eksportu.

    `details=True`, bo bez niego exifread pomija UserComment - komentarz
    wpisany wczesniej znikal z formularza. Kosztuje to milisekunde.
    Miniatury nie wyciagamy, bo do niczego tu nie sluzy.
    """
    try:
        with open(path, "rb") as handle:
            return exifread.process_file(handle, details=True, extract_thumbnail=False)
    except OSError:
        return {}
    except Exception:  # noqa: BLE001 - nietypowa notatka producenta nie moze zablokowac zdjecia
        try:
            with open(path, "rb") as handle:
                return exifread.process_file(handle, details=False, extract_thumbnail=False)
        except Exception:  # noqa: BLE001
            return {}


def _decode_user_comment(raw: bytes) -> str:
    """UserComment: pierwsze osiem bajtow mowi, jak czytac reszte.

    exifread czyta wariant UNICODE jako Latin-1 i robi z ogonkow krzaki.
    Kolejnosc bajtow UTF-16 zgadujemy po zerach: w tekscie lacinskim co drugi
    bajt jest zerem, a to, po ktorej stronie stoi, zdradza kolejnosc.
    """
    code, body = raw[:8], raw[8:]
    if code.startswith(b"UNICODE"):
        even_zeros = body[0::2].count(0)
        odd_zeros = body[1::2].count(0)
        encoding = "utf-16-be" if even_zeros > odd_zeros else "utf-16-le"
        text = body.decode(encoding, errors="ignore")
    else:  # ASCII, JIS albo osiem zer ("nieokreslone") - w praktyce ASCII/UTF-8
        text = body.decode("utf-8", errors="ignore")
    return text.replace("\x00", "").strip()


def _tag_text(key: str, tag) -> str:
    """Wartosc tagu jako tekst do formularza - tam, gdzie str() exifreada klamie."""
    values = getattr(tag, "values", None)
    if key.startswith("XP") and isinstance(values, list):
        # Pola Windows to UTF-16LE zapisane jako BYTE - exifread oddaje liste liczb.
        try:
            return bytes(values).decode("utf-16-le", errors="ignore").replace("\x00", "").strip()
        except (TypeError, ValueError):
            return ""
    if key == "UserComment" and isinstance(values, list):
        try:
            return _decode_user_comment(bytes(values))
        except (TypeError, ValueError):
            return ""
    if key == "Orientation" and isinstance(values, list) and values:
        # Formularz zna liczby 1/3/6/8, a exifread podaje opis ("Rotated 90 CW").
        # Opis nie pasowal do zadnej pozycji listy, lista pokazywala "Normalna"
        # i przy pierwszej zmianie innego pola do sidecara szla orientacja 1.
        return str(values[0])
    return str(tag).strip()


def current_values(path: str) -> dict[str, str]:
    """Obecne wartosci pol edytowalnych - to, co widac w polach formularza."""
    return _values_from_tags(_read_tags(path))


def source_metadata(path: str) -> tuple[dict[str, str], tuple[float, float] | None]:
    """Wartosci pol i wspolrzedne GPS zapisane w pliku zrodlowym - jednym odczytem.

    Z tego powstaje podstawa metadanych pliku wynikowego: bez niej eksport
    gubil date wykonania, aparat, naswietlenie i GPS z telefonu.
    """
    from .metadata import _dms_to_degrees

    tags = _read_tags(path)
    location = None
    if "GPS GPSLatitude" in tags and "GPS GPSLongitude" in tags:
        latitude = _dms_to_degrees(
            tags["GPS GPSLatitude"], str(tags.get("GPS GPSLatitudeRef", "")).strip()
        )
        longitude = _dms_to_degrees(
            tags["GPS GPSLongitude"], str(tags.get("GPS GPSLongitudeRef", "")).strip()
        )
        if latitude is not None and longitude is not None:
            location = (latitude, longitude)
    return _values_from_tags(tags), location


def _values_from_tags(tags: dict) -> dict[str, str]:
    # exifread trzyma te same pola pod roznymi przedrostkami, zaleznie od
    # tego, w ktorym bloku pliku siedza.
    lookup = {
        "Artist": ("Image Artist",),
        "Copyright": ("Image Copyright",),
        "ImageDescription": ("Image ImageDescription",),
        "UserComment": ("EXIF UserComment",),
        "XPKeywords": ("Image XPKeywords",),
        "XPSubject": ("Image XPSubject",),
        "DateTimeOriginal": ("EXIF DateTimeOriginal",),
        "DateTimeDigitized": ("EXIF DateTimeDigitized",),
        "DateTime": ("Image DateTime",),
        "Make": ("Image Make",),
        "Model": ("Image Model",),
        "LensModel": ("EXIF LensModel", "MakerNote LensType"),
        "BodySerialNumber": ("EXIF BodySerialNumber", "Image BodySerialNumber"),
        "Software": ("Image Software",),
        "ISOSpeedRatings": ("EXIF ISOSpeedRatings", "EXIF PhotographicSensitivity",
                            "Image Tag 0x0017", "Image Tag 0x0037"),
        "FNumber": ("EXIF FNumber",),
        "ExposureTime": ("EXIF ExposureTime",),
        "FocalLength": ("EXIF FocalLength",),
        "Orientation": ("Image Orientation",),
    }

    found: dict[str, str] = {}
    for key, candidates in lookup.items():
        for candidate in candidates:
            if candidate in tags:
                text = _tag_text(key, tags[candidate])
                if text:  # aparaty wpisuja puste komentarze ze spacji i zer
                    found[key] = text
                break
    return found


# --------------------------------------------------- metadane eksportu


def merge_keywords(*groups: str) -> str:
    """Laczy slowa kluczowe z kilku zrodel: kolejnosc zostaje, powtorki znikaja.

    Przyjmujemy srednik (tak zapisuje Windows) i przecinek (tak wpisuje
    wiekszosc ludzi). Powtorki porownujemy bez wielkosci liter, bo "Tatry"
    i "tatry" to dla wyszukiwarki zdjec ten sam tag.
    """
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for word in (group or "").replace(",", ";").split(";"):
            word = word.strip()
            if word and word.casefold() not in seen:
                seen.add(word.casefold())
                merged.append(word)
    return "; ".join(merged)


def layer_metadata(camera: dict[str, str], photo: dict[str, str],
                   export: dict[str, str], software: str = "") -> dict[str, str]:
    """Pola pliku wynikowego z trzech warstw: plik zrodlowy < zdjecie < okno eksportu.

    Kolejnosc ustalil uzytkownik: to, co wpisane przy eksporcie, obowiazuje
    cala serie i wygrywa z polami pojedynczych zdjec. Wyjatkiem sa slowa
    kluczowe - te sie sumuja, bo tag serii ("Wakacje 2026") i tag zdjecia
    ("zachod slonca") nie wykluczaja sie.
    """
    result = {key: value for key, value in camera.items() if key in FIELDS_BY_KEY}
    if software:
        # Program, ktory zapisal plik, to my - nie aparat i nie Lightroom,
        # ktory wyeksportowal JPEG-a zrodlowego.
        result["Software"] = software
    for key, value in photo.items():
        if str(value).strip():
            result[key] = str(value).strip()
    for key, value in export.items():
        text = str(value).strip()
        if key == "XPKeywords":
            text = merge_keywords(result.get("XPKeywords", ""), text)
        if text:
            result[key] = text
    # Piksele sa juz obrocone (LibRaw i exif_transpose robia to przy
    # wczytaniu), wiec kazda inna orientacja w pliku wynikowym kazalaby
    # przegladarce obrocic zdjecie drugi raz.
    result["Orientation"] = "1"
    return result


# ------------------------------------------------------- zapis do pliku


def normalise_datetime(text: str) -> str | None:
    """Data w dowolnym z przyjmowanych zapisow -> format EXIF.

    EXIF chce "RRRR:MM:DD GG:MM:SS" - z dwukropkami takze w dacie, co jest
    myloce dla kazdego, kto to wpisuje recznie. Przyjmujemy wiec i myslniki,
    i dwukropki, a na format EXIF przepisujemy sami.
    """
    from datetime import datetime

    raw = text.strip()
    if not raw:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S",
                    "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern).strftime("%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _rational(text: str) -> tuple[int, int] | None:
    """Liczba albo ulamek (np. 1/250) -> para licznik, mianownik."""
    raw = text.strip().replace(",", ".")
    if not raw:
        return None
    try:
        if "/" in raw:
            top, _, bottom = raw.partition("/")
            return (int(float(top)), int(float(bottom)))
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return (int(round(value * 10000)), 10000)


def validate(key: str, text: str) -> str | None:
    """Zwraca komunikat o bledzie albo None, gdy wartosc jest do przyjecia."""
    field = FIELDS_BY_KEY.get(key)
    if field is None or not text.strip():
        return None
    if field.kind == "datetime" and normalise_datetime(text) is None:
        return t("Data ma mieć postać RRRR-MM-DD GG:MM:SS")
    if field.kind == "number" and _rational(text) is None:
        return t("To pole przyjmuje liczbę")
    if key == "ExposureTime" and _rational(text) is None:
        return t("Czas podaj jako ułamek (1/250) albo liczbę sekund")
    if key == "Orientation" and text.strip() not in dict(field.choices):
        return t("Nieznana wartość orientacji")
    return None


def _fill_ifds(metadata: dict[str, str], location=None) -> dict:
    """Nasze pola -> struktura, ktorej oczekuje piexif.

    Puste wartosci pomijamy: puste pole w formularzu znaczy "nie zmieniam",
    a nie "skasuj tag". Kasowanie byloby decyzja nieodwracalna, wiec nie
    chcemy jej podejmowac przez nieuwage.
    """
    import piexif

    zeroth: dict = {}
    exif: dict = {}

    ascii_zeroth = {
        "Artist": piexif.ImageIFD.Artist,
        "Copyright": piexif.ImageIFD.Copyright,
        "ImageDescription": piexif.ImageIFD.ImageDescription,
        "Make": piexif.ImageIFD.Make,
        "Model": piexif.ImageIFD.Model,
        "Software": piexif.ImageIFD.Software,
        "DateTime": piexif.ImageIFD.DateTime,
    }
    ascii_exif = {
        "DateTimeOriginal": piexif.ExifIFD.DateTimeOriginal,
        "DateTimeDigitized": piexif.ExifIFD.DateTimeDigitized,
        "LensModel": piexif.ExifIFD.LensModel,
        "BodySerialNumber": piexif.ExifIFD.BodySerialNumber,
    }
    # Pola "XP" Windows trzyma jako UTF-16 z koncowym zerem, jako ciag bajtow.
    windows_text = {
        "XPKeywords": piexif.ImageIFD.XPKeywords,
        "XPSubject": piexif.ImageIFD.XPSubject,
    }

    for key, raw in metadata.items():
        text = (raw or "").strip()
        if not text:
            continue
        if key in ascii_zeroth:
            value = normalise_datetime(text) if key == "DateTime" else text
            zeroth[ascii_zeroth[key]] = (value or text).encode("utf-8")
        elif key in ascii_exif:
            value = normalise_datetime(text) if key.startswith("DateTime") else text
            exif[ascii_exif[key]] = (value or text).encode("utf-8")
        elif key in windows_text:
            zeroth[windows_text[key]] = text.encode("utf-16-le") + b"\x00\x00"
        elif key == "UserComment":
            # Pierwsze osiem bajtow mowi, w jakim kodowaniu jest reszta.
            exif[piexif.ExifIFD.UserComment] = b"UNICODE\x00" + text.encode("utf-16-le")
        elif key == "ISOSpeedRatings":
            try:
                exif[piexif.ExifIFD.ISOSpeedRatings] = int(float(text))
            except ValueError:
                pass
        elif key == "Orientation":
            try:
                zeroth[piexif.ImageIFD.Orientation] = int(text)
            except ValueError:
                pass
        elif key in ("FNumber", "ExposureTime", "FocalLength"):
            rational = _rational(text)
            if rational is not None:
                exif[getattr(piexif.ExifIFD, key)] = rational

    result = {"0th": zeroth, "Exif": exif, "1st": {}, "thumbnail": None}
    if location is not None:
        result["GPS"] = _gps_ifd(*location)
    return result


def _gps_ifd(latitude: float, longitude: float) -> dict:
    import piexif

    def dms(value: float):
        magnitude = abs(float(value))
        degrees = int(magnitude)
        minutes_float = (magnitude - degrees) * 60.0
        minutes = int(minutes_float)
        seconds = (minutes_float - minutes) * 60.0
        return ((degrees, 1), (minutes, 1), (int(round(seconds * 10000)), 10000))

    return {
        piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),
        piexif.GPSIFD.GPSLatitudeRef: "N" if latitude >= 0 else "S",
        piexif.GPSIFD.GPSLatitude: dms(latitude),
        piexif.GPSIFD.GPSLongitudeRef: "E" if longitude >= 0 else "W",
        piexif.GPSIFD.GPSLongitude: dms(longitude),
    }


def exif_bytes(metadata: dict[str, str] | None,
               location: tuple[float, float] | None) -> bytes | None:
    """Blok EXIF do wstawienia w NOWY plik (eksport). None, gdy nie ma czego."""
    if not metadata and location is None:
        return None
    try:
        import piexif
    except ImportError:
        return None

    def dump(fields: dict[str, str]) -> bytes | None:
        try:
            return piexif.dump(_fill_ifds(fields, location))
        except Exception:  # noqa: BLE001 - zla wartosc nie moze przerwac eksportu
            return None

    block = dump(metadata or {})
    if block is None and metadata:
        # Od kiedy przepisujemy dane z pliku zrodlowego, jedna dziwna wartosc
        # z aparatu zabieralaby cala reszte - z data wykonania wlacznie.
        # Odsiewamy wiec tylko te pola, ktorych piexif nie przyjmuje.
        good = {key: value for key, value in metadata.items() if dump({key: value})}
        block = dump(good)
    return block


def write_into_file(path: str, metadata: dict[str, str] | None,
                    location: tuple[float, float] | None = None) -> str | None:
    """Wpisuje metadane wprost w istniejacy plik. Zwraca komunikat o bledzie.

    Trzy rzeczy, ktore trzeba tu uszanowac:

    1. **Obraz zostaje nietkniety.** piexif podmienia sam naglowek metadanych,
       wiec nie ma mowy o ponownej kompresji i utracie jakosci.
    2. **Reszta metadanych zostaje.** Wczytujemy to, co w pliku juz jest,
       i dokladamy swoje pola. Inaczej zapis autora kasowalby dane aparatu.
    3. **Data pliku zostaje.** Inaczej kazda poprawka opisu przestawialaby
       porzadek chronologiczny w kazdym menedzerze plikow.
    """
    if not is_writable_format(path):
        return t("{plik}: tego formatu nie da się zapisać", plik=os.path.basename(path))
    if not metadata and location is None:
        return None

    try:
        import piexif
    except ImportError:
        return t("Brak biblioteki piexif")

    try:
        existing = piexif.load(path)
    except Exception:  # noqa: BLE001 - plik bez EXIF-u tez wolno opisac
        existing = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    fresh = _fill_ifds(metadata or {}, location)
    for block in ("0th", "Exif", "GPS"):
        merged = dict(existing.get(block) or {})
        merged.update(fresh.get(block) or {})
        existing[block] = merged
    existing["thumbnail"] = None  # miniatura i tak nie pasuje po zmianie danych

    times = None
    try:
        info = os.stat(path)
        times = (info.st_atime, info.st_mtime)
    except OSError:
        pass

    try:
        piexif.insert(piexif.dump(existing), path)
    except Exception as error:  # noqa: BLE001
        return f"{os.path.basename(path)}: {type(error).__name__} — {error}"

    if times is not None:
        try:
            os.utime(path, times)
        except OSError:
            pass
    return None
