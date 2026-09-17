"""Zapis nastaw edycji obok zdjecia - plik XMP.

Zasada nieniszczaca dotyczy takze zapisu: **pliku ze zdjeciem nie ruszamy**.
Nastawy ida do osobnego pliku XMP lezacego obok, tak jak robi to Lightroom
i darktable.

W srodku sa dwa komplety wartosci i to jest celowe.

**Przestrzen `crs:`** - te same nazwy pol, ktorych uzywa Camera Raw. Dzieki
temu inny program cos z naszego pliku odczyta. Zgodnosc jest jednak tylko
czesciowa: nasze suwaki nie odpowiadaja jeden do jednego lightroomowym, bo
inaczej liczymy maski swiatel i cieni, a suwak bieli dziala u nas na samym
szczycie histogramu. Traktujemy te pola jako grzecznosc wobec innych
programow, nie jako zrodlo prawdy.

**Przestrzen `punctum:`** - nasze dokladne wartosci. To z nich czytamy przy
otwieraniu zdjecia i tylko one gwarantuja, ze zdjecie wroci dokladnie takie,
jakie bylo.

Cudzych plikow nie nadpisujemy. Jesli pod nasza sciezka lezy juz XMP bez
naszej przestrzeni nazw - czyli czyjas praca w innym programie - nasze
nastawy ida obok, do `<nazwa>.punctum.xmp`. Dodatkowy plik jest mniejszym
zlem niz skasowana cudza robota.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime

from .loader import is_raw
from .params import EditParams

PUNCTUM_NS = "https://github.com/Riberrr/Punctum/ns/1.0/"
CRS_NS = "http://ns.adobe.com/camera-raw-settings/1.0/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

SIDECAR_SUFFIX = ".xmp"
OWN_SUFFIX = ".punctum.xmp"

# orientacja w stopniach -> wartosc pola tiff:Orientation
_TIFF_ORIENTATION = {0: 1, 90: 6, 180: 3, 270: 8}


def _standard_path(photo_path: str) -> str:
    """Miejsce, w ktorym sidecara szuka Lightroom albo darktable.

    Przy RAW to nazwa bez rozszerzenia (`P1170926.xmp`) - taka jest konwencja
    Adobe. Przy JPEG-u zostawiamy pelna nazwe (`foto.jpg.xmp`), bo inaczej RAW
    i JPEG o tej samej nazwie w jednym katalogu bilyby sie o ten sam plik.
    """
    if is_raw(photo_path):
        return os.path.splitext(photo_path)[0] + SIDECAR_SUFFIX
    return photo_path + SIDECAR_SUFFIX


def _written_by_us(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return PUNCTUM_NS in handle.read(8192)
    except OSError:
        return False


def sidecar_path(photo_path: str) -> str:
    """Gdzie leza nastawy tego zdjecia."""
    standard = _standard_path(photo_path)
    if os.path.exists(standard) and not _written_by_us(standard):
        return photo_path + OWN_SUFFIX  # cudzej pracy nie nadpisujemy
    return standard


def has_edits(photo_path: str) -> bool:
    """Czy zdjecie ma zapisane nasze nastawy. Sam fakt istnienia pliku."""
    own = photo_path + OWN_SUFFIX
    if os.path.exists(own):
        return True
    standard = _standard_path(photo_path)
    return os.path.exists(standard) and _written_by_us(standard)


# ------------------------------------------------------------------- zapis


def _lines(params: EditParams) -> list[str]:
    """Pola XMP: najpierw grzecznosciowe crs:, potem nasze wlasne."""
    crop_left, crop_top, crop_right, crop_bottom = params.crop
    has_crop = (crop_left, crop_top, crop_right, crop_bottom) != (0.0, 0.0, 1.0, 1.0)

    fields: list[tuple[str, str]] = [
        ("crs:Version", "15.0"),
        ("crs:ProcessVersion", "11.0"),
        ("crs:Exposure2012", f"{params.exposure:+.2f}"),
        ("crs:Contrast2012", f"{params.contrast:+.0f}"),
        ("crs:Highlights2012", f"{params.highlights:+.0f}"),
        ("crs:Shadows2012", f"{params.shadows:+.0f}"),
        ("crs:Whites2012", f"{params.whites:+.0f}"),
        ("crs:Blacks2012", f"{params.blacks:+.0f}"),
        ("crs:Vibrance", f"{params.vibrance:+.0f}"),
        ("crs:Saturation", f"{params.saturation:+.0f}"),
        ("crs:LuminanceSmoothing", f"{params.noise_luminance:.0f}"),
        ("crs:ColorNoiseReduction", f"{params.noise_color:.0f}"),
        ("crs:HasCrop", "True" if has_crop else "False"),
        ("crs:CropLeft", f"{crop_left:.6f}"),
        ("crs:CropTop", f"{crop_top:.6f}"),
        ("crs:CropRight", f"{crop_right:.6f}"),
        ("crs:CropBottom", f"{crop_bottom:.6f}"),
        ("crs:CropAngle", f"{-params.rotation:.4f}"),
        ("tiff:Orientation", str(_TIFF_ORIENTATION.get(params.orientation % 360, 1))),
    ]
    if params.temperature is not None:
        fields.append(("crs:Temperature", f"{params.temperature:.0f}"))
        fields.append(("crs:Tint", f"{params.tint:+.0f}"))

    fields += [
        ("punctum:Version", "1"),
        # "jak na ujeciu" zapisujemy jako brak wartosci, nie jako liczbe -
        # inaczej po zmianie sposobu odczytu temperatury z aparatu stare pliki
        # narzucalyby zdjeciu nieaktualna nastawe.
        ("punctum:Temperature",
         "asShot" if params.temperature is None else f"{params.temperature:.4f}"),
        ("punctum:Tint", f"{params.tint:.4f}"),
        ("punctum:Exposure", f"{params.exposure:.4f}"),
        ("punctum:Contrast", f"{params.contrast:.4f}"),
        ("punctum:Highlights", f"{params.highlights:.4f}"),
        ("punctum:Shadows", f"{params.shadows:.4f}"),
        ("punctum:Whites", f"{params.whites:.4f}"),
        ("punctum:Blacks", f"{params.blacks:.4f}"),
        ("punctum:Vibrance", f"{params.vibrance:.4f}"),
        ("punctum:Saturation", f"{params.saturation:.4f}"),
        ("punctum:Orientation", str(int(params.orientation))),
        ("punctum:Rotation", f"{params.rotation:.4f}"),
        ("punctum:CropLeft", f"{crop_left:.6f}"),
        ("punctum:CropTop", f"{crop_top:.6f}"),
        ("punctum:CropRight", f"{crop_right:.6f}"),
        ("punctum:CropBottom", f"{crop_bottom:.6f}"),
        ("punctum:NoiseLuminance", f"{params.noise_luminance:.4f}"),
        ("punctum:NoiseColor", f"{params.noise_color:.4f}"),
    ]
    return [f'    {name}="{value}"' for name, value in fields]


def write_sidecar(photo_path: str, params: EditParams) -> str | None:
    """Zapisuje nastawy obok zdjecia. Zwraca sciezke pliku albo None.

    Pusty sidecar dla kazdego obejrzanego zdjecia zasmiecalby katalog na 2000
    plikow, wiec plik powstaje dopiero wtedy, gdy sa jakies korekty. Jesli
    jednak sidecar juz istnieje, zapisujemy zawsze - inaczej cofniecie
    wszystkich suwakow zostawialoby na dysku nieaktualne nastawy, ktore
    wrocilyby przy nastepnym otwarciu.
    """
    target = sidecar_path(photo_path)
    if params.is_default() and not os.path.exists(target):
        return None

    body = "\n".join(_lines(params))
    text = (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Punctum">\n'
        f' <rdf:RDF xmlns:rdf="{RDF_NS}">\n'
        '  <rdf:Description rdf:about=""\n'
        '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
        f'    xmlns:crs="{CRS_NS}"\n'
        '    xmlns:tiff="http://ns.adobe.com/tiff/1.0/"\n'
        f'    xmlns:punctum="{PUNCTUM_NS}"\n'
        f'    xmp:ModifyDate="{datetime.now().isoformat(timespec="seconds")}"\n'
        f'{body}/>\n'
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>\n'
    )

    try:
        # Zapis przez plik tymczasowy: przerwanie w polowie nie zostawia
        # uszkodzonego sidecara, ktory przy nastepnym otwarciu zjadlby korekty.
        temporary = target + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, target)
        return target
    except OSError:
        return None  # katalog tylko do odczytu, karta wyjeta, brak miejsca


# ------------------------------------------------------------------ odczyt


def _values(path: str) -> dict[str, str]:
    """Wyciaga pola z rdf:Description - i z atrybutow, i z elementow.

    Camera Raw zapisuje czesc pol jako atrybuty, a czesc jako elementy
    potomne. Nasze pliki maja same atrybuty, ale czytamy oba warianty, zeby
    dalo sie otworzyc plik napisany gdzie indziej.
    """
    root = ET.parse(path).getroot()
    found: dict[str, str] = {}
    for description in root.iter(f"{{{RDF_NS}}}Description"):
        for name, value in description.attrib.items():
            found[name] = value
        for child in description:
            if child.text and child.text.strip():
                found[child.tag] = child.text.strip()
    return found


def read_sidecar(photo_path: str) -> EditParams | None:
    """Wczytuje nasze nastawy. None, gdy ich nie ma albo plik jest nie nasz.

    Pol `crs:` celowo nie czytamy jako zamiennika. Sidecar z Lightrooma opisuje
    suwaki, ktore u nas licza sie inaczej - wczytanie go wygladaloby jak
    przeniesienie edycji, a po cichu zmienialoby zdjecie. Lepiej zostawic
    czysty panel niz podstawic wartosci, ktore znacza co innego.
    """
    for candidate in (photo_path + OWN_SUFFIX, _standard_path(photo_path)):
        if not os.path.exists(candidate) or not _written_by_us(candidate):
            continue
        try:
            found = _values(candidate)
        except (ET.ParseError, OSError):
            return None  # uszkodzony plik nie moze wywalic otwierania zdjecia

        def number(field: str, fallback: float) -> float:
            try:
                return float(found[f"{{{PUNCTUM_NS}}}{field}"])
            except (KeyError, TypeError, ValueError):
                return fallback

        temperature_text = found.get(f"{{{PUNCTUM_NS}}}Temperature", "asShot")
        try:
            temperature = None if temperature_text == "asShot" else float(temperature_text)
        except ValueError:
            temperature = None

        return EditParams(
            temperature=temperature,
            tint=number("Tint", 0.0),
            exposure=number("Exposure", 0.0),
            contrast=number("Contrast", 0.0),
            highlights=number("Highlights", 0.0),
            shadows=number("Shadows", 0.0),
            whites=number("Whites", 0.0),
            blacks=number("Blacks", 0.0),
            vibrance=number("Vibrance", 0.0),
            saturation=number("Saturation", 0.0),
            orientation=int(number("Orientation", 0.0)),
            rotation=number("Rotation", 0.0),
            crop=(
                number("CropLeft", 0.0),
                number("CropTop", 0.0),
                number("CropRight", 1.0),
                number("CropBottom", 1.0),
            ),
            noise_luminance=number("NoiseLuminance", 0.0),
            noise_color=number("NoiseColor", 25.0),
        )
    return None


def edited_photos(paths: list[str]) -> set[str]:
    """Ktore z podanych zdjec maja juz zapisane nastawy."""
    return {path for path in paths if has_edits(path)}
