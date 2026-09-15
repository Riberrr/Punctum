"""Zadania w tle.

Zasada nadrzedna: watek GUI nigdy nie dekoduje pliku i nie liczy obrazu.
Kazda operacja dluzsza niz kilka milisekund idzie do puli watkow, a wynik
wraca sygnalem. Inaczej okno zamarza przy kazdym kliknieciu.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, QRect, QRunnable, Signal

from ..core import (
    EditParams,
    RawImage,
    auto_tone,
    develop,
    develop_region,
    load_raw,
    load_thumbnail,
    read_metadata,
)
from ..core.metadata import PhotoMetadata
from ..core.pipeline import apply_noise_reduction


class _Signals(QObject):
    thumbnail_ready = Signal(int, object, object)  # indeks, obraz RGB, metadane
    raw_ready = Signal(str, object)  # sciezka, RawImage
    raw_failed = Signal(str, str)  # sciezka, komunikat
    render_ready = Signal(int, object)  # numer zlecenia, obraz RGB
    detail_ready = Signal(int, object, QRect, float)  # zlecenie, obraz, prostokat, skala
    auto_ready = Signal(str, object)  # sciezka, slownik parametrow


class ThumbnailTask(QRunnable):
    """Wyciaga podglad JPEG wbudowany w RAW - okolo 100 ms na plik."""

    def __init__(self, index: int, path: str):
        super().__init__()
        self.index, self.path = index, path
        self.signals = _Signals()

    def run(self) -> None:
        try:
            image = load_thumbnail(self.path)
            meta = read_metadata(self.path)
        except Exception:  # uszkodzony plik nie moze wywalic calej aplikacji
            image, meta = None, PhotoMetadata()
        self.signals.thumbnail_ready.emit(self.index, image, meta)


class LoadRawTask(QRunnable):
    """Pelne dekodowanie pliku - okolo 0,9 s, wiec zawsze poza watkiem GUI."""

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.signals = _Signals()

    def run(self) -> None:
        try:
            raw = load_raw(self.path)
        except Exception as exc:
            self.signals.raw_failed.emit(self.path, f"{type(exc).__name__}: {exc}")
            return
        self.signals.raw_ready.emit(self.path, raw)


class RenderTask(QRunnable):
    """Przelicza podglad dla zadanych parametrow.

    Kazde zlecenie ma numer. Jesli w miedzyczasie uzytkownik ruszyl suwakiem
    jeszcze raz, okno zignoruje przestarzaly wynik - dzieki temu podglad
    zawsze pokazuje ostatnie ustawienie, a nie to, ktore akurat sie doliczylo.
    """

    def __init__(self, job_id: int, raw: RawImage, params: EditParams, denoise: bool = True):
        super().__init__()
        self.job_id, self.raw, self.params, self.denoise = job_id, raw, params, denoise
        self.signals = _Signals()

    def run(self) -> None:
        try:
            rgb8 = develop(self.raw, self.params, denoise=self.denoise)
        except Exception:
            rgb8 = np.zeros((16, 16, 3), dtype=np.uint8)
        self.signals.render_ready.emit(self.job_id, rgb8)


class DetailRenderTask(QRunnable):
    """Liczy widoczny fragment z pelnej rozdzielczosci, od razu w skali ekranu.

    To jest to, co daje ostry obraz przy powiekszeniu 100 % i wyzej. Koszt
    zalezy od rozmiaru okna, nie od stopnia powiekszenia ani wielkosci pliku.
    """

    def __init__(
        self, job_id: int, raw: RawImage, params: EditParams, rect: QRect, scale: float
    ):
        super().__init__()
        self.job_id, self.raw, self.params = job_id, raw, params
        self.rect, self.scale = rect, scale
        self.signals = _Signals()

    def run(self) -> None:
        try:
            rgb8 = develop_region(
                self.raw,
                self.params,
                (self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()),
                scale=self.scale,
            )
        except Exception:
            return
        self.signals.detail_ready.emit(self.job_id, rgb8, self.rect, self.scale)


class NoiseReductionTask(QRunnable):
    """Doklada redukcje szumu do gotowego obrazu.

    Karta graficzna liczy caly tor tonalny, ale odszumianie zostaje na
    procesorze - non-local means nie ma sensownego odpowiednika w shaderze.
    Dlatego jest osobnym, opoznionym krokiem: podglad pojawia sie natychmiast,
    a szum znika chwile pozniej, gdy uzytkownik przestanie ruszac suwakiem.
    """

    def __init__(self, job_id: int, image: np.ndarray, params: EditParams):
        super().__init__()
        self.job_id, self.image, self.params = job_id, image, params
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = apply_noise_reduction(
                self.image,
                self.params.noise_luminance,
                self.params.noise_color,
                quality="balanced",
            )
        except Exception:
            result = self.image
        self.signals.render_ready.emit(self.job_id, result)


class AutoToneTask(QRunnable):
    """Analiza histogramu i dobor parametrow - okolo 100 ms."""

    def __init__(self, path: str, raw: RawImage, params: EditParams):
        super().__init__()
        self.path, self.raw, self.params = path, raw, params
        self.signals = _Signals()

    def run(self) -> None:
        try:
            values = auto_tone(self.raw, self.params)
        except Exception:
            values = {}
        self.signals.auto_ready.emit(self.path, values)
