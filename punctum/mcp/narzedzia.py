"""Opisy narzedzi MCP: nazwa, opis dla modelu i schemat wejscia.

Opisy sa po angielsku celowo: czyta je model jezykowy, nie uzytkownik
(to nie sa napisy interfejsu i nie ida przez `t()`), a angielski rozumie
kazdy klient - Claude, ChatGPT, modele lokalne w LM Studio.

Ten modul nie importuje Qt ani numpy: mostek stdio podaje z niego liste
narzedzi takze wtedy, gdy Punctum jest zamkniety - klient widzi wtedy
narzedzia od razu, a wywolanie konczy sie prosba o uruchomienie programu.

Zasada 16 briefu: kazda istotna nowa funkcja programu dostaje tu narzedzie.
`test_mcp` sprawdza, ze kazde pole `EditParams` ustawiane suwakiem ma
zakres w `ZAKRESY`.
"""

from __future__ import annotations

# Zakresy suwakow (app/edit_panel.py, wywolania `_add`). Model dostaje je
# w schemacie, a warstwa polecen przycina do nich wartosci - wartosc spoza
# suwaka dalaby nastawe, ktorej uzytkownik nie moze potem przesunac.
ZAKRESY: dict[str, tuple[float, float]] = {
    "temperature": (2000.0, 15000.0),
    "tint": (-100.0, 100.0),
    "exposure": (-5.0, 5.0),
    "contrast": (-100.0, 100.0),
    "highlights": (-100.0, 100.0),
    "shadows": (-100.0, 100.0),
    "whites": (-100.0, 100.0),
    "blacks": (-100.0, 100.0),
    "vibrance": (-100.0, 100.0),
    "saturation": (-100.0, 100.0),
    "rotation": (-45.0, 45.0),
    "sharpen_amount": (0.0, 150.0),
    "sharpen_radius": (0.5, 3.0),
    "sharpen_detail": (0.0, 100.0),
    "sharpen_masking": (0.0, 100.0),
    "noise_luminance": (0.0, 100.0),
    "noise_color": (0.0, 100.0),
    "mono_red": (-100.0, 100.0),
    "mono_yellow": (-100.0, 100.0),
    "mono_green": (-100.0, 100.0),
    "mono_cyan": (-100.0, 100.0),
    "mono_blue": (-100.0, 100.0),
    "mono_magenta": (-100.0, 100.0),
}

OPISY_POL: dict[str, str] = {
    "temperature": "White balance temperature in kelvin. For JPEG files it is relative "
                   "to the file (as-shot = the file's own look).",
    "tint": "White balance tint, negative = green, positive = magenta.",
    "exposure": "Exposure in EV stops.",
    "contrast": "Contrast.",
    "highlights": "Highlights recovery (negative darkens bright areas).",
    "shadows": "Shadows (positive lifts dark areas).",
    "whites": "White point.",
    "blacks": "Black point.",
    "vibrance": "Vibrance - saturation that protects already saturated colours and skin.",
    "saturation": "Saturation of all colours.",
    "rotation": "Straightening angle in degrees (fine rotation, not 90-degree turns).",
    "sharpen_amount": "Sharpening amount (RAW default 40, JPEG default 0).",
    "sharpen_radius": "Sharpening radius in pixels.",
    "sharpen_detail": "Sharpening detail.",
    "sharpen_masking": "Sharpening edge masking (higher = only edges are sharpened).",
    "noise_luminance": "Luminance noise reduction.",
    "noise_color": "Colour noise reduction.",
    "mono_red": "Black & white mix: brightness of reds.",
    "mono_yellow": "Black & white mix: brightness of yellows.",
    "mono_green": "Black & white mix: brightness of greens.",
    "mono_cyan": "Black & white mix: brightness of cyans.",
    "mono_blue": "Black & white mix: brightness of blues.",
    "mono_magenta": "Black & white mix: brightness of magentas.",
}

# Grupy jak w presetach (core/presety.GRUPY) - te same nazwy w obu miejscach,
# zeby "kopiuj kolor" znaczylo to samo w oknie i w poleceniu.
GRUPY = ("balans", "ton", "obecnosc", "monochrom", "wyostrzanie", "szum")
OPIS_GRUP = ("Groups: balans = white balance, ton = exposure/contrast/highlights/"
             "shadows/whites/blacks, obecnosc = vibrance/saturation, monochrom = "
             "black & white, wyostrzanie = sharpening, szum = noise reduction.")

FILTRY = ("brak", "zolty", "pomaranczowy", "czerwony", "zielony")

_CEL = {
    "target": {
        "type": "string", "enum": ["current", "selected"], "default": "current",
        "description": "Which photos to change when `photos` is not given: the photo "
                       "open in the editor, or all photos selected in the filmstrip.",
    },
    "photos": {
        "type": "array", "items": {"type": "string"},
        "description": "File names (as returned by list_photos) to change instead of `target`.",
    },
}


def _schemat(wlasciwosci: dict | None = None, wymagane: list[str] | None = None) -> dict:
    schemat = {"type": "object", "properties": wlasciwosci or {}}
    if wymagane:
        schemat["required"] = wymagane
    return schemat


def _pola_nastaw() -> dict:
    pola = {}
    for nazwa, (lo, hi) in ZAKRESY.items():
        pola[nazwa] = {"type": "number", "minimum": lo, "maximum": hi,
                       "description": OPISY_POL[nazwa]}
    return pola


def _pola_zmian() -> dict:
    # Zmiany wzgledne bez minimum i maksimum ze schematu: "+500 K" nie miesci
    # sie w zakresie 2000..15000, a jest poprawnym poleceniem.
    return {nazwa: {"type": "number"} for nazwa in ZAKRESY}


def _narzedzie(nazwa: str, opis: str, wejscie: dict, tylko_odczyt: bool = False) -> dict:
    return {
        "name": nazwa,
        "description": opis,
        "inputSchema": wejscie,
        # Wskazowka dla klienta: odczyty moze puszczac bez pytania uzytkownika.
        "annotations": {"readOnlyHint": tylko_odczyt, "destructiveHint": False},
    }


NARZEDZIA: list[dict] = [
    # --- 1. rozpoznanie ---------------------------------------------------
    _narzedzie(
        "get_status",
        "Current state of Punctum: open folder, photo open in the editor, selected "
        "photos, number of photos. Call this first.",
        _schemat(), tylko_odczyt=True),
    _narzedzie(
        "list_photos",
        "List photos of the open folder (in filmstrip order) with date, camera, ISO, "
        "exposure, whether they already have edits and a location.",
        _schemat({
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
            "only_selected": {"type": "boolean", "default": False},
        }), tylko_odczyt=True),
    _narzedzie(
        "get_photo_info",
        "EXIF data and current adjustment values of one photo (default: the open one).",
        _schemat({"photo": {"type": "string", "description": "File name."}}),
        tylko_odczyt=True),
    _narzedzie(
        "get_preview",
        "Rendered preview of the photo open in the editor, with all current "
        "adjustments (including noise reduction and sharpening), as an image you can "
        "look at. Use it to judge results. `view`: after (default), before (no "
        "adjustments, same crop) or side_by_side. `crop_100`: a 1:1 pixel crop around "
        "a point - use it to judge noise and sharpness.",
        _schemat({
            "max_size": {"type": "integer", "minimum": 256, "maximum": 2048,
                         "default": 1200, "description": "Longer side in pixels."},
            "view": {"type": "string", "enum": ["after", "before", "side_by_side"],
                     "default": "after"},
            "crop_100": {"type": "object", "description": "1:1 crop instead of the whole "
                         "frame. x, y = centre as fractions 0..1 of the (cropped) image.",
                         "properties": {"x": {"type": "number", "minimum": 0, "maximum": 1},
                                        "y": {"type": "number", "minimum": 0, "maximum": 1},
                                        "size": {"type": "integer", "minimum": 128,
                                                 "maximum": 1024, "default": 600}}},
        }),
        tylko_odczyt=True),
    _narzedzie(
        "get_image_stats",
        "Numbers describing the open photo as rendered now: brightness percentiles, "
        "clipped shadows/highlights, channel means, saturation, a coarse histogram.",
        _schemat(), tylko_odczyt=True),
    # --- 2. nawigacja -----------------------------------------------------
    _narzedzie(
        "open_folder",
        "Open a folder with photos in Punctum (absolute path on this computer).",
        _schemat({"path": {"type": "string"}}, ["path"])),
    _narzedzie(
        "open_photo",
        "Open a photo in the editor (waits until it is loaded).",
        _schemat({"photo": {"type": "string", "description": "File name."}}, ["photo"])),
    _narzedzie(
        "select_photos",
        "Select photos in the filmstrip, by names and/or criteria (all given criteria "
        "must match). Selected photos are the target of target='selected'.",
        _schemat({
            "photos": {"type": "array", "items": {"type": "string"}},
            "all": {"type": "boolean", "description": "Select every photo."},
            "date_from": {"type": "string", "description": "YYYY-MM-DD or YYYY-MM-DD HH:MM"},
            "date_to": {"type": "string", "description": "YYYY-MM-DD or YYYY-MM-DD HH:MM"},
            "iso_min": {"type": "integer"},
            "iso_max": {"type": "integer"},
            "camera": {"type": "string", "description": "Part of the camera name."},
            "format": {"type": "string", "enum": ["raw", "jpeg"]},
            "edited": {"type": "boolean"},
            "located": {"type": "boolean"},
        })),
    # --- 3. edycja --------------------------------------------------------
    _narzedzie(
        "set_adjustments",
        "Change adjustment sliders. `values` sets absolute values, `deltas` adds to "
        "the current ones (e.g. exposure +0.3). Each photo gets one undo step. "
        "Changes are saved next to the photo (the photo file is never modified).",
        _schemat({
            **_CEL,
            "values": {"type": "object", "properties": _pola_nastaw(),
                       "additionalProperties": False},
            "deltas": {"type": "object", "properties": _pola_zmian(),
                       "additionalProperties": False},
        })),
    _narzedzie(
        "auto_adjust",
        "Punctum's automatic tone correction (exposure, contrast, highlights, shadows, "
        "whites, blacks, vibrance). About 1 s per photo that is not open.",
        _schemat(dict(_CEL))),
    _narzedzie(
        "reset_adjustments",
        "Reset adjustments to defaults - all, or only some groups. " + OPIS_GRUP,
        _schemat({**_CEL, "groups": {"type": "array",
                                     "items": {"type": "string", "enum": list(GRUPY)}}})),
    _narzedzie(
        "list_presets",
        "List built-in and user presets with the values they set.",
        _schemat(), tylko_odczyt=True),
    _narzedzie(
        "apply_preset",
        "Apply a preset. A preset changes only the values it contains.",
        _schemat({**_CEL, "name": {"type": "string"}}, ["name"])),
    _narzedzie(
        "save_preset",
        "Save groups of the open photo's adjustments as a new user preset. " + OPIS_GRUP,
        _schemat({"name": {"type": "string"},
                  "groups": {"type": "array", "items": {"type": "string", "enum": list(GRUPY)},
                             "default": ["ton", "obecnosc", "monochrom"]}}, ["name"])),
    _narzedzie(
        "set_monochrome",
        "Turn black & white conversion on or off, optionally with a classic filter "
        "(zolty = yellow, pomaranczowy = orange, czerwony = red, zielony = green, "
        "brak = neutral). Fine mixing: mono_* values in set_adjustments.",
        _schemat({**_CEL, "enabled": {"type": "boolean"},
                  "filter": {"type": "string", "enum": list(FILTRY)}}, ["enabled"])),
    _narzedzie(
        "rotate",
        "Rotate by 90 degrees (resets the crop, like in the editor).",
        _schemat({**_CEL, "direction": {"type": "string", "enum": ["left", "right", "180"]}},
                 ["direction"])),
    _narzedzie(
        "set_crop",
        "Crop. Either `aspect` (largest centred crop with that ratio, e.g. '3:2', "
        "'1:1', '16:9', '4:5'; 'original' or 'none' removes the crop) or `rect` = "
        "[left, top, right, bottom] as fractions 0..1 of the rotated image.",
        _schemat({**_CEL, "aspect": {"type": "string"},
                  "rect": {"type": "array", "items": {"type": "number"},
                           "minItems": 4, "maxItems": 4}})),
    _narzedzie(
        "copy_adjustments",
        "Copy adjustments from one photo to others (like synchronising settings). "
        "Default groups: all except white balance. " + OPIS_GRUP,
        _schemat({**_CEL, "source": {"type": "string", "description": "File name."},
                  "groups": {"type": "array",
                             "items": {"type": "string", "enum": list(GRUPY)}}},
                 ["source"])),
    _narzedzie(
        "undo",
        "Undo the last change of the photo open in the editor.",
        _schemat()),
    _narzedzie(
        "redo",
        "Redo the last undone change of the photo open in the editor.",
        _schemat()),
    # --- 4. metadane i mapa ---------------------------------------------
    _narzedzie(
        "set_metadata",
        "Set descriptive metadata. Saved next to the photo and written into exported "
        "files (the original is not modified). An empty string removes Punctum's "
        "value and falls back to what the file itself contains.",
        _schemat({
            **_CEL,
            "fields": {"type": "object", "additionalProperties": False, "properties": {
                "title": {"type": "string", "description": "Title / description."},
                "comment": {"type": "string"},
                "keywords": {"type": "string",
                             "description": "Keywords separated by semicolons."},
                "subject": {"type": "string"},
                "author": {"type": "string"},
                "copyright": {"type": "string"},
                "date_taken": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"},
            }},
            "keywords_mode": {"type": "string", "enum": ["replace", "add", "remove"],
                              "default": "replace"},
        }, ["fields"])),
    _narzedzie(
        "find_place",
        "Look up a place name (OpenStreetMap) and return candidate coordinates. "
        "Needs internet.",
        _schemat({"query": {"type": "string"}}, ["query"]), tylko_odczyt=True),
    _narzedzie(
        "set_location",
        "Assign a location to photos: `latitude` + `longitude`, or `place` (a name "
        "looked up in OpenStreetMap, first match). One undo step in the Map tab.",
        _schemat({**_CEL, "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                  "longitude": {"type": "number", "minimum": -180, "maximum": 180},
                  "place": {"type": "string"}})),
    _narzedzie(
        "remove_location",
        "Remove the location assigned in Punctum (GPS written by the camera stays "
        "in the file and becomes visible again).",
        _schemat(dict(_CEL))),
    # --- 5. eksport -----------------------------------------------------
    _narzedzie(
        "export_photos",
        "Export photos with their adjustments to image files, like the Export "
        "dialog. Options not given come from the user's last export settings. "
        "By default waits until the export finishes.",
        _schemat({
            **_CEL,
            "folder": {"type": "string", "description": "Target folder (absolute)."},
            "subfolder": {"type": "string",
                          "description": "Subfolder inside `folder`; empty = none."},
            "format": {"type": "string", "enum": ["jpeg", "png", "tiff"]},
            "quality": {"type": "integer", "minimum": 1, "maximum": 100,
                        "description": "JPEG quality."},
            "max_side": {"type": "integer", "minimum": 0,
                         "description": "Longer side in pixels, 0 = full resolution."},
            "naming": {"type": "string", "enum": ["original", "custom"]},
            "custom_name": {"type": "string",
                            "description": "Base name for naming=custom (numbers added)."},
            "start_number": {"type": "integer", "minimum": 0},
            "on_existing": {"type": "string", "enum": ["unique", "skip", "overwrite"],
                            "default": "unique"},
            "watermark": {"type": "boolean", "description": "Apply the user's watermark."},
            "add_author": {"type": "boolean"},
            "add_copyright": {"type": "boolean"},
            "keywords": {"type": "string", "description": "Extra keywords for this export."},
            "subject": {"type": "string"},
            "comment": {"type": "string"},
            "wait": {"type": "boolean", "default": True},
        })),
    _narzedzie(
        "get_export_status",
        "Progress of a running export, or the result of the last one.",
        _schemat(), tylko_odczyt=True),
    _narzedzie(
        "cancel_export",
        "Stop a running export (files already written stay).",
        _schemat()),
]

# Przyjazne nazwy pol metadanych -> klucze EXIF (core/exif_edit.FIELDS).
POLA_METADANYCH = {
    "title": "ImageDescription", "comment": "UserComment", "keywords": "XPKeywords",
    "subject": "XPSubject", "author": "Artist", "copyright": "Copyright",
    "date_taken": "DateTimeOriginal",
}

NAZWY = {n["name"] for n in NARZEDZIA}

INSTRUKCJA = (
    "Punctum is a RAW/JPEG photo editor running on the user's computer. These tools "
    "control the open Punctum window: the user sees every change live. Edits are "
    "non-destructive (saved in XMP sidecars next to photos) and can be undone. "
    "Start with get_status and list_photos; use get_preview to look at results "
    "before and after changing adjustments. Photo names are file names."
)
