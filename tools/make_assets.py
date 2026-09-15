"""Generuje drobne zasoby graficzne interfejsu.

Arkusze stylow Qt nie potrafia narysowac trojkata obramowaniem, tak jak robi to
CSS w przegladarce - trzeba podac gotowy obrazek. Skrypt tworzy strzalki pol
liczbowych w wariancie zwyklym i wyszarzonym, w dwoch skalach (zwykla i dla
ekranow o duzej gestosci pikseli).

Uruchamiac po zmianie kolorow motywu; wynik trafia do repozytorium.
"""

from __future__ import annotations

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

print(f"\nzapisano w {ASSETS}")
