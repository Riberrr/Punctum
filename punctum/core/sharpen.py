"""Wyostrzanie: maska wyostrzajaca na luminancji z ograniczeniem aureoli.

Cztery suwaki w znaczeniu przyjetym w programach do obrobki RAW:
- ilosc (0..150): sila wzmocnienia krawedzi,
- promien (0,5..3 px): jak szerokie przejscia sa wzmacniane,
- szczegoly (0..100): nisko - tlumienie aureoli przy mocnych krawedziach,
  wysoko - wzmacniane jest takze drobne ziarno i faktura,
- maskowanie (0..100): 0 - wyostrzany caly obraz, wyzej - tylko krawedzie,
  gladkie powierzchnie (niebo, skora) zostaja nietkniete.

Tylko luminancja: wyostrzanie kanalow barwnych daje kolorowe obwodki.
Kalibracja domyslnych wartosci (40 / 1,0 / 25 / 0): energia krawedzi zdjecia
testowego zbliza sie do eksportu z Lightrooma przy jego domyslnym
wyostrzaniu RAW, z lekkim zapasem na korzysc detalu (zyczenie uzytkownika).
"""

from __future__ import annotations

import cv2
import numpy as np

from .params import SHARPEN_MIN_RADIUS

# Wzmocnienie maski przy ilosci 100. Dobrane pomiarem, patrz docstring.
GAIN_AT_100 = 1.9


def sharpen(
    rgb8: np.ndarray,
    amount: float,
    radius: float = 1.0,
    detail: float = 25.0,
    masking: float = 0.0,
    scale: float = 1.0,
) -> np.ndarray:
    """`scale` to skala obrazu wzgledem pelnej rozdzielczosci.

    Promien podajemy w pikselach zdjecia. Na podgladzie pomniejszonym do
    40 % ten sam promien to 0,4 piksela ekranu - wyostrzanie liczone
    z pelnym promieniem dawaloby na podgladzie grube aureole, ktorych
    w eksporcie nie ma.
    """
    if amount < 0.5:
        return rgb8
    r = float(radius) * float(scale)
    if r < SHARPEN_MIN_RADIUS:
        return rgb8  # ten sam prog co w EditParams.needs_detail_pass
    ycc = cv2.cvtColor(rgb8, cv2.COLOR_RGB2YCrCb)
    y = ycc[..., 0].astype(np.float32)
    high = y - cv2.GaussianBlur(y, (0, 0), r)
    # Szczegoly: miekkie ograniczenie amplitudy. Mocna krawedz ma duza
    # odpowiedz i to ona daje aureole - tanh ja scina, a drobna faktura
    # (mala amplituda) przechodzi prawie bez zmian.
    limit = 3.0 + 0.5 * float(detail)
    high = limit * np.tanh(high / limit)
    gain = GAIN_AT_100 * float(amount) / 100.0
    if masking > 0.5:
        smooth = cv2.GaussianBlur(y, (0, 0), 1.5 * max(scale, 0.5))
        gx = cv2.Sobel(smooth, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(smooth, cv2.CV_32F, 0, 1, ksize=3)
        edge = cv2.magnitude(gx, gy)
        low = 0.25 * float(masking)
        mask = np.clip((edge - low) / (4.0 + 0.1 * float(masking)), 0.0, 1.0)
        high *= mask
    ycc[..., 0] = np.clip(y + gain * high + 0.5, 0, 255).astype(np.uint8)
    return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)
