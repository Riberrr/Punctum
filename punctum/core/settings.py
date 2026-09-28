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
from ..przeklad import N_, jezyki

APP_NAME = "Punctum"

ENGINE_AUTO = "auto"
ENGINE_GPU = "gpu"
ENGINE_CPU = "cpu"
ENGINE_LABELS = {
    ENGINE_AUTO: N_("Automatycznie"),
    ENGINE_GPU: N_("Karta graficzna"),
    ENGINE_CPU: N_("Procesor"),
}

PREVIEW_SIZES = (1200, 1600, 2048, 2560, 3200)

# Granice rozmiarow przeciaganych mysza, w pikselach.
LAYOUT_LIMITS = {
    "left_panel_width": (220, 420),
    "right_panel_width": (290, 480),
    "filmstrip_height": (90, 260),
}

NOISE_QUALITY_LABELS = {
    "fast": N_("Szybka (non-local means 3/7)"),
    "balanced": N_("Zrównoważona (non-local means 5/11)"),
    "high": N_("Dokładna (non-local means 5/13)"),
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


# Zakres skali interfejsu. Ponizej 75 % napisy sa nieczytelne, a powyzej
# 200 % okno na zwyklym monitorze przestaje miescic panele.
UI_SCALE_MIN = 0.75
UI_SCALE_MAX = 2.0


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
    # Dymki z objasnieniami. Wylaczalne, bo komus, kto zna program na
    # pamiec, wyskakujace okienka zaslaniaja suwaki.
    show_tooltips: bool = True
    tooltip_delay_ms: int = 700  # tyle co domyslnie w Qt

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
    export_use_subfolder: bool = False
    export_subfolder: str = N_("Eksport")  # patrz ExportOptions.subfolder
    export_naming: str = "original"  # original | custom
    export_custom_name: str = ""
    export_start_number: int = 1
    export_number_digits: int = 3
    export_on_existing: str = "ask"  # ask | overwrite | skip | unique
    # Autor i prawa autorskie: wartosci domyslne dla okna eksportu. Okno
    # pozwala je zmienic na jeden eksport, ale nie nadpisuje ich tutaj -
    # jednorazowa poprawka nie powinna zmieniac podpisu wszystkich kolejnych.
    # Pamietamy za to, czy pola byly zaznaczone.
    export_author: str = ""
    export_copyright: str = ""
    export_add_author: bool = False
    export_add_copyright: bool = False
    # Znak wodny (punkt 11): wzor jako slownik z ZnakWodny.do_dict - modul
    # ustawien nie importuje Pillow przy starcie - i czy byl wlaczony.
    export_add_watermark: bool = False
    export_watermark: dict = field(default_factory=dict)

    # --- ogolne ---------------------------------------------------------
    # Kod jezyka interfejsu (pl, en...). Pusty = jeszcze nie wybrany: przy
    # starcie bierzemy jezyk systemu, o ile mamy dla niego plik przekladu.
    language: str = ""
    # Skala napisow, przyciskow i paneli (1.0 = jak system). Dziala przez
    # QT_SCALE_FACTOR, ktory Qt czyta tylko przy starcie - stad zmiana po
    # ponownym uruchomieniu.
    ui_scale: float = 1.0
    reopen_last_folder: bool = True
    last_folder: str = ""
    # Zapis korekt obok zdjec (sidecar XMP). Dzieki temu obrobke 2000 zdjec
    # mozna rozlozyc na kilka dni - zamkniecie programu nie gubi pracy.
    store_edits: bool = True
    recent_folders: list[str] = field(default_factory=list)
    recent_folders_limit: int = 10
    # Ktore formaty pokazywac w pasku miniatur: all | raw | jpeg.
    # Wartosci sa te same, co stale FORMAT_* w core/loader.py; trzymamy tu
    # goly napis, zeby modul ustawien nie zalezal od dekodowania zdjec.
    format_filter: str = "all"

    # --- sterowanie przez AI (punkt 6, MCP) -------------------------------
    # Serwer slucha tylko na 127.0.0.1 i wymaga tokenu (mcp.json obok
    # ustawien). Port staly, bo klienci HTTP maja go wpisanego na sztywno.
    mcp_enabled: bool = True
    mcp_port: int = 47823

    # --- uklad okna -----------------------------------------------------
    # Rozmiary ustawiane przeciaganiem krawedzi. Zakresy (LAYOUT_LIMITS)
    # pilnuja, zeby zle zapisana wartosc nie zostawila panelu, w ktorym
    # nie miesci sie zaden przycisk.
    left_panel_width: int = 260
    right_panel_width: int = 340
    filmstrip_height: int = 150
    # Uklad sekcji w panelach (punkt 23): miejsca (z schowkiem), kolejnosc,
    # zwiniete, blokada. Sprawdza go app/panele.py - tu tylko pilnujemy typu.
    panel_layout: dict = field(default_factory=dict)

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
        clean.tooltip_delay_ms = max(0, min(5000, int(clean.tooltip_delay_ms)))
        clean.ui_scale = round(float(min(UI_SCALE_MAX, max(UI_SCALE_MIN, float(clean.ui_scale)))), 2)
        if clean.language not in jezyki():
            clean.language = ""  # plik jezyka zniknal - wybierzemy od nowa przy starcie
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
        if clean.export_naming not in ("original", "custom"):
            clean.export_naming = "original"
        if clean.export_on_existing not in ("ask", "overwrite", "skip", "unique"):
            clean.export_on_existing = "ask"
        clean.export_author = str(clean.export_author or "").strip()
        clean.export_copyright = str(clean.export_copyright or "").strip()
        clean.export_add_author = bool(clean.export_add_author)
        clean.export_add_copyright = bool(clean.export_add_copyright)
        clean.export_add_watermark = bool(clean.export_add_watermark)
        from .znak_wodny import ZnakWodny

        clean.export_watermark = ZnakWodny.z_dict(clean.export_watermark).do_dict()
        if clean.format_filter not in ("all", "raw", "jpeg"):
            clean.format_filter = "all"
        clean.recent_folders_limit = max(0, min(50, int(clean.recent_folders_limit)))
        seen: set[str] = set()
        unique: list[str] = []
        for folder in clean.recent_folders:
            if isinstance(folder, str) and folder and folder.lower() not in seen:
                seen.add(folder.lower())
                unique.append(folder)
        clean.recent_folders = unique[: clean.recent_folders_limit]
        clean.export_start_number = max(0, min(999999, int(clean.export_start_number)))
        clean.export_number_digits = max(1, min(8, int(clean.export_number_digits)))
        if not isinstance(clean.panel_layout, dict):
            clean.panel_layout = {}
        for name, (low, high) in LAYOUT_LIMITS.items():
            setattr(clean, name, max(low, min(high, int(getattr(clean, name)))))
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

    def remember_folder(self, folder: str) -> None:
        """Wstawia katalog na poczatek historii, bez powtorzen."""
        if not folder:
            return
        others = [f for f in self.recent_folders if f.lower() != folder.lower()]
        self.recent_folders = [folder, *others][: max(1, self.recent_folders_limit)]
