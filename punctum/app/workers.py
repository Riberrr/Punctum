"""Zadania w tle.

Zasada nadrzedna: watek GUI nigdy nie dekoduje pliku i nie liczy obrazu.
Kazda operacja dluzsza niz kilka milisekund idzie do puli watkow, a wynik
wraca sygnalem. Inaczej okno zamarza przy kazdym kliknieciu.
"""

from __future__ import annotations

import os
import threading

import numpy as np
from PySide6.QtCore import QObject, QRect, QRunnable, Signal

from ..core import (
    EditParams,
    RawImage,
    auto_tone,
    default_params_for,
    develop,
    develop_region,
    load_photo,
    load_preview,
    read_metadata,
)
from ..core.metadata import PhotoMetadata
from ..core.pipeline import apply_detail


class _Signals(QObject):
    # indeks, sciezka, obraz RGB, metadane. Sciezka jest w sygnale dlatego,
    # ze lista w pasku miniatur moze sie zmienic (filtr formatow), zanim
    # miniatura dojedzie - sam indeks wskazywalby wtedy inne zdjecie.
    thumbnail_ready = Signal(int, str, object, object)
    raw_ready = Signal(str, object)  # sciezka, RawImage
    raw_failed = Signal(str, str)  # sciezka, komunikat
    render_ready = Signal(int, object)  # numer zlecenia, obraz RGB
    detail_ready = Signal(int, object, QRect, float)  # zlecenie, obraz, prostokat, skala
    auto_ready = Signal(str, object)  # sciezka, slownik parametrow
    export_progress = Signal(int, int, str)  # gotowe, wszystkich, nazwa pliku
    export_finished = Signal(int, int, object)  # zapisane, nieudane, lista bledow


class ThumbnailTask(QRunnable):
    """Miniatura do paska - z RAW-a podglad wbudowany, z JPEG-a zmniejszony plik."""

    def __init__(self, index: int, path: str):
        super().__init__()
        self.index, self.path = index, path
        self.signals = _Signals()

    def run(self) -> None:
        try:
            image = load_preview(self.path)
            meta = read_metadata(self.path)
        except Exception:  # uszkodzony plik nie moze wywalic calej aplikacji
            image, meta = None, PhotoMetadata()
        self.signals.thumbnail_ready.emit(self.index, self.path, image, meta)


class LoadRawTask(QRunnable):
    """Pelne dekodowanie pliku - okolo 0,9 s, wiec zawsze poza watkiem GUI."""

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.signals = _Signals()

    def run(self) -> None:
        try:
            raw = load_photo(self.path)
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

    def __init__(self, job_id: int, image: np.ndarray, params: EditParams,
                 scale: float = 1.0):
        super().__init__()
        self.job_id, self.image, self.params = job_id, image, params
        self.scale = scale  # skala podgladu - dla promienia wyostrzania
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = apply_detail(self.image, self.params, "balanced", scale=self.scale)
        except Exception:
            result = self.image
        try:
            self.signals.render_ready.emit(self.job_id, result)
        except RuntimeError:
            # okno zamknieto, zanim odszumianie sie skonczylo - wynik
            # nie ma juz dokad trafic, a wyjatek z watku tylko smieci w konsoli
            pass


class ExportTask(QRunnable):
    """Wsadowy eksport w tle.

    Kazde zdjecie przechodzi pelna droge: dekodowanie, tor tonalny w pelnej
    rozdzielczosci, odszumianie i zapis. Zajmuje to kilka sekund na plik,
    dlatego leci na watku roboczym, a okno dostaje postep po kazdym zdjeciu.

    Blad pojedynczego pliku nie przerywa calosci - zbieramy go na liste
    i pokazujemy dopiero na koncu. Przy eksporcie kilkudziesieciu zdjec
    zatrzymanie sie na jednym uszkodzonym pliku byloby najgorszym mozliwym
    zachowaniem.
    """

    def __init__(self, pairs, params_by_path: dict, options):
        super().__init__()
        self.pairs = list(pairs)
        self.params_by_path = dict(params_by_path)
        self.options = options
        self.signals = _Signals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def run(self) -> None:
        from ..core import load_photo, save_image
        from ..core.export import export_metadata

        total = len(self.pairs)
        saved = 0
        errors: list[str] = []

        for index, (source, target) in enumerate(self.pairs):
            if self._cancelled.is_set():
                break
            name = os.path.basename(target)
            self.signals.export_progress.emit(index, total, name)
            try:
                raw = load_photo(source)
                params = self.params_by_path.get(source) or default_params_for(source)
                rgb8 = develop(
                    raw, params, denoise=True, quality=self.options.noise_quality
                )
                fields, location = export_metadata(source, params, self.options)
                save_image(
                    rgb8, target,
                    quality=self.options.quality,
                    max_side=self.options.max_side or None,
                    location=location,
                    metadata=fields,
                )
                saved += 1
            except Exception as exc:
                errors.append(f"{os.path.basename(source)}: {type(exc).__name__} — {exc}")

        self.signals.export_progress.emit(total, total, "")
        self.signals.export_finished.emit(saved, len(errors), errors)


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
