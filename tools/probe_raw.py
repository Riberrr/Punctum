"""Diagnostyka: co LibRaw widzi w pliku RAW."""
import sys
import numpy as np
import rawpy

path = sys.argv[1]
with rawpy.imread(path) as raw:
    s = raw.sizes
    print(f"plik              : {path}")
    print(f"rozmiar RAW       : {s.raw_width} x {s.raw_height}")
    print(f"obszar widoczny   : {s.width} x {s.height}")
    print(f"proporcje px      : {s.pixel_aspect}")
    print(f"orientacja (flip) : {s.flip}")
    print(f"wzor CFA          : {raw.color_desc}")
    print(f"liczba kanalow    : {raw.num_colors}")
    print(f"czarny punkt      : {raw.black_level_per_channel}")
    print(f"bialy punkt       : {raw.white_level}")
    print(f"WB z aparatu      : {[round(float(x), 4) for x in raw.camera_whitebalance]}")
    print(f"WB dzienne        : {[round(float(x), 4) for x in raw.daylight_whitebalance]}")
    print("macierz kamera->XYZ:")
    m = np.asarray(raw.rgb_xyz_matrix, dtype=np.float64)
    for row in m[:raw.num_colors]:
        print("   " + "  ".join(f"{v: .5f}" for v in row))
    vis = raw.raw_image_visible
    print(f"typ danych        : {vis.dtype}")
    print(f"zakres wartosci   : {int(vis.min())} .. {int(vis.max())}")
    sat = int((vis >= raw.white_level * 0.995).sum())
    print(f"piksele przepalone: {sat} ({100.0 * sat / vis.size:.3f} %)")
    try:
        th = raw.extract_thumb()
        print(f"podglad JPEG      : {th.format}, {len(th.data) / 1024:.0f} kB")
    except Exception as exc:
        print(f"podglad JPEG      : brak ({exc})")
