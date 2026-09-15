"""Wczytywanie plikow RAW i przygotowanie ich do edycji.

Zalozenie architektoniczne: plik dekodujemy DOKLADNIE RAZ, a wynik
trzymamy w pamieci jako liniowy float32 w przestrzeni aparatu. Kazdy
ruch suwaka operuje juz tylko na tej tablicy - dzieki temu podglad
odpowiada natychmiast, zamiast czekac sekunde na ponowne dekodowanie.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
import rawpy

from . import whitebalance as wb


@dataclass
class RawImage:
    path: str
    # liniowy float32 HxWx3 w przestrzeni aparatu, z balansem bieli "jak na ujeciu"
    camera_linear: np.ndarray = field(repr=False)
    cam_xyz: np.ndarray = field(repr=False)
    cam_to_srgb: np.ndarray = field(repr=False)
    as_shot_temp: float = 5500.0
    as_shot_tint: float = 0.0
    as_shot_mult: np.ndarray = field(default_factory=lambda: np.ones(3), repr=False)
    raw_width: int = 0
    raw_height: int = 0

    _oriented_cache: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def shape(self) -> tuple[int, int]:
        return self.camera_linear.shape[0], self.camera_linear.shape[1]

    def oriented(self, orientation: int) -> np.ndarray:
        """Obraz obrocony o wielokrotnosc 90 stopni, z pamiecia podreczna.

        Obrot 20-megapikselowej tablicy float32 kosztuje kilkaset milisekund
        i 240 MB kopii, a przy przesuwaniu powiekszonego kadru siegamy po
        niego kilkadziesiat razy na sekunde - dlatego wynik trzymamy.
        """
        steps = int(round(orientation / 90.0)) % 4
        if steps == 0:
            return self.camera_linear
        cached = self._oriented_cache.get(steps)
        if cached is None:
            cached = np.ascontiguousarray(np.rot90(self.camera_linear, k=-steps))
            self._oriented_cache.clear()  # trzymamy tylko jedna orientacje
            self._oriented_cache[steps] = cached
        return cached

    def proxy(self, max_side: int = 2048) -> "RawImage":
        """Pomniejszona kopia do pracy na podgladzie."""
        import cv2

        h, w = self.shape
        scale = min(1.0, max_side / float(max(h, w)))
        if scale >= 1.0:
            return self
        small = cv2.resize(
            self.camera_linear,
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            interpolation=cv2.INTER_AREA,
        )
        return RawImage(
            path=self.path,
            camera_linear=np.ascontiguousarray(small),
            cam_xyz=self.cam_xyz,
            cam_to_srgb=self.cam_to_srgb,
            as_shot_temp=self.as_shot_temp,
            as_shot_tint=self.as_shot_tint,
            as_shot_mult=self.as_shot_mult,
            raw_width=self.raw_width,
            raw_height=self.raw_height,
        )


def load_raw(path: str, half_size: bool = False) -> RawImage:
    """Dekoduje plik RAW do liniowej przestrzeni aparatu.

    Demozaikowanie i rekonstrukcje swiatel zostawiamy LibRaw - jest w tym
    dobry i sprawdzony. Przejmujemy kontrole dopiero od momentu, gdy mamy
    liniowe RGB: konwersje barw i caly tor tonalny liczymy sami.
    """
    with rawpy.imread(path) as raw:
        cam_xyz = np.asarray(raw.rgb_xyz_matrix, dtype=np.float64)
        cam_wb = np.asarray(raw.camera_whitebalance, dtype=np.float64)
        raw_w, raw_h = raw.sizes.width, raw.sizes.height

        rgb16 = raw.postprocess(
            output_color=rawpy.ColorSpace.raw,  # zostajemy w przestrzeni aparatu
            use_camera_wb=True,  # WB przed demozaikowaniem = poprawne swiatla
            no_auto_bright=True,  # zadnego automatu, chcemy powtarzalnosci
            gamma=(1.0, 1.0),  # dane maja zostac liniowe
            output_bps=16,
            half_size=half_size,
            highlight_mode=rawpy.HighlightMode.Clip,
            user_flip=-1,  # respektuj orientacje z EXIF
        )

    camera_linear = (rgb16.astype(np.float32) / 65535.0).astype(np.float32)
    temp, tint = wb.estimate_temp_tint(cam_xyz, cam_wb)

    return RawImage(
        path=path,
        camera_linear=camera_linear,
        cam_xyz=cam_xyz,
        cam_to_srgb=wb.camera_to_srgb_matrix(cam_xyz),
        as_shot_temp=float(temp),
        as_shot_tint=float(tint),
        as_shot_mult=wb.camera_multipliers(cam_xyz, temp, tint),
        raw_width=raw_w,
        raw_height=raw_h,
    )


def load_thumbnail(path: str) -> np.ndarray | None:
    """Wyciaga podglad JPEG wbudowany w plik RAW.

    To jest sztuczka, dzieki ktorej siatka miniatur pojawia sie od razu:
    kazdy RW2 ma w srodku gotowy podglad, wiec nie trzeba dekodowac
    kilkudziesieciu plikow po 20 Mpix, zeby cokolwiek pokazac.
    """
    import cv2

    try:
        with rawpy.imread(path) as raw:
            thumb = raw.extract_thumb()
    except (rawpy.LibRawError, OSError):
        return None

    if thumb.format == rawpy.ThumbFormat.JPEG:
        buf = np.frombuffer(thumb.data, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        return None if img is None else cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    if thumb.format == rawpy.ThumbFormat.BITMAP:
        return np.asarray(thumb.data)
    return None
