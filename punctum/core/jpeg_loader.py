"""Wczytywanie plikow JPEG do tego samego toru, co RAW.

JPEG to material JUZ WYWOLANY: przeszedl przez balans bieli aparatu, jego
krzywa tonalna i krzywa sRGB, a zakres zostal obciety do 8 bitow. Zeby wszedl
w tor Punctum, ktory caly liczy liniowo, trzeba te krzywa zdjac - i to jest
cala roznica w kodzie. Cala reszta toru, lacznie z shaderem i eksportem, nie
musi wiedziec, skad wzial sie obraz.

Czego z JPEG-a nie odzyskamy - warto to znac, zanim ktos uzna za blad, ze
korekty dzialaja slabiej niz na RAW:

- **nie ma zapasu w swiatlach**. W RAW nad biala scianka zostaje jeszcze
  material do sciagniecia; w JPEG wszystko powyzej punktu bieli zostalo
  scietne przy zapisie i suwak swiatel nie ma czego wyciagac,
- **w cieniach jest 8 bitow zamiast dwunastu**. Mocne podnoszenie pokaze
  schodki tam, gdzie RAW dalby gladkie przejscie,
- **nie ma mnoznikow aparatu ani macierzy barw**, wiec temperatury "jak na
  ujeciu" nie da sie odtworzyc.

Balans bieli dzialla wiec inaczej i trzeba to powiedziec wprost. Przyjmujemy,
ze plik jest w sRGB o punkcie bieli D65 i ze taki wlasnie jest jego stan
wyjsciowy. Suwak temperatury przesuwa barwe WZGLEDEM tego, co zapisal aparat,
a nie wzgledem swiatla sceny: 6500 K nie znaczy tu "tak swiecilo slonce",
tylko "nie ruszam nic". Interfejs oznacza taki suwak jako wzgledny.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from . import whitebalance as wb
from .raw_loader import RawImage

JPEG_EXTENSIONS = (".jpg", ".jpeg", ".jpe")

# XYZ -> RGB. W plikach RAW to samo pole opisuje przejscie z XYZ do przestrzeni
# aparatu; dla JPEG-a "aparatem" jest po prostu sRGB, wiec bierzemy odwrotnosc
# macierzy sRGB -> XYZ. Dzieki temu caly aparat pojeciowy balansu bieli
# (krzywa Plancka, mnozniki kanalow) dziala bez zadnej gałęzi "jesli JPEG".
SRGB_XYZ = np.linalg.inv(wb.XYZ_RGB)

_neutral: tuple[float, float] | None = None


def srgb_to_linear(img: np.ndarray) -> np.ndarray:
    """Zdejmuje krzywa sRGB. Dokladna odwrotnosc pipeline.linear_to_srgb."""
    x = np.clip(img, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def neutral_temp_tint() -> tuple[float, float]:
    """Temperatura i odcien, przy ktorych mnozniki kanalow wychodza (1, 1, 1).

    To ten sam przeszukiwany punkt krzywej Plancka, co przy RAW, tylko cel
    znamy z gory: chcemy miejsca, w ktorym suwak zostawia zdjecie nietkniete.
    Liczymy raz na proces - przeszukanie kosztuje kilkadziesiat milisekund,
    a wynik jest staly.
    """
    global _neutral
    if _neutral is None:
        _neutral = wb.estimate_temp_tint(SRGB_XYZ, np.ones(3))
    return _neutral


def load_jpeg(path: str) -> RawImage:
    """Dekoduje JPEG do liniowego sRGB, respektujac orientacje z EXIF."""
    with Image.open(path) as handle:
        image = ImageOps.exif_transpose(handle)
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0

    linear = np.ascontiguousarray(srgb_to_linear(rgb).astype(np.float32))
    temp, tint = neutral_temp_tint()
    return RawImage(
        path=path,
        camera_linear=linear,
        cam_xyz=SRGB_XYZ,
        cam_to_srgb=wb.camera_to_srgb_matrix(SRGB_XYZ),  # wychodzi jednostkowa
        as_shot_temp=float(temp),
        as_shot_tint=float(tint),
        as_shot_mult=wb.camera_multipliers(SRGB_XYZ, temp, tint),
        raw_width=linear.shape[1],
        raw_height=linear.shape[0],
        source_format="jpeg",
    )


def jpeg_thumbnail(path: str, max_side: int = 400) -> np.ndarray | None:
    """Miniatura bez dekodowania calego pliku.

    `draft` kaze bibliotece rozpakowac JPEG od razu pomniejszony - przy
    kilkunastu tysiacach plikow w katalogu to roznica miedzy sekundami
    a minutami czekania na pasek miniatur.
    """
    try:
        with Image.open(path) as handle:
            handle.draft("RGB", (max_side, max_side))
            image = ImageOps.exif_transpose(handle)
            image.thumbnail((max_side, max_side))
            return np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (OSError, ValueError):
        return None
