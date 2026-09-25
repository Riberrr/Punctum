"""Generuje drobne zasoby graficzne interfejsu.

Arkusze stylow Qt nie potrafia narysowac trojkata obramowaniem, tak jak robi to
CSS w przegladarce - trzeba podac gotowy obrazek. Skrypt tworzy strzalki pol
liczbowych w wariancie zwyklym i wyszarzonym, w dwoch skalach (zwykla i dla
ekranow o duzej gestosci pikseli).

Uruchamiac po zmianie kolorow motywu; wynik trafia do repozytorium.
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(HERE, "punctum", "assets")
os.makedirs(ASSETS, exist_ok=True)

WIDTH, HEIGHT = 9, 5
VARIANTS = {"": (200, 200, 208, 255), "-disabled": (90, 90, 98, 255)}


def triangle(width: int, height: int, pointing_up: bool) -> list[tuple[int, int]]:
    if pointing_up:
        return [(0, height - 1), (width - 1, height - 1), ((width - 1) / 2, 0)]
    return [(0, 0), (width - 1, 0), ((width - 1) / 2, height - 1)]


for suffix, color in VARIANTS.items():
    for name, up in (("up", True), ("down", False)):
        for scale, tag in ((1, ""), (2, "@2x")):
            w, h = WIDTH * scale, HEIGHT * scale
            # rysujemy w powiekszeniu i zmniejszamy - daje gladkie krawedzie
            oversample = 8
            big = Image.new("RGBA", (w * oversample, h * oversample), (0, 0, 0, 0))
            ImageDraw.Draw(big).polygon(
                [(x * oversample, y * oversample) for x, y in triangle(w, h, up)],
                fill=color,
            )
            image = big.resize((w, h), Image.LANCZOS)
            path = os.path.join(ASSETS, f"arrow-{name}{suffix}{tag}.png")
            image.save(path)
            print(f"  {os.path.basename(path):<28} {w}x{h}")

# Fajka zaznaczonego pola wyboru. Sam jasny kwadrat (bez znaku) czytal sie
# odwrotnie niz w innych programach: bialy wygladal jak "wylaczony".
# Ciemna fajka na jasnym tle, wariant wyszarzony dla pola nieaktywnego.
CHECK = 11  # pole ma 13 px, minus ramka
CHECK_VARIANTS = {"": (32, 32, 36, 255), "-disabled": (58, 58, 64, 255)}
CHECK_POINTS = [(0.18, 0.52), (0.42, 0.76), (0.84, 0.26)]

for suffix, color in CHECK_VARIANTS.items():
    for scale, tag in ((1, ""), (2, "@2x")):
        size = CHECK * scale
        oversample = 8
        big_size = size * oversample
        big = Image.new("RGBA", (big_size, big_size), (0, 0, 0, 0))
        ImageDraw.Draw(big).line(
            [(x * big_size, y * big_size) for x, y in CHECK_POINTS],
            fill=color, width=round(big_size * 0.17), joint="curve",
        )
        image = big.resize((size, size), Image.LANCZOS)
        path = os.path.join(ASSETS, f"check{suffix}{tag}.png")
        image.save(path)
        print(f"  {os.path.basename(path):<28} {size}x{size}")

# Kursor obrotu przy kadrowaniu. Qt nie ma takiego wbudowanego, a krzyzyk
# nie mowil, ze poza kadrem sie obraca. Luk z grotami na obu koncach, bialy
# z czarna obwodka - widoczny na jasnym i ciemnym zdjeciu. Goracy punkt
# w srodku obrazka (podawany w image_view.py).

CURSOR = 32
ARC_FROM, ARC_TO = 205.0, 335.0  # stopnie, os y w dol: gorny luk


def rotate_cursor_shapes(size: float) -> tuple[list, list]:
    centre, radius = size / 2, size * 0.30
    arc = [
        (centre + radius * math.cos(math.radians(a)), centre + radius * math.sin(math.radians(a)))
        for a in [ARC_FROM + (ARC_TO - ARC_FROM) * i / 40 for i in range(41)]
    ]
    heads = []
    for angle, sign in ((ARC_TO, 1.0), (ARC_FROM, -1.0)):
        t = math.radians(angle)
        px, py = centre + radius * math.cos(t), centre + radius * math.sin(t)
        tx, ty = -math.sin(t) * sign, math.cos(t) * sign  # styczna na zewnatrz luku
        nx, ny = math.cos(t), math.sin(t)
        length, half = size * 0.17, size * 0.13
        heads.append([
            (px + tx * length, py + ty * length),
            (px + nx * half, py + ny * half),
            (px - nx * half, py - ny * half),
        ])
    return arc, heads


for scale, tag in ((1, ""), (2, "@2x")):
    size = CURSOR * scale
    oversample = 8
    big_size = size * oversample
    arc, heads = rotate_cursor_shapes(big_size)
    big = Image.new("RGBA", (big_size, big_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    stroke = big_size * 0.075
    outline = big_size * 0.045
    for color, extra in (((0, 0, 0, 255), outline), ((255, 255, 255, 255), 0)):
        draw.line(arc, fill=color, width=round(stroke + 2 * extra), joint="curve")
        for head in heads:
            # obwodka grotu: trojkat powiekszony wokol srodka ciezkosci o tyle,
            # zeby odsunal sie o grubosc obwodki (promien wpisany ~0.064 rozmiaru)
            grow = 1.0 + extra / (big_size * 0.064)
            cx = sum(x for x, _ in head) / 3
            cy = sum(y for _, y in head) / 3
            draw.polygon([(cx + (x - cx) * grow, cy + (y - cy) * grow) for x, y in head], fill=color)
    image = big.resize((size, size), Image.LANCZOS)
    path = os.path.join(ASSETS, f"rotate-cursor{tag}.png")
    image.save(path)
    print(f"  {os.path.basename(path):<28} {size}x{size}")

print(f"\nzapisano w {ASSETS}")
