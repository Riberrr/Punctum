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
    Field("Artist", "Autor", "Autorstwo",
          hint="Kto zrobił zdjęcie. Trafia do pola Artist."),
    Field("Copyright", "Prawa autorskie", "Autorstwo",
          hint="np. © 2026 Imię Nazwisko"),
    Field("ImageDescription", "Tytuł / opis", "Opis", kind="multiline"),
    Field("UserComment", "Komentarz", "Opis", kind="multiline"),
    Field("XPKeywords", "Słowa kluczowe", "Opis",
          hint="Oddzielone średnikiem — tak czyta je Windows."),
    Field("XPSubject", "Temat", "Opis"),
    Field("DateTimeOriginal", "Data wykonania", "Czas", kind="datetime",
          hint="RRRR-MM-DD GG:MM:SS"),
    Field("DateTimeDigitized", "Data digitalizacji", "Czas", kind="datetime"),
    Field("DateTime", "Data modyfikacji", "Czas", kind="datetime"),
    Field("Make", "Producent", "Sprzęt"),
    Field("Model", "Model aparatu", "Sprzęt"),
    Field("LensModel", "Obiektyw", "Sprzęt"),
    Field("BodySerialNumber", "Numer seryjny", "Sprzęt"),
    Field("Software", "Oprogramowanie", "Sprzęt"),
    Field("ISOSpeedRatings", "ISO", "Naświetlenie", kind="number"),
    Field("FNumber", "Przysłona", "Naświetlenie", kind="number",
          hint="Sama liczba, np. 5.6"),
    Field("ExposureTime", "Czas naświetlania", "Naświetlenie",
          hint="Ułamek albo sekundy, np. 1/250 lub 2"),
    Field("FocalLength", "Ogniskowa", "Naświetlenie", kind="number", hint="w mm"),
    Field("Orientation", "Orientacja", "Obraz", kind="choice", choices=(
        ("1", "Normalna"),
        ("3", "Obrócone o 180°"),
        ("6", "Obrócone w prawo (90° CW)"),
        ("8", "Obrócone w lewo (90° CCW)"),
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


def current_values(path: str) -> dict[str, str]:
    """Obecne wartosci pol edytowalnych - to, co widac w polach formularza."""
    try:
        with open(path, "rb") as handle:
            tags = exifread.process_file(handle, details=False)
    except OSError:
        return {}

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
                found[key] = str(tags[candidate]).strip()
                break
    return found


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
        return "Data ma mieć postać RRRR-MM-DD GG:MM:SS"
    if field.kind == "number" and _rational(text) is None:
        return "To pole przyjmuje liczbę"
    if key == "ExposureTime" and _rational(text) is None:
        return "Czas podaj jako ułamek (1/250) albo liczbę sekund"
    if key == "Orientation" and text.strip() not in dict(field.choices):
        return "Nieznana wartość orientacji"
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
        return piexif.dump(_fill_ifds(metadata or {}, location))
    except Exception:  # noqa: BLE001 - zla wartosc nie moze przerwac eksportu
        return None


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
        return f"{os.path.basename(path)}: tego formatu nie da się zapisać"
    if not metadata and location is None:
        return None

    try:
        import piexif
    except ImportError:
        return "Brak biblioteki piexif"

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
