"""Parametry edycji zdjecia.

Cala edycja jest nieniszczaca: ten obiekt to komplet nastaw, ktore
opisuja, jak z surowego pliku RAW powstaje obraz wyjsciowy.
Zakresy suwakow celowo naslaguja Lightrooma, zeby przenoszenie
ustawien miedzy programami bylo intuicyjne.
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

    # --- redukcja szumu -------------------------------------------------
    noise_luminance: float = 0.0  # 0 .. 100
    noise_color: float = 25.0  # 0 .. 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditParams":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        if "crop" in clean and clean["crop"] is not None:
            clean["crop"] = tuple(clean["crop"])
        return cls(**clean)

    def is_default(self) -> bool:
        return self == EditParams()
