"""Tor obrobki: z liniowego RAW do gotowego obrazu.

Kolejnosc operacji nie jest przypadkowa. Ekspozycja, balans bieli,
swiatla i cienie musza dzialac na danych LINIOWYCH - czyli takich,
w ktorych podwojna wartosc piksela oznacza dwa razy wiecej swiatla.
Dopiero na samym koncu nakladamy krzywa sRGB, ktora przygotowuje
obraz pod monitor. Odwrocenie tej kolejnosci daje plastikowe,
"cyfrowe" kolory - to najczestszy blad w amatorskich programach do obrobki RAW.

Modul udostepnia dwie drogi liczenia:
  develop()        - caly obraz, do podgladu dopasowanego do okna i eksportu
  develop_region() - tylko widoczny fragment, liczony z pelnej rozdzielczosci
Druga droga jest tym, co daje ostry obraz przy powiekszeniu 100 % i wyzej,
bez przeliczania calych 20 megapikseli na kazde przesuniecie kadru.
"""

from __future__ import annotations

import cv2
import numpy as np

from .geometry import orientation_steps, output_size, output_to_source
from .params import EditParams
from .raw_loader import RawImage
from . import whitebalance as wb

MID_GREY = 0.18  # szarosc 18% - punkt odniesienia dla kontrastu i masek
_EPS = 1e-6

# wagi luminancji wg Rec. 709 (takie same jak w sRGB)
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _luminance(img: np.ndarray) -> np.ndarray:
    return img @ LUMA


# --------------------------------------------------------------------- kolor


def apply_white_balance(img: np.ndarray, raw: RawImage, p: EditParams) -> np.ndarray:
    """Koryguje balans bieli wzgledem nastawy z aparatu."""
    if p.temperature is None and abs(p.tint) < 1e-9:
        return img
    temp = p.temperature if p.temperature is not None else raw.as_shot_temp
    tint = raw.as_shot_tint + p.tint
    target = wb.camera_multipliers(raw.cam_xyz, temp, tint)
    gain = (target / raw.as_shot_mult).astype(np.float32)
    return img * gain


def camera_to_srgb(img: np.ndarray, raw: RawImage) -> np.ndarray:
    """Z przestrzeni aparatu do liniowego sRGB (bez krzywej gamma)."""
    return img @ raw.cam_to_srgb.astype(np.float32).T


# --------------------------------------------------------------------- odcien


def apply_exposure(img: np.ndarray, ev: float) -> np.ndarray:
    if abs(ev) < 1e-6:
        return img
    return img * np.float32(2.0**ev)


def apply_highlights_shadows(img: np.ndarray, highlights: float, shadows: float) -> np.ndarray:
    """Rozjasnia cienie i sciaga swiatla, nie ruszajac srodkow tonalnych.

    Maski budujemy w dzialkach EV wzgledem szarosci 18%, a nie na surowej
    wartosci piksela - dzieki temu przejscia sa rownomierne i nie widac
    obwodek wokol kontrastowych krawedzi.
    """
    if abs(highlights) < 1e-6 and abs(shadows) < 1e-6:
        return img

    lum = np.maximum(_luminance(img), _EPS)
    ev = np.log2(lum / MID_GREY)
    gain = np.ones_like(ev)

    if abs(shadows) > 1e-6:
        mask = 1.0 - _smoothstep(-4.5, -0.5, ev)
        gain = gain * (1.0 + (shadows / 100.0) * mask * 1.2)
    if abs(highlights) > 1e-6:
        mask = _smoothstep(-0.2, 2.5, ev)
        gain = gain * (1.0 + (highlights / 100.0) * mask * 0.9)

    return img * gain[..., None].astype(np.float32)


def apply_whites_blacks(img: np.ndarray, whites: float, blacks: float) -> np.ndarray:
    """Przesuwa skrajne punkty histogramu: biel i czern.

    Czern to odjecie stalej - przesuwa punkt czerni, a srodkow tonalnych
    praktycznie nie rusza, bo 0.04 w skali liniowej to juz glebokie cienie.

    Biel dziala tylko w gornej czesci skali, od ok. 1.4 dzialki ponad
    szaroscia. Wczesniej byla zwyklym mnoznikiem calego obrazu, czyli drugim
    suwakiem ekspozycji pod inna nazwa - przy okazji prac nad automatem
    okazalo sie, ze taki suwak nie potrafi zrobic tego, po co istnieje:
    postawic punktu bieli bez rozjasniania calego zdjecia. Maska jest
    wyzsza niz maska swiatel (od -0.2 dzialki), wiec oba suwaki nie
    powielaja swojego dzialania: swiatla ratuja jasne partie, biel
    ustawia sam koniec skali.
    """
    out = img
    if abs(blacks) > 1e-6:
        offset = np.float32(-(blacks / 100.0) * 0.04)
        out = (out - offset) / np.float32(1.0 - offset)
    if abs(whites) > 1e-6:
        ev = np.log2(np.maximum(_luminance(out), _EPS) / MID_GREY)
        gain = 1.0 + (whites / 100.0) * _smoothstep(0.5, 3.0, ev) * 0.8
        out = out * gain[..., None].astype(np.float32)
    return out


def apply_contrast(img: np.ndarray, contrast: float) -> np.ndarray:
    """Kontrast jako krzywa potegowa zaczepiona w szarosci 18%."""
    if abs(contrast) < 1e-6:
        return img
    exponent = np.float32(1.0 + 0.6 * (contrast / 100.0))
    return np.float32(MID_GREY) * np.power(np.maximum(img, 0.0) / np.float32(MID_GREY) + _EPS, exponent)


def linear_to_srgb(img: np.ndarray) -> np.ndarray:
    """Krzywa przenoszenia sRGB - ostatni krok toru liniowego."""
    x = np.clip(img, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)


def apply_saturation(img: np.ndarray, saturation: float, vibrance: float) -> np.ndarray:
    """Nasycenie i jaskrawosc, liczone juz po krzywej przenoszenia.

    Na danych liniowych ta sama operacja podbijalaby szum w cieniach.
    """
    if abs(saturation) < 1e-6 and abs(vibrance) < 1e-6:
        return img

    lum = _luminance(img)[..., None]
    out = lum + (img - lum) * np.float32(1.0 + saturation / 100.0)

    if abs(vibrance) > 1e-6:
        mx, mn = out.max(axis=2), out.min(axis=2)
        current_sat = (mx - mn) / np.maximum(mx, _EPS)
        weight = (1.0 - np.clip(current_sat, 0.0, 1.0))[..., None]
        vib = np.float32(1.0 + (vibrance / 100.0) * 0.8) * weight + (1.0 - weight)
        lum2 = _luminance(out)[..., None]
        out = lum2 + (out - lum2) * vib

    return out


# ------------------------------------------------------------------ geometria


def geometry_size(raw: RawImage, p: EditParams) -> tuple[int, int]:
    """Rozmiar obrazu po zastosowaniu geometrii, jako (szerokosc, wysokosc)."""
    height, width = raw.camera_linear.shape[:2]
    return output_size(p, width, height)


def _warp(
    source: np.ndarray,
    p: EditParams,
    out_w: int,
    out_h: int,
    region: tuple[int, int, int, int] | None = None,
    scale: float = 1.0,
) -> np.ndarray:
    """Jedno przeksztalcenie zamiast trzech osobnych kroków.

    Obrot o 90 stopni, plynny obrot, kadrowanie i powiekszenie skladamy
    w jedna macierz i kazemy warpAffine policzyc wylacznie zadany prostokat.
    Koszt zalezy przez to od rozmiaru wyniku, a nie od rozmiaru zdjecia.

    Macierz pochodzi z tego samego miejsca, co macierz uzywana przez shader
    na karcie graficznej - dzieki temu oba tory nie moga sie rozjechac.
    """
    height, width = source.shape[:2]
    matrix = output_to_source(p, width, height, region=region, scale=scale)
    return cv2.warpAffine(
        source,
        matrix[:2].astype(np.float64),
        (int(out_w), int(out_h)),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )


def apply_geometry(img: np.ndarray, p: EditParams) -> np.ndarray:
    """Obrot o 90 stopni, plynny obrot i kadrowanie calego obrazu."""
    height, width = img.shape[:2]
    out_w, out_h = output_size(p, width, height)
    if (
        orientation_steps(p.orientation) == 0
        and abs(p.rotation) < 1e-9
        and p.crop == (0.0, 0.0, 1.0, 1.0)
    ):
        return img  # nic do zrobienia, nie ma po co kopiowac 240 MB
    return _warp(img, p, out_w, out_h)


def _region_from_source(
    raw: RawImage, p: EditParams, rect: tuple[int, int, int, int], scale: float = 1.0
) -> np.ndarray:
    """Wycina fragment obrazu wynikowego prosto z pelnej rozdzielczosci."""
    out_w = max(1, int(round(rect[2] * scale)))
    out_h = max(1, int(round(rect[3] * scale)))
    return _warp(raw.camera_linear, p, out_w, out_h, region=rect, scale=scale)


# ------------------------------------------------------------- redukcja szumu

# Implementacja w denoise.py; import tutaj, bo reszta programu bierze ja z pipeline.
from .denoise import NLM_WINDOWS, apply_noise_reduction  # noqa: E402,F401


# ------------------------------------------------------------------ zlozenie


def apply_tone(img: np.ndarray, raw: RawImage, p: EditParams) -> np.ndarray:
    """Tor tonalny na danych w przestrzeni aparatu. Zwraca float 0..1."""
    img = apply_white_balance(img, raw, p)
    img = camera_to_srgb(img, raw)
    img = apply_exposure(img, p.exposure)
    img = apply_highlights_shadows(img, p.highlights, p.shadows)
    img = apply_whites_blacks(img, p.whites, p.blacks)
    img = apply_contrast(img, p.contrast)
    img = linear_to_srgb(img)
    return apply_saturation(img, p.saturation, p.vibrance)


def _to_uint8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def develop(
    raw: RawImage, p: EditParams, denoise: bool = True, quality: str = "fast"
) -> np.ndarray:
    """Pelny tor obrobki. Zwraca obraz RGB uint8 gotowy do wyswietlenia."""
    img = apply_geometry(raw.camera_linear, p)
    rgb8 = _to_uint8(apply_tone(img, raw, p))
    if denoise:
        rgb8 = apply_noise_reduction(rgb8, p.noise_luminance, p.noise_color, quality)
    return rgb8


def develop_region(
    raw: RawImage,
    p: EditParams,
    rect: tuple[int, int, int, int],
    scale: float = 1.0,
    denoise: bool = True,
    quality: str = "balanced",
) -> np.ndarray:
    """Liczy tylko wskazany prostokat obrazu wynikowego, z pelnej rozdzielczosci.

    Powyzej skali 1:1 caly tor - lacznie z odszumianiem - liczymy w
    rozdzielczosci natywnej, a dopiero gotowy obraz powiekszamy. Odwrotna
    kolejnosc rozciagalaby ziarno szumu ponad zasieg filtrow i przy 400 %
    odszumianie nie robiloby nic widocznego. Przy duzym powiekszeniu skalujemy
    najblizszym sasiadem, zeby bylo widac prawdziwe piksele, a nie interpolacje.
    """
    render_scale = min(float(scale), 1.0)
    patch = _region_from_source(raw, p, rect, render_scale)
    rgb8 = _to_uint8(apply_tone(patch, raw, p))
    if denoise:
        rgb8 = apply_noise_reduction(rgb8, p.noise_luminance, p.noise_color, quality)

    if scale > render_scale:
        out_w = max(1, int(round(rect[2] * scale)))
        out_h = max(1, int(round(rect[3] * scale)))
        interpolation = cv2.INTER_NEAREST if scale >= 2.5 else cv2.INTER_LINEAR
        rgb8 = cv2.resize(rgb8, (out_w, out_h), interpolation=interpolation)
    return rgb8


HISTOGRAM_SAMPLES = 400_000


def histogram(rgb8: np.ndarray, bins: int = 256) -> np.ndarray:
    """Histogram trzech kanalow, ksztalt (3, bins).

    Liczymy go na probce, nie na calym obrazie. Przy dwoch milionach pikseli
    `np.bincount` zajmuje kilka milisekund na kanal, a to caly budzet jednej
    klatki - tymczasem histogram z co trzeciego piksela wyglada identycznie.
    """
    height, width = rgb8.shape[:2]
    step = max(1, int(((height * width) / HISTOGRAM_SAMPLES) ** 0.5))
    sample = np.ascontiguousarray(rgb8[::step, ::step])
    return np.stack(
        [
            cv2.calcHist([sample], [channel], None, [bins], [0, 256]).ravel()
            for channel in range(3)
        ]
    )
