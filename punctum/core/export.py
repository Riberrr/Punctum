"""Zapis gotowego obrazu do pliku oraz planowanie eksportu."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .exif_edit import exif_bytes, layer_metadata, source_metadata
from .metadata import PhotoMetadata

# co zrobic, gdy plik o danej nazwie juz istnieje
ON_EXISTING_ASK = "ask"
ON_EXISTING_OVERWRITE = "overwrite"
ON_EXISTING_SKIP = "skip"
ON_EXISTING_UNIQUE = "unique"

EXISTING_LABELS = {
    ON_EXISTING_ASK: "Zapytaj, co robić",
    ON_EXISTING_OVERWRITE: "Zastąp istniejący plik",
    ON_EXISTING_SKIP: "Pomiń to zdjęcie",
    ON_EXISTING_UNIQUE: "Wybierz nową nazwę",
}

NAMING_ORIGINAL = "original"
NAMING_CUSTOM = "custom"

FORMAT_LABELS = {".jpg": "JPEG", ".png": "PNG", ".tif": "TIFF"}


def save_image(
    rgb8: np.ndarray,
    out_path: str,
    quality: int = 92,
    max_side: int | None = None,
    meta: PhotoMetadata | None = None,
    location: tuple[float, float] | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    """Zapisuje obraz RGB uint8 jako JPEG, PNG lub TIFF (wg rozszerzenia)."""
    img = Image.fromarray(rgb8, mode="RGB")

    if max_side:
        w, h = img.size
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            img = img.resize(
                (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS
            )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    ext = os.path.splitext(out_path)[1].lower()

    # Pillow nie przyjmuje `exif=None` - sprawdza dlugosc, zanim zdazy
    # zauwazyc, ze nic nie dostal. Blok metadanych podajemy wiec tylko
    # wtedy, gdy naprawde jest co zapisac. PNG (blok eXIf) i TIFF przyjmuja
    # ten sam blok co JPEG - wczesniej wychodzily zupelnie bez metadanych.
    extra = {}
    block = exif_bytes(metadata, location)
    if block:
        extra["exif"] = block

    if ext in (".jpg", ".jpeg"):
        img.save(out_path, "JPEG", quality=quality, subsampling=0, optimize=True, **extra)
    elif ext == ".png":
        img.save(out_path, "PNG", compress_level=6, **extra)
    elif ext in (".tif", ".tiff"):
        img.save(out_path, "TIFF", **_tiff_exif(block))
    else:
        raise ValueError(f"Nieobsługiwane rozszerzenie: {ext}")

    return out_path


def _tiff_exif(block: bytes | None) -> dict:
    """Blok EXIF w postaci, ktorej zapis TIFF-a nie przekreca.

    Pillow rozpakowuje blok przed zapisem TIFF-a: teksty czyta jako Latin-1,
    a zapisuje jako ASCII z zamiana, wiec "Łukasz" wychodzil jako "??ukasz".
    Gotowe bajty zapisuje za to bez przekodowania - oddajemy mu wiec te same
    bajty UTF-8, ktore sa w bloku (Latin-1 odwraca sie bez strat).
    Poprawiamy tylko glowny katalog: autor, prawa i opis siedza wlasnie tam.
    """
    if not block:
        return {}
    exif = Image.Exif()
    exif.load(block)
    for tag, value in list(exif.items()):
        if isinstance(value, str):
            try:
                exif[tag] = value.encode("latin-1")
            except UnicodeEncodeError:
                pass
    return {"exif": exif}


def output_path_for(raw_path: str, out_dir: str, ext: str = ".jpg") -> str:
    stem = os.path.splitext(os.path.basename(raw_path))[0]
    return os.path.join(out_dir, stem + ext)


# --------------------------------------------------------------- opcje


@dataclass
class ExportOptions:
    """Komplet nastaw jednego eksportu."""

    folder: str = ""
    use_subfolder: bool = False
    subfolder: str = "Eksport"

    naming: str = NAMING_ORIGINAL
    custom_name: str = ""
    start_number: int = 1
    number_digits: int = 3

    on_existing: str = ON_EXISTING_ASK

    file_format: str = ".jpg"
    quality: int = 92
    max_side: int = 0  # 0 = pelna rozdzielczosc
    noise_quality: str = "high"

    # Metadane dla calej serii. Autor i prawa autorskie maja wlasne pola
    # wyboru, bo ich wartosci przychodza wypelnione z ustawien - samo
    # niepuste pole nie znaczy tu, ze uzytkownik chce je dopisac.
    add_author: bool = False
    author: str = ""
    add_copyright: bool = False
    copyright: str = ""
    keywords: str = ""
    subject: str = ""
    comment: str = ""

    def metadata_overrides(self) -> dict[str, str]:
        """Pola z okna eksportu pod nazwami EXIF; puste i odznaczone pomijamy."""
        values: dict[str, str] = {}
        if self.add_author and self.author.strip():
            values["Artist"] = self.author.strip()
        if self.add_copyright and self.copyright.strip():
            values["Copyright"] = self.copyright.strip()
        for key, value in (("XPKeywords", self.keywords), ("XPSubject", self.subject),
                           ("UserComment", self.comment)):
            if value.strip():
                values[key] = value.strip()
        return values

    def target_folder(self) -> str:
        if self.use_subfolder and self.subfolder.strip():
            return os.path.join(self.folder, self.subfolder.strip())
        return self.folder

    def file_name(self, source_path: str, index: int) -> str:
        """Nazwa pliku wynikowego dla `index`-tego zdjecia w kolejce (od zera)."""
        if self.naming == NAMING_CUSTOM and self.custom_name.strip():
            number = self.start_number + index
            digits = max(1, min(8, self.number_digits))
            return f"{self.custom_name.strip()}-{number:0{digits}d}{self.file_format}"
        stem = os.path.splitext(os.path.basename(source_path))[0]
        return stem + self.file_format

    def preview_name(self, source_path: str = "P1170926.RW2") -> str:
        return self.file_name(source_path, 0)


def export_metadata(source: str, params, options: ExportOptions | None = None
                    ) -> tuple[dict[str, str], tuple[float, float] | None]:
    """Metadane i wspolrzedne pliku wynikowego dla jednego zdjecia.

    Podstawa to plik zrodlowy (data, aparat, naswietlenie, GPS), na nia ida
    pola wpisane przy zdjeciu, a na wierzch pola z okna eksportu. Lokalizacja
    nadana na mapie wygrywa z GPS-em aparatu - skoro ktos ja poprawil, to
    dlatego, ze aparatowa byla zla albo jej nie bylo.
    """
    from .. import __version__

    camera, camera_location = source_metadata(source)
    fields = layer_metadata(
        camera,
        dict(params.metadata or {}) if params is not None else {},
        options.metadata_overrides() if options is not None else {},
        software=f"Punctum {__version__}",
    )
    if params is not None and params.has_location:
        return fields, (params.latitude, params.longitude)
    return fields, camera_location


@dataclass
class ExportPlan:
    """Lista par zrodlo-cel wraz z informacja o kolizjach nazw."""

    pairs: list[tuple[str, str]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def _unique_path(path: str, taken: set[str]) -> str:
    """Dokleja kolejny numer, az nazwa bedzie wolna."""
    stem, ext = os.path.splitext(path)
    counter = 1
    candidate = path
    while candidate.lower() in taken or os.path.exists(candidate):
        counter += 1
        candidate = f"{stem}-{counter}{ext}"
    return candidate


def plan_export(sources: list[str], options: ExportOptions) -> ExportPlan:
    """Wylicza sciezki docelowe i wskazuje, ktore z nich juz istnieja.

    Kolizje wykrywamy PRZED rozpoczeciem eksportu, zeby zadac pytanie raz,
    a nie przerywac pracy przy kazdym pliku. Sprawdzamy tez kolizje wewnatrz
    samej kolejki - przy nazwie z numeratorem dwa zdjecia moglyby dostac
    ten sam plik docelowy.
    """
    folder = options.target_folder()
    plan = ExportPlan()
    seen: set[str] = set()

    for index, source in enumerate(sources):
        target = os.path.join(folder, options.file_name(source, index))
        # Zrodlo nie moze byc celem. Przy RAW-ach bylo to niemozliwe, bo wynik
        # ma inne rozszerzenie; przy JPEG-u eksport do tego samego katalogu
        # trafia dokladnie w plik oryginalu i polityka "zastap" skasowalaby go
        # bezpowrotnie. Takiej decyzji nie wolno zostawiac uzytkownikowi przez
        # nieuwage - dajemy nowa nazwe niezaleznie od wybranej polityki.
        if os.path.normcase(os.path.abspath(target)) == os.path.normcase(
            os.path.abspath(source)
        ):
            target = _unique_path(target, seen)
        if target.lower() in seen:
            target = _unique_path(target, seen)
        seen.add(target.lower())
        plan.pairs.append((source, target))
        if os.path.exists(target):
            plan.conflicts.append(target)

    return plan


def resolve_conflicts(plan: ExportPlan, policy: str) -> tuple[list[tuple[str, str]], int]:
    """Stosuje wybrana polityke. Zwraca (pary do zapisania, liczba pominietych)."""
    if policy == ON_EXISTING_OVERWRITE or not plan.has_conflicts:
        return list(plan.pairs), 0

    if policy == ON_EXISTING_SKIP:
        kept = [(s, t) for s, t in plan.pairs if not os.path.exists(t)]
        return kept, len(plan.pairs) - len(kept)

    if policy == ON_EXISTING_UNIQUE:
        taken: set[str] = set()
        resolved = []
        for source, target in plan.pairs:
            final = _unique_path(target, taken)
            taken.add(final.lower())
            resolved.append((source, final))
        return resolved, 0

    return list(plan.pairs), 0
