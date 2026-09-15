"""Test rdzenia bez GUI: wczytaj RAW, nanies parametry, zapisz JPG.

Przyklad:
    python tools/develop_cli.py "C:\\Zdjecia\\P1170926.RW2" -o out ^
        --exposure 0.57 --contrast 7 --highlights -76 --shadows 28 ^
        --whites 14 --blacks -19 --vibrance 15 --saturation 1
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import (  # noqa: E402
    EditParams,
    develop,
    load_raw,
    output_path_for,
    read_metadata,
    save_image,
)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Wywolanie pliku RAW do JPEG")
    ap.add_argument("raw", help="sciezka do pliku RAW")
    ap.add_argument("-o", "--out-dir", default="out", help="katalog docelowy")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--tint", type=float, default=0.0)
    ap.add_argument("--exposure", type=float, default=0.0)
    ap.add_argument("--contrast", type=float, default=0.0)
    ap.add_argument("--highlights", type=float, default=0.0)
    ap.add_argument("--shadows", type=float, default=0.0)
    ap.add_argument("--whites", type=float, default=0.0)
    ap.add_argument("--blacks", type=float, default=0.0)
    ap.add_argument("--vibrance", type=float, default=0.0)
    ap.add_argument("--saturation", type=float, default=0.0)
    ap.add_argument("--rotation", type=float, default=0.0)
    ap.add_argument("--noise-luminance", type=float, default=0.0)
    ap.add_argument("--noise-color", type=float, default=0.0)
    ap.add_argument("--max-side", type=int, default=None)
    ap.add_argument("--quality", type=int, default=92)
    ap.add_argument("--suffix", default="", help="dopisek do nazwy pliku wyjsciowego")
    return ap


def main() -> int:
    args = build_parser().parse_args()

    t0 = time.perf_counter()
    raw = load_raw(args.raw)
    t_decode = time.perf_counter() - t0

    meta = read_metadata(args.raw)
    print(f"aparat       : {meta.camera or '-'}")
    print(f"obiektyw     : {meta.lens or '-'}")
    print(
        f"parametry    : {meta.iso_text}, {meta.focal_text}, "
        f"{meta.shutter_text}, {meta.aperture_text}"
    )
    print(f"data         : {meta.shot_at or '-'}")
    print(
        "lokalizacja  : "
        + (f"{meta.latitude:.6f}, {meta.longitude:.6f}" if meta.has_gps else "brak")
    )
    print(f"WB z aparatu : {raw.as_shot_temp:.0f} K, odcien {raw.as_shot_tint:+.0f}")
    print(f"rozmiar      : {raw.shape[1]} x {raw.shape[0]}")
    print(f"dekodowanie  : {t_decode:.2f} s")

    p = EditParams(
        temperature=args.temperature,
        tint=args.tint,
        exposure=args.exposure,
        contrast=args.contrast,
        highlights=args.highlights,
        shadows=args.shadows,
        whites=args.whites,
        blacks=args.blacks,
        vibrance=args.vibrance,
        saturation=args.saturation,
        rotation=args.rotation,
        noise_luminance=args.noise_luminance,
        noise_color=args.noise_color,
    )

    t1 = time.perf_counter()
    rgb8 = develop(raw, p)
    t_develop = time.perf_counter() - t1
    print(f"obrobka      : {t_develop:.2f} s")

    stem, ext = os.path.splitext(output_path_for(args.raw, args.out_dir, ".jpg"))
    out_path = f"{stem}{args.suffix}{ext}"
    save_image(rgb8, out_path, quality=args.quality, max_side=args.max_side, meta=meta)
    size_kb = os.path.getsize(out_path) / 1024.0
    print(f"zapisano     : {out_path} ({size_kb:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
