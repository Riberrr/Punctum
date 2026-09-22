"""Parametry edycji zdjecia.

Cala edycja jest nieniszczaca: ten obiekt to komplet nastaw, ktore
opisuja, jak z surowego pliku RAW powstaje obraz wyjsciowy.
Zakresy suwakow sa takie, jakie w programach do obrobki RAW sa przyjete
(-100..+100, ekspozycja w dzialkach EV) - fotograf nie musi uczyc sie ich
od nowa.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


@dataclass
class EditParams:
    # --- balans bieli ---------------------------------------------------
    # temperature w kelwinach; None = "jak na ujeciu" (nastawa z aparatu)
    temperature: float | None = None
    tint: float = 0.0  # -150 .. +150, zielony <-> magenta

    # --- odcien ---------------------------------------------------------
    exposure: float = 0.0  # w dzialkach EV, -5 .. +5
    contrast: float = 0.0  # -100 .. +100
    highlights: float = 0.0  # -100 .. +100
    shadows: float = 0.0  # -100 .. +100
    whites: float = 0.0  # -100 .. +100
    blacks: float = 0.0  # -100 .. +100

    # --- obecnosc -------------------------------------------------------
    vibrance: float = 0.0  # -100 .. +100
    saturation: float = 0.0  # -100 .. +100

    # --- geometria ------------------------------------------------------
    # obrot o wielokrotnosc 90 stopni (0, 90, 180, 270) - zmiana orientacji
    orientation: int = 0
    rotation: float = 0.0  # plynny obrot w stopniach, -45 .. +45
    # kadr jako ulamki szerokosci/wysokosci: (left, top, right, bottom)
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

    # --- wyostrzanie ---------------------------------------------------
    # Domyslne jak dla RAW (JPEG jest juz wyostrzony w aparacie i dostaje
    # 0 - patrz default_params_for). Liczone na procesorze razem z szumem.
    sharpen_amount: float = 40.0  # 0 .. 150
    sharpen_radius: float = 1.0  # 0.5 .. 3.0 px
    sharpen_detail: float = 25.0  # 0 .. 100
    sharpen_masking: float = 0.0  # 0 .. 100

    # --- redukcja szumu -------------------------------------------------
    noise_luminance: float = 0.0  # 0 .. 100
    noise_color: float = 25.0  # 0 .. 100

    # --- lokalizacja ----------------------------------------------------
    # Wspolrzedne nadane na mapie. Nie sa parametrem obrazu, ale dziela z nim
    # los: leza w tym samym sidecarze i tak samo nie ruszaja pliku zrodlowego.
    # Do metadanych trafiaja dopiero w pliku wynikowym, przy eksporcie.
    latitude: float | None = None
    longitude: float | None = None

    # --- metadane ------------------------------------------------------
    # Zmienione pola EXIF, po naszych nazwach (patrz core/exif_edit.py).
    # Trzymamy je TUTAJ, a nie osobno, zeby jechaly ta sama droga co reszta:
    # pamiec per zdjecie, sidecar, eksport. Kazdy osobny schowek predzej czy
    # pozniej rozjechalby sie z nastawami.
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def has_metadata(self) -> bool:
        return any(str(value).strip() for value in self.metadata.values())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditParams":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        if "crop" in clean and clean["crop"] is not None:
            clean["crop"] = tuple(clean["crop"])
        return cls(**clean)

    def is_default(self, jpeg: bool = False) -> bool:
        return self == default_params(jpeg)

    def needs_detail_pass(self, scale: float = 1.0) -> bool:
        """Czy obraz w skali `scale` wymaga przebiegu na procesorze.

        Shader nie odszumia ani nie wyostrza, wiec kazde miejsce pokazujace
        obraz musi wtedy isc torem CPU - inaczej efekt znika po dorysowaniu
        fragmentu. Wyostrzanie liczy sie dopiero, gdy promien w pikselach
        obrazu przekracza SHARPEN_MIN_RADIUS: na podgladzie dopasowanym do
        okna i tak nie byloby go widac, a przebieg CPU po kazdym ruchu
        suwaka dawalby tylko mrugniecie.
        """
        if self.noise_luminance > 0.5 or self.noise_color > 0.5:
            return True
        return self.sharpen_amount > 0.5 and self.sharpen_radius * scale >= SHARPEN_MIN_RADIUS


SHARPEN_MIN_RADIUS = 0.5  # px obrazu wyswietlanego; ponizej wyostrzanie pomijamy


def default_params(jpeg: bool = False) -> EditParams:
    """Nastawy wyjsciowe nowego zdjecia. JPEG byl juz wyostrzony w aparacie -
    drugie domyslne wyostrzanie dawaloby przeostrzone krawedzie."""
    return EditParams(sharpen_amount=0.0) if jpeg else EditParams()
