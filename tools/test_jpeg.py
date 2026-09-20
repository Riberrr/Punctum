"""Test obslugi plikow JPEG: krzywa, kolor, automat, eksport, filtr formatow.

Najwazniejsze pytanie brzmi: czy JPEG wpuszczony w tor liniowy i wypuszczony
z niego bez zadnych korekt wychodzi taki sam, jaki byl. Jesli nie, to znaczy,
ze gdzies gubimy kolor albo gamma, i kazda dalsza korekta liczy sie od zlego
punktu wyjscia.

Uzycie:  python tools/test_jpeg.py [katalog z JPEG-ami]
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import (  # noqa: E402
    FORMAT_JPEG,
    FORMAT_RAW,
    EditParams,
    ExportOptions,
    auto_tone,
    count_formats,
    develop,
    folder_photos,
    load_photo,
    matches_filter,
    plan_export,
    read_metadata,
)
from punctum.core.jpeg_loader import (  # noqa: E402
    jpeg_thumbnail,
    load_jpeg,
    neutral_temp_tint,
    srgb_to_linear,
)
from punctum.core.pipeline import linear_to_srgb  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def make_test_jpeg(folder: str, name: str = "wzorzec.jpg") -> str:
    """Wzorzec o znanej zawartosci: gradient jasnosci i trzy plamy barwne."""
    height, width = 180, 320
    image = np.zeros((height, width, 3), dtype=np.uint8)
    ramp = np.linspace(0, 255, width, dtype=np.uint8)
    image[:120] = ramp[None, :, None]
    for index, color in enumerate(((210, 60, 60), (60, 190, 90), (70, 110, 230))):
        image[120:, index * (width // 3):(index + 1) * (width // 3)] = color
    path = os.path.join(folder, name)
    Image.fromarray(image).save(path, quality=100, subsampling=0)
    return path


# --- 1. krzywa sRGB tam i z powrotem --------------------------------------

values = np.linspace(0.0, 1.0, 4096, dtype=np.float64)
back = linear_to_srgb(srgb_to_linear(values))
check("krzywa sRGB jest odwracalna", float(np.abs(back - values).max()) < 1e-9,
      f"najwieksza roznica {float(np.abs(back - values).max()):.2e}")
check("18 % szarosci siedzi tam, gdzie powinno",
      abs(float(srgb_to_linear(np.array(0.4620))) - 0.18) < 0.002,
      f"{float(srgb_to_linear(np.array(0.4620))):.4f}")

with tempfile.TemporaryDirectory() as tmp:
    source = make_test_jpeg(tmp)
    original = np.asarray(Image.open(source).convert("RGB"))
    photo = load_jpeg(source)

    # --- 2. plik bez korekt wychodzi taki, jaki wszedl ---------------------
    output = develop(photo, EditParams(), denoise=False)
    difference = np.abs(output.astype(np.int16) - original.astype(np.int16))
    check("JPEG bez korekt wraca bez zmian", int(difference.max()) <= 1,
          f"najwieksza roznica {int(difference.max())} poziomu, "
          f"srednia {float(difference.mean()):.3f}")

    # --- 3. przestrzen barw ------------------------------------------------
    check("macierz barw jest jednostkowa",
          float(np.abs(photo.cam_to_srgb - np.eye(3)).max()) < 1e-6,
          f"{float(np.abs(photo.cam_to_srgb - np.eye(3)).max()):.2e}")
    check("mnozniki kanalow sa neutralne",
          float(np.abs(photo.as_shot_mult - 1.0).max()) < 0.01,
          " ".join(f"{m:.4f}" for m in photo.as_shot_mult))
    temp, tint = neutral_temp_tint()
    check("punkt wyjscia lezy w okolicy D65", 6000 <= temp <= 7000,
          f"{temp:.0f} K, tinta {tint:+.1f}")
    check("format jest rozpoznany", photo.source_format == "jpeg", photo.source_format)

    # --- 4. suwak temperatury dziala wzglednie -----------------------------
    same = develop(photo, EditParams(temperature=photo.as_shot_temp), denoise=False)
    check("temperatura w punkcie wyjscia nic nie zmienia",
          int(np.abs(same.astype(np.int16) - output.astype(np.int16)).max()) <= 1,
          f"{int(np.abs(same.astype(np.int16) - output.astype(np.int16)).max())} poziomu")

    # Kierunek suwaka: mowi, JAKIE bylo swiatlo. Wpisanie
    # niskiej wartosci znaczy "to swiatlo bylo cieple", wiec program odejmuje
    # ciepla i zdjecie robi sie chlodniejsze. Suwak w lewo = blekit.
    low = develop(photo, EditParams(temperature=3200.0), denoise=False)
    high = develop(photo, EditParams(temperature=12000.0), denoise=False)
    low_ratio = float(low[..., 0].mean()) / max(float(low[..., 2].mean()), 1e-6)
    high_ratio = float(high[..., 0].mean()) / max(float(high[..., 2].mean()), 1e-6)
    check("kierunek suwaka: nizsze kelwiny chlodza obraz (w lewo = błękit)",
          low_ratio < high_ratio,
          f"czerwien/blekit: {low_ratio:.2f} przy 3200 K, {high_ratio:.2f} przy 12000 K")

    # --- 5. automat ---------------------------------------------------------
    values_auto = auto_tone(photo)
    check("automat zwraca komplet parametrow",
          set(values_auto) >= {"exposure", "contrast", "highlights", "shadows"},
          ", ".join(f"{k} {v:g}" for k, v in values_auto.items()))
    check("automat nie wariuje na wzorcu", abs(values_auto["exposure"]) < 3.0,
          f"EV{values_auto['exposure']:+.2f}")

    # --- 6. miniatura -------------------------------------------------------
    thumb = jpeg_thumbnail(source, 200)
    check("miniatura powstaje i jest pomniejszona",
          thumb is not None and max(thumb.shape[:2]) <= 200,
          "brak" if thumb is None else f"{thumb.shape[1]}x{thumb.shape[0]}")


    # --- 7. eksport nie moze nadpisac oryginalu -----------------------------
    plan = plan_export([source], ExportOptions(folder=tmp, file_format=".jpg"))
    target = plan.pairs[0][1]
    check("eksport JPEG-a nie celuje w plik zrodlowy",
          os.path.abspath(target) != os.path.abspath(source),
          os.path.basename(target))

    # --- 8. filtr formatow ---------------------------------------------------
    for name in ("a.rw2", "b.JPG", "c.jpeg", "d.txt"):
        open(os.path.join(tmp, name), "w", encoding="utf-8").close()
    found = folder_photos(tmp)
    check("katalog listuje oba formaty, pomija obce pliki",
          len(found) == 4 and not any(p.endswith(".txt") for p in found),
          ", ".join(sorted(os.path.basename(p) for p in found)))
    raw_count, jpeg_count = count_formats(found)
    check("licznik formatow zgadza sie", (raw_count, jpeg_count) == (1, 3),
          f"{raw_count} RAW, {jpeg_count} JPEG")
    check("filtr RAW przepuszcza tylko RAW",
          [os.path.basename(p) for p in found if matches_filter(p, FORMAT_RAW)] == ["a.rw2"])
    check("filtr JPEG przepuszcza tylko JPEG",
          sum(1 for p in found if matches_filter(p, FORMAT_JPEG)) == 3)

# --- 9. prawdziwe zdjecia z biblioteki ------------------------------------

folder = sys.argv[1] if len(sys.argv) > 1 else ""
if folder and os.path.isdir(folder):
    real = [p for p in folder_photos(folder) if matches_filter(p, FORMAT_JPEG)][:5]
    print(f"\n=== PRAWDZIWE PLIKI ({len(real)}) ===")
    print(f"{'plik':<28}{'rozmiar':>12}{'ISO':>7}{'EV':>8}{'kontr':>7}{'cienie':>8}")
    print("-" * 72)
    ok_all = True
    for path in real:
        try:
            photo = load_photo(path)
            meta = read_metadata(path)
            values_auto = auto_tone(photo)
            rendered = develop(photo.proxy(1200), EditParams(), denoise=False)
        except Exception as error:
            ok_all = False
            print(f"{os.path.basename(path):<28}  blad: {type(error).__name__}: {error}")
            continue
        print(f"{os.path.basename(path):<28}{photo.raw_width}x{photo.raw_height:<6}"
              f"{(meta.iso or 0):>7}{values_auto['exposure']:>8.2f}"
              f"{values_auto['contrast']:>7.0f}{values_auto['shadows']:>8.0f}")
        ok_all = ok_all and rendered.size > 0 and photo.source_format == "jpeg"
    if real:
        check("prawdziwe JPEG-i wczytuja sie i licza", ok_all)

from wspolne import wypisz  # noqa: E402  (test jest skryptem, nie modulem)

sys.exit(wypisz(results))
