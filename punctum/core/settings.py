"""Ustawienia aplikacji: wartosci domyslne, zapis i odczyt.

Plik trafia do katalogu konfiguracyjnego uzytkownika, nie do katalogu
programu - dzieki temu przetrwa aktualizacje i nie wymaga praw do zapisu
w Program Files.

Odczyt jest celowo pobłazliwy. Uszkodzony albo niepelny plik ustawien nie
moze zablokowac uruchomienia programu: nieznane klucze pomijamy, brakujace
uzupelniamy wartoscia domyslna, a wartosci spoza dopuszczalnego zakresu
przycinamy.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, field, fields
from typing import Any

APP_NAME = "Punctum"

ENGINE_AUTO = "auto"
ENGINE_GPU = "gpu"
ENGINE_CPU = "cpu"
ENGINE_LABELS = {
    ENGINE_AUTO: "Automatycznie",
    ENGINE_GPU: "Karta graficzna",
    ENGINE_CPU: "Procesor",
}

PREVIEW_SIZES = (1200, 1600, 2048, 2560, 3200)
NOISE_QUALITY_LABELS = {
    "fast": "Szybka (filtr bilateralny)",
    "balanced": "Zrównoważona (non-local means 5/11)",
    "high": "Dokładna (non-local means 7/21)",
}


def config_directory() -> str:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP_NAME)


def settings_path() -> str:
    return os.path.join(config_directory(), "settings.json")


@dataclass
class Settings:
    # --- wydajnosc ------------------------------------------------------
    render_engine: str = ENGINE_AUTO
    preview_size: int = 1600
    thumbnail_threads: int = 0  # 0 = dobierz automatycznie

    # --- podglad --------------------------------------------------------
    detail_delay_ms: int = 160
    noise_delay_ms: int = 260
    preview_noise_quality: str = "balanced"
    pixel_peek_zoom: float = 2.5  # powyzej tego skalujemy najblizszym sasiadem
    show_navigator: bool = True

    # --- kolko myszy ----------------------------------------------------
    # Po przewinieciu listy suwaki przez ten czas nie reaguja na kolko,
    # zeby przewijanie panelu nie zmienialo przypadkiem parametrow zdjecia.
    wheel_lockout_ms: int = 400
    # Kursor musi postac nad suwakiem tyle czasu, zanim kolko zacznie dzialac.
    wheel_dwell_ms: int = 220

    # --- eksport --------------------------------------------------------
    export_format: str = ".jpg"
    export_quality: int = 92
    export_max_side: int = 0  # 0 = pelna rozdzielczosc
    export_noise_quality: str = "high"
    export_folder: str = ""

    # --- ogolne ---------------------------------------------------------
    reopen_last_folder: bool = True
    last_folder: str = ""

    # ---------------------------------------------------------- walidacja

    def normalised(self) -> "Settings":
        """Przycina wartosci do dopuszczalnych zakresow."""
        clean = Settings(**asdict(self))
        if clean.render_engine not in ENGINE_LABELS:
            clean.render_engine = ENGINE_AUTO
        clean.preview_size = min(PREVIEW_SIZES, key=lambda s: abs(s - clean.preview_size))
        clean.thumbnail_threads = max(0, min(32, int(clean.thumbnail_threads)))
        clean.detail_delay_ms = max(0, min(2000, int(clean.detail_delay_ms)))
        clean.noise_delay_ms = max(0, min(5000, int(clean.noise_delay_ms)))
        if clean.preview_noise_quality not in NOISE_QUALITY_LABELS:
            clean.preview_noise_quality = "balanced"
        if clean.export_noise_quality not in NOISE_QUALITY_LABELS:
            clean.export_noise_quality = "high"
        clean.pixel_peek_zoom = float(min(16.0, max(1.0, clean.pixel_peek_zoom)))
        clean.wheel_lockout_ms = max(0, min(3000, int(clean.wheel_lockout_ms)))
        clean.wheel_dwell_ms = max(0, min(3000, int(clean.wheel_dwell_ms)))
        clean.export_quality = max(50, min(100, int(clean.export_quality)))
        clean.export_max_side = max(0, min(20000, int(clean.export_max_side)))
        if clean.export_format not in (".jpg", ".png", ".tif"):
            clean.export_format = ".jpg"
        return clean

    # -------------------------------------------------------- zapis/odczyt

    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        target = path or settings_path()
        try:
            with open(target, encoding="utf-8") as handle:
                data: dict[str, Any] = json.load(handle)
        except (OSError, ValueError):
            return cls()  # brak pliku albo uszkodzony - startujemy na domyslnych

        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known}).normalised()

    def save(self, path: str | None = None) -> bool:
        target = path or settings_path()
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            # zapis przez plik tymczasowy: przerwany zapis nie zostawia
            # polowicznego pliku, ktory przy nastepnym starcie bylby uszkodzony
            temporary = target + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(asdict(self.normalised()), handle, indent=2, ensure_ascii=False)
            os.replace(temporary, target)
            return True
        except OSError:
            return False

    def copy(self) -> "Settings":
        return Settings(**asdict(self))
