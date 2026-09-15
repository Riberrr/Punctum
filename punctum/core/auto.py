"""Automatyczny dobor parametrow tonalnych.

Pomysl jest prosty: policzyc, jak rozlozone jest swiatlo na zdjeciu, a potem
tak dobrac suwaki, zeby obraz wypelnil caly zakres tonalny, nie przepalajac
swiatel i nie zalepiajac cieni. Analize robimy na danych LINIOWYCH, przed
krzywa gamma - tylko tam percentyle jasnosci maja fizyczny sens.

Wszystkie progi sa wyrazone w dzialkach EV, nie w ulamkach jasnosci. To
istotne: oko reaguje na swiatlo logarytmicznie, wiec "dwa razy za ciemno"
znaczy zawsze tyle samo, niezaleznie od tego, czy mowimy o cieniach, czy
o swiatlach. Progi liniowe dzialaja dobrze dla jednego zdjecia i rozjezdzaja
sie przy nastepnym.

Balansu bieli celowo nie ruszamy. Aparat zna warunki oswietlenia lepiej niz
histogram, a automat, ktory "poprawia" kolor zachodu slonca na neutralny,
psuje wiecej niz naprawia.

Kalibracja: wartosci progow dobrano tak, zeby wynik pokrywal sie z przyciskiem
"Automatycznie" w Lightroomie na zdjeciach referencyjnych z Panasonica G91.
"""

from __future__ import annotations

import cv2
import numpy as np

from .params import EditParams
from .pipeline import LUMA, apply_white_balance, camera_to_srgb
from .raw_loader import RawImage

MID_GREY = 0.18

# 90. percentyl jasnosci to punkt, ktorym celujemy w srednia szarosc.
# Srednia zbijalaby do czerni kazde zdjecie z duza ciemna plama (nocne niebo),
# a pojedyncze przepalone latarnie nie powinny decydowac o calosci kadru.
TARGET_P90 = 0.19
# najjasniejsze piksele nie moga wyjsc powyzej tego poziomu po rozjasnieniu
HIGHLIGHT_CEILING = 0.80
# ponizej tego poziomu cienie uznajemy za zalepione
SHADOW_FLOOR = 0.06
# scena o rozpietosci ponizej tylu EV nie wymaga kompresji zakresu
NEUTRAL_SPAN_EV = 4.0

ANALYSIS_SIZE = 512  # analiza na pomniejszonym obrazie - wynik ten sam, czas znikomy


def _analysis_image(raw: RawImage, params: EditParams) -> np.ndarray:
    """Maly, liniowy obraz sRGB z aktualnym balansem bieli."""
    source = raw.camera_linear
    h, w = source.shape[:2]
    scale = min(1.0, ANALYSIS_SIZE / float(max(h, w)))
    if scale < 1.0:
        source = cv2.resize(
            source,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return camera_to_srgb(apply_white_balance(source, raw, params), raw)


def _mean_saturation(img: np.ndarray) -> float:
    mx, mn = img.max(axis=2), img.min(axis=2)
    return float(np.clip((mx - mn) / np.maximum(mx, 1e-6), 0.0, 1.0).mean())


def analyse(raw: RawImage, params: EditParams | None = None) -> dict[str, float]:
    """Surowe dane o rozkladzie swiatla - przydatne przy strojeniu automatu."""
    img = _analysis_image(raw, params or EditParams())
    lum = np.maximum(img @ LUMA, 0.0).ravel()
    p02, p2, p10, p50, p90, p99, p998 = (
        float(v) for v in np.percentile(lum, [0.2, 2, 10, 50, 90, 99, 99.8])
    )
    return {
        "p02": p02, "p2": p2, "p10": p10, "p50": p50,
        "p90": p90, "p99": p99, "p998": p998,
        "span_ev": float(np.log2(max(p99, 1e-6) / max(p2, 1e-6))),
        "saturation": _mean_saturation(img),
    }


def auto_tone(raw: RawImage, params: EditParams | None = None) -> dict[str, float]:
    """Dobiera parametry tonalne i zwraca je jako slownik nazw suwakow."""
    stats = analyse(raw, params)

    # --- ekspozycja ---------------------------------------------------
    # Dwa ograniczenia naraz: chcemy trafic 90. percentylem w srednia szarosc,
    # ale nigdy kosztem wypalenia swiatel. Wybieramy slabsze z dwoch.
    ev_mid = float(np.log2(TARGET_P90 / max(stats["p90"], 1e-6)))
    ev_ceiling = float(np.log2(HIGHLIGHT_CEILING / max(stats["p998"], 1e-6)))
    exposure = min(ev_mid, ev_ceiling)
    # przyciemnianie traktujemy ostrozniej niz rozjasnianie - zdjecie lekko
    # przeswietlone latwiej uratowac suwakiem swiatel niz niedoswietlone szumem
    if exposure < 0:
        exposure *= 0.5
    exposure = float(np.clip(exposure, -2.0, 3.0))

    gain = 2.0**exposure
    span = stats["span_ev"]
    excess = max(0.0, span - NEUTRAL_SPAN_EV)

    # --- swiatla i cienie ---------------------------------------------
    # Im szerszy zakres jasnosci w scenie, tym mocniej trzeba scisnac oba konce,
    # zeby zmiescic go w zakresie monitora. Zachod slonca ma okolo 8 EV
    # rozpietosci i wymaga silnej kompresji; plaskie, pochmurne niebo prawie zadnej.
    highlights = -float(np.clip(excess * 12.0, 0.0, 85.0))

    p10_gained = stats["p10"] * gain
    shortfall_ev = float(np.log2(SHADOW_FLOOR / max(p10_gained, 1e-6)))
    shadows = float(np.clip(shortfall_ev * 12.0, 0.0, 85.0))

    # --- biele i czernie ----------------------------------------------
    # Biele dociagaja gore histogramu do krancow zakresu.
    whites = float(np.clip((0.85 - stats["p998"] * gain) / 0.85 * 30.0, -30.0, 30.0))
    # Podniesienie cieni splaszcza czern, wiec przywracamy punkt zaczepienia.
    blacks = -float(np.clip(shadows * 0.15, 0.0, 22.0))

    # --- kontrast i jaskrawosc ----------------------------------------
    contrast = float(np.clip(excess * 1.5, -10.0, 25.0))
    # Nawet zdjecie juz nasycone zyskuje na lekkim podbiciu - jaskrawosc dziala
    # najmocniej na barwy blade, wiec nie przepala tego, co i tak jest intensywne.
    vibrance = float(np.clip(29.0 - 30.0 * stats["saturation"], 0.0, 30.0))

    return {
        "exposure": round(exposure, 2),
        "contrast": round(contrast),
        "highlights": round(highlights),
        "shadows": round(shadows),
        "whites": round(whites),
        "blacks": round(blacks),
        "vibrance": round(vibrance),
    }
