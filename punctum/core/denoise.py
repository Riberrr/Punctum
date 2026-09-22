"""Usuwanie szumu dopasowane do zmierzonego szumu zdjecia.

Suwaki nie ustawiaja bezwzglednej sily filtra, tylko sile WZGLEDEM szumu,
ktory mierzymy na samym obrazie. Dzieki temu "50" dziala podobnie przy
ISO 400 i ISO 6400, w cieniach i w swiatlach, dla RAW-a i JPEG-a.

Tor:
1. Pomiar sigma(jasnosc) filtrem Immerkaera.
2. Przeksztalcenie wyrownujace szum (VST): f(v) = calka 1/sigma(v). Po nim
   szum ma to samo sigma w kazdej tonacji, wiec jeden prog filtra dziala
   jednakowo w cieniach i w swiatlach. Bez tego filtr dobrany do cieni
   rozmywal swiatla, a dobrany do swiatel zostawial szum w cieniach.
3. Jasnosc: non-local means na danych po VST, czesc oryginalu z powrotem
   (drobne ziarno wyglada naturalniej niz plastik) i lekkie odzyskanie konturu.
4. Kolor: falki a trous na kilku skalach, w polowie rozdzielczosci.

Kalibracja (zdjecie ISO 6400, porownanie z eksportami Lightrooma): suwak
jasnosci 50 daje szum resztkowy jak Lightroom 50, a kolor 25 usuwa barwne
iskry w stopniu podobnym do jego domyslnego 25.
"""

from __future__ import annotations

import cv2
import numpy as np

# Filtr Immerkaera: zerowa odpowiedz na plaskie tlo i liniowe gradienty,
# zostaje sam szum. Norma L2 jadra wynosi 6.
_IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
_B3 = np.array([1, 4, 6, 4, 1], np.float32) / 16.0
_MIN_SAMPLES = 2000

# (template, search) non-local means dla poziomow jakosci. Po VST szum jest
# rowny w calym obrazie, wiec male okno przeszukiwania wystarcza - 7/21
# z dawnego toru kosztowalo trzy razy wiecej bez widocznej roznicy.
NLM_WINDOWS = {"fast": (3, 7), "balanced": (5, 11), "high": (5, 13)}


def noise_sigma(y: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Sigma szumu luminancji (skala 0..255) w przedzialach jasnosci.

    Srednia |odpowiedzi| z odcietymi 10 % najwiekszych wartosci: krawedzie
    daja duze odpowiedzi, ale jest ich malo. Srednia z |N(0,s)| to
    s*sqrt(2/pi), a odciecie zaniza ja o ok. 16 % - stala poprawka.
    Przedzialy z za mala liczba pikseli zwracaja NaN.
    """
    yf = y.astype(np.float32)
    r = np.abs(cv2.filter2D(yf, -1, _IMMERKAER))
    mean = cv2.blur(yf, (7, 7))
    # na duzym obrazie wystarczy co trzeci piksel w kazdym kierunku -
    # sortowanie 20 mln wartosci kosztowalo 1,5 s, probka daje ten sam wynik
    if y.size > 4_000_000:
        r, mean = r[::3, ::3], mean[::3, ::3]
    idx = np.clip(np.searchsorted(edges, mean, side="right") - 1, 0, len(edges) - 2)
    out = np.full(len(edges) - 1, np.nan)
    flat_idx, flat_r = idx.ravel(), r.ravel()
    order = np.argsort(flat_idx, kind="stable")
    bounds = np.searchsorted(flat_idx[order], np.arange(len(edges)))
    for i in range(len(edges) - 1):
        v = flat_r[order[bounds[i] : bounds[i + 1]]]
        if v.size < _MIN_SAMPLES:
            continue
        v = v[v <= np.percentile(v, 90)]
        out[i] = float(v.mean()) * np.sqrt(np.pi / 2) / 6.0 / 0.84
    return out


def vst_curve(y: np.ndarray) -> np.ndarray:
    """Tablica f[0..255] wyrownujaca szum; po niej sigma szumu ~ 1."""
    edges = np.arange(0, 264, 8)
    s = noise_sigma(y, edges)
    ok = np.isfinite(s)
    if not ok.any():  # male wycinki: jedna sigma dla calego obrazu
        s = noise_sigma(y, np.array([0, 256]))
        ok = np.isfinite(s)
        if not ok.any():
            return np.arange(256, dtype=np.float32)
        s = np.full(256, s[0])
    else:
        centres = (edges[:-1] + edges[1:]) / 2.0
        s = np.interp(np.arange(256), centres[ok], s[ok])
    # dolne ograniczenie: w przepalonych i czarnych obszarach pomiar daje
    # prawie zero, a 1/sigma rozciagnalby je w nieskonczonosc
    s = np.maximum(s, max(0.25, 0.15 * float(np.median(s))))
    return np.concatenate([[0.0], np.cumsum(1.0 / s)[:-1]]).astype(np.float32)


def _atrous_kernel(level: int) -> np.ndarray:
    step = 2**level
    k = np.zeros(4 * step + 1, np.float32)
    k[::step] = _B3
    return k


def _chroma_shrink(c: np.ndarray, strength: float, levels: int = 5) -> np.ndarray:
    """Falki a trous z lagodnym tlumieniem kazdej skali.

    Szum koloru siega wielu skal (drobne iskry i wieksze plamy), wiec tlumimy
    wszystkie rowno. Prog to wielokrotnosc mediany lokalnej energii danej
    skali: szum wypelnia caly obraz, a prawdziwe przejscia barwne sa rzadkie
    i silne, wiec przezywaja. Tlumienie d*d^2/(d^2+t^2) zamiast twardego
    progu - brak skokow, ktore daja "robaczki".
    """
    base = c
    out = np.zeros_like(c)
    for j in range(levels):
        k = _atrous_kernel(j)
        smooth = cv2.sepFilter2D(base, cv2.CV_32F, k, k, borderType=cv2.BORDER_REFLECT)
        d = base - smooth
        d2 = d * d
        # blur w float32 potrafi zejsc minimalnie ponizej zera
        rms = np.sqrt(np.maximum(cv2.blur(d2, (9, 9)), 0.0))
        t = strength * float(np.median(rms[::4, ::4]))
        out += d * d2 / (d2 + t * t + 1e-12)
        base = smooth
    return out + base


def _denoise_color(ycc: np.ndarray, strength: float) -> None:
    """Kolor liczymy w polowie rozdzielczosci (tak jak JPEG 4:2:0 i tak go
    zapisuje) - czterokrotnie taniej, a roznicy nie widac."""
    h, w = ycc.shape[:2]
    small = cv2.resize(ycc[..., 1:], (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
    for ch in (0, 1):
        small[..., ch] = np.clip(
            _chroma_shrink(small[..., ch].astype(np.float32), strength) + 0.5, 0, 255
        ).astype(np.uint8)
    ycc[..., 1:] = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _denoise_luma(y: np.ndarray, t: float, quality: str) -> np.ndarray:
    """t = suwak/100. Zwraca nowa luminancje uint8."""
    f = vst_curve(y)
    span = float(f[-1])
    if span < 1.0:
        return y
    # NLM pracuje na uint8: skalujemy VST tak, by wypelnil zakres 0..250.
    # Sigma szumu w tych jednostkach wynosi wtedy `scale`.
    scale = 250.0 / span
    z = f[y]
    zu = np.clip(z * scale + 0.5, 0, 255).astype(np.uint8)
    template, search = NLM_WINDOWS.get(quality, NLM_WINDOWS["high"])
    # h w wielokrotnosciach sigma: 50 -> 2 sigma. NLM dziala progowo (ponizej
    # ~1 sigma prawie nic nie robi), dlatego slabe ustawienia uzyskujemy
    # mieszaniem, a nie samym zmniejszaniem h.
    h = (1.0 + 2.0 * t) * scale
    zd = cv2.fastNlMeansDenoising(zu, None, h, template, search).astype(np.float32) / scale
    yd = np.interp(zd, f, np.arange(256, dtype=np.float32)).astype(np.float32)
    # Szum TLUMIMY, nie wygladzamy: czesc oryginalu wraca jako drobne ziarno
    # (30 -> ok. 30 %, 50 -> 15 %, od 70 nic). Porownanie z eksportami
    # Lightrooma pokazalo, ze przy 30-40 zostawia on wyrazne ziarno i wlasnie
    # to uzytkownik uznal za dobre; pelne wygladzenie dawalo efekt wosku.
    # Kontur odzyskuje wyostrzanie (sharpen.py), liczone zaraz potem.
    weight = min(1.0, t * 4.0) * min(1.0, 0.45 + 0.8 * t)
    yf = y.astype(np.float32)
    return np.clip(yf + weight * (yd - yf) + 0.5, 0, 255).astype(np.uint8)


def apply_detail(rgb8: np.ndarray, p, quality: str = "high", scale: float = 1.0) -> np.ndarray:
    """Caly przebieg na procesorze: usuwanie szumu, potem wyostrzanie.

    Kolejnosc ma znaczenie - wyostrzony szum jest wiekszy i trudniejszy do
    usuniecia. `scale` to skala obrazu wzgledem pelnej rozdzielczosci
    (podglad pomniejszony), potrzebna, by promien wyostrzania znaczyl to samo.
    """
    from .sharpen import sharpen

    rgb8 = apply_noise_reduction(rgb8, p.noise_luminance, p.noise_color, quality)
    return sharpen(rgb8, p.sharpen_amount, p.sharpen_radius, p.sharpen_detail,
                   p.sharpen_masking, scale)


def apply_noise_reduction(
    rgb8: np.ndarray, luminance: float, color: float, quality: str = "high"
) -> np.ndarray:
    """Usuwanie szumu jasnosci i koloru, suwaki 0..100.

    WAZNE: wywolywac wylacznie na obrazie w rozdzielczosci NATYWNEJ albo
    pomniejszonym - nigdy po powiekszeniu, bo ziarno rozciagniete ponad
    zasieg filtrow przestaje byc widoczne dla pomiaru. Na obrazie
    pomniejszonym pomiar sam wykrywa mniejszy szum i filtr slabnie.

    Poziomy jakosci roznia sie tylko oknem NLM: "fast" na podglad
    dopasowany do okna, "balanced" na wycinek przy powiekszeniu, "high"
    przy eksporcie.
    """
    t_lum = max(0.0, min(100.0, luminance)) / 100.0
    t_col = max(0.0, min(100.0, color)) / 100.0
    if t_lum < 0.005 and t_col < 0.005:
        return rgb8
    ycc = cv2.cvtColor(rgb8, cv2.COLOR_RGB2YCrCb)
    if t_col >= 0.005:
        _denoise_color(ycc, t_col * 16.0)  # 25 -> prog 4x mediana energii skali
    if t_lum >= 0.005:
        ycc[..., 0] = _denoise_luma(ycc[..., 0], t_lum, quality)
    return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)
