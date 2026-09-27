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

# ------------------------------------------------------------------ logo
# Znak "P." (punkt 16): wariant ciemny do okna programu (logo.svg) i fioletowy
# na pasek zadan i do pliku .ico (logo-fiolet.svg) - na jasnym pasku zadan
# ciemny kafel zlewal sie z tlem przy 16 px. Grupa P + kropka jest przesunieta
# tak, by na srodku kafla stal jej optyczny srodek, a nie sama litera.

FIOLET, FIOLET_JASNY, JASNY, KAFEL = "#6c63ff", "#7b73ff", "#e8e8ea", "#26262a"


def logo_svg(tlo: str, kropka: str, obwodka: str = "") -> str:
    ramka = f' stroke="{obwodka}" stroke-width="3"' if obwodka else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'
        f'<rect x="8" y="8" width="240" height="240" rx="54" fill="{tlo}"{ramka}/>'
        '<g transform="translate(-10 -4)">'
        f'<path d="M72 212V60h56a48 48 0 0 1 0 96H72" fill="none" stroke="{JASNY}" '
        'stroke-width="34" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="201.2" cy="204" r="25" fill="{kropka}"/></g></svg>\n'
    )


LOGA = {
    "logo.svg": logo_svg(KAFEL, FIOLET_JASNY, "#3a3a42"),
    "logo-fiolet.svg": logo_svg(FIOLET, JASNY),
}
for nazwa, tresc in LOGA.items():
    with open(os.path.join(ASSETS, nazwa), "w", encoding="utf-8") as plik:
        plik.write(tresc)
    print(f"  {nazwa:<28} wektor")

# Rastrowanie SVG robi Qt - to ten sam silnik, ktory pokaze logo w programie,
# wiec .ico wyglada dokladnie tak jak ikona okna.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

_qt = QGuiApplication.instance() or QGuiApplication([])


def svg_do_obrazu(svg: str, rozmiar: int) -> Image.Image:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    obraz = QImage(rozmiar, rozmiar, QImage.Format_RGBA8888)
    obraz.fill(Qt.transparent)
    painter = QPainter(obraz)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, rozmiar, rozmiar))
    painter.end()
    return Image.frombuffer("RGBA", (rozmiar, rozmiar), bytes(obraz.constBits()), "raw", "RGBA", 0, 1)


ROZMIARY_ICO = (16, 24, 32, 48, 64, 128, 256)
# Kazdy rozmiar rastrowany osobno z wektora - zmniejszanie 256 px rozmywa
# kreske P przy 16 px bardziej niz rysowanie od razu w tej skali.
obrazy = [svg_do_obrazu(LOGA["logo-fiolet.svg"], r) for r in ROZMIARY_ICO]
obrazy[-1].save(
    os.path.join(ASSETS, "punctum.ico"),
    sizes=[(r, r) for r in ROZMIARY_ICO],
    append_images=obrazy[:-1],
)
print(f"  {'punctum.ico':<28} {', '.join(str(r) for r in ROZMIARY_ICO)}")
svg_do_obrazu(LOGA["logo.svg"], 512).save(os.path.join(ASSETS, "logo-512.png"))
print(f"  {'logo-512.png':<28} 512x512 (README)")

# ------------------------------------------------------------ ikony narzedzi
# Jeden styl: kreska 2 px na siatce 24 px, zaokraglone konce, kolor jak
# dotychczasowa ikona kadrowania. Fiolet tylko tam, gdzie znaczy "punkt"
# (pinezka z geotagiem). Wersje wyszarzone robi sam QIcon.

KOLOR_IKON = "#c8c8cc"
IKONY = {
    "crop": '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M2 6h14a2 2 0 0 1 2 2v14"/>',
    # Kadr pomniejszony do lewego gornego rogu i ta sama strzalka powrotu co
    # przy geotagu - "cofnij do oryginalu" wyglada w calym programie tak samo.
    "crop-reset": (
        '<path d="M5.5 2v9.5a1.5 1.5 0 0 0 1.5 1.5h6"/><path d="M2 5.5h9.5a1.5 1.5 0 0 1 1.5 1.5v3"/>'
        '<path d="M14 18a3.6 3.6 0 1 0 1.1-2.6L14 16.5"/><path d="M14 13.8v2.7h2.7"/>'
    ),
    "rotate-left": '<path d="M4 12a8 8 0 1 0 2.34-5.66L4 8.5"/><path d="M4 4v4.5h4.5"/>',
    "rotate-right": '<path d="M20 12a8 8 0 1 1-2.34-5.66L20 8.5"/><path d="M20 4v4.5h-4.5"/>',
    "rotate-180": '<path d="M4 15a8 8 0 0 1 16 0"/><path d="M17 12.5l3 3 3-3"/><path d="M8 20h8"/>',
    "before-after": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 2v20"/>'
        f'<path d="M3 6a2 2 0 0 1 2-2h7v16H5a2 2 0 0 1-2-2z" fill="{KOLOR_IKON}" fill-opacity=".35" stroke="none"/>'
    ),
    # Ta sama ramka co "przed / po", ale linia z kolkiem i grotami - jak
    # uchwyt, ktory podzial rysuje na zdjeciu.
    "split-view": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v5M12 15v5"/>'
        '<circle cx="12" cy="12" r="3"/><path d="M7.5 10.5 6 12l1.5 1.5M16.5 10.5 18 12l-1.5 1.5"/>'
    ),
    # Dwie ramki obok siebie, lewa przyciemniona jak "przed" w ikonie
    # "przed / po" - dwa widoki porownania.
    "side-by-side": (
        '<rect x="2" y="5" width="9" height="14" rx="1.5"/><rect x="13" y="5" width="9" height="14" rx="1.5"/>'
        f'<rect x="2" y="5" width="9" height="14" rx="1.5" fill="{KOLOR_IKON}" fill-opacity=".35" stroke="none"/>'
    ),
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "fit": '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>',
    "actual-size": (
        '<path d="M5 8l2.5-2v12M16.5 8l2.5-2v12"/>'
        f'<circle cx="12" cy="9.5" r=".6" fill="{KOLOR_IKON}"/><circle cx="12" cy="14.5" r=".6" fill="{KOLOR_IKON}"/>'
    ),
    "export": '<path d="M4 14v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/><path d="M12 15V3M7 8l5-5 5 5"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "unlock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.75-1.4"/>',
    "filter": '<path d="M3 5h18l-7 8.5V19l-4 2v-7.5z"/>',
    "select-all": (
        '<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/>'
        '<rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>'
    ),
    "geotag": (
        '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/>'
        f'<circle cx="12" cy="10" r="2.2" fill="{FIOLET_JASNY}" stroke="none"/>'
    ),
    "no-geotag": '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><path d="M3 3l18 18"/>',
    "geotag-reset": (
        '<path d="M10 19s-5.5-4.8-5.5-9.5a5.5 5.5 0 0 1 11 0"/>'
        f'<circle cx="10" cy="9.5" r="1.8" fill="{KOLOR_IKON}" stroke="none"/>'
        '<path d="M14 18a3.6 3.6 0 1 0 1.1-2.6L14 16.5"/><path d="M14 13.8v2.7h2.7"/>'
    ),
}
IKONY_DIR = os.path.join(ASSETS, "icons")
os.makedirs(IKONY_DIR, exist_ok=True)
for nazwa, wnetrze in IKONY.items():
    with open(os.path.join(IKONY_DIR, f"{nazwa}.svg"), "w", encoding="utf-8") as plik:
        plik.write(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
            f'<g fill="none" stroke="{KOLOR_IKON}" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{wnetrze}</g></svg>\n'
        )
print(f"  icons/*.svg                  {len(IKONY)} ikon")

# ------------------------------------------------------- tlo ekranu startowego
# Rozmyte swiatla i jeden ostry punkt - idea punctum: wszystko miekkie, jedna
# rzecz kluje. Tylko tlo; napisy (nazwa, haslo, wersja, stan) rysuje program,
# bo zaleza od jezyka. Generator liczb z ustalonym ziarnem - ten sam obraz
# przy kazdym uruchomieniu skryptu.

import cv2  # noqa: E402
import numpy as np  # noqa: E402

EKRAN_W, EKRAN_H = 640, 380


def _kolor(hex_: str) -> np.ndarray:
    return np.array([int(hex_[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32) / 255.0


def _nad(obraz: np.ndarray, kolor, alfa: np.ndarray) -> None:
    """Nakladanie "over" koloru o masce alfa (0..1) na obraz float RGB."""
    a = alfa[..., None]
    obraz *= 1.0 - a
    obraz += np.asarray(kolor, dtype=np.float32) * a


def tlo_ekranu(skala: int) -> Image.Image:
    w, h = EKRAN_W * skala, EKRAN_H * skala
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    xs = (xs + 0.5) / skala
    ys = (ys + 0.5) / skala
    # gradient promienisty jak w projekcie: srodek (0.72, 0.30), promien 0.9 wymiaru
    t = np.clip(np.hypot((xs / EKRAN_W - 0.72) / 0.9, (ys / EKRAN_H - 0.30) / 0.9), 0, 1)
    a, b, c = _kolor("#211d33"), _kolor("#141318"), _kolor("#0f0f12")
    k1 = np.clip(t / 0.6, 0, 1)[..., None]
    k2 = np.clip((t - 0.6) / 0.4, 0, 1)[..., None]
    obraz = np.where(t[..., None] < 0.6, a + (b - a) * k1, b + (c - b) * k2).astype(np.float32)

    ziarno = 7
    def los() -> float:
        nonlocal ziarno
        ziarno = (ziarno * 16807) % 2147483647
        return ziarno / 2147483647

    kolory = [_kolor(k) for k in ("#6c63ff", "#8e7bff", "#4a6cff", "#b07cff", "#ff9a6a")]
    for i in range(22):
        x, y, r = 180 + los() * 470, -20 + los() * 300, 18 + los() * 60
        kolor = kolory[int(los() * (5 if i % 7 == 0 else 4))]
        krycie = 0.08 + los() * 0.22
        maska = np.clip(r - np.hypot(xs - x, ys - y) + 0.5, 0, 1) * krycie
        sigma = (16 if r > 45 else 6) * skala
        _nad(obraz, kolor, cv2.GaussianBlur(maska, (0, 0), sigma))

    # przyciemnienie dolu pod napisami
    _nad(obraz, _kolor("#0f0f12"), np.clip((ys / EKRAN_H - 0.45) / 0.55, 0, 1) * 0.95)

    # ostry punkt z poswiata
    d = np.hypot(xs - 468, ys - 128) / 30
    bialy, fiolet = np.ones(3, np.float32), _kolor(FIOLET_JASNY)
    k = np.clip(d / 0.25, 0, 1)[..., None]
    kolor = np.where(d[..., None] < 0.25, bialy + (fiolet - bialy) * k, fiolet)
    alfa = np.where(d < 0.25, 0.9 + (0.55 - 0.9) * (d / 0.25), 0.55 * (1 - (d - 0.25) / 0.75))
    _nad(obraz, kolor, np.clip(alfa, 0, 1) * (d < 1))
    _nad(obraz, bialy, np.clip(4.5 - np.hypot(xs - 468, ys - 128) + 0.5, 0, 1))

    # drobny szum przed zaokragleniem do 8 bitow - bez niego lagodny gradient
    # ciemnego tla rozpada sie na widoczne pasy
    szum = np.random.default_rng(16).triangular(-1, 0, 1, obraz.shape).astype(np.float32)
    wynik = np.clip(obraz * 255 + szum, 0, 255).round().astype(np.uint8)
    return Image.fromarray(wynik, "RGB")


for skala, tag in ((1, ""), (2, "@2x")):
    tlo_ekranu(skala).save(os.path.join(ASSETS, f"ekran-startowy{tag}.png"), optimize=True)
    print(f"  {f'ekran-startowy{tag}.png':<28} {EKRAN_W * skala}x{EKRAN_H * skala}")

print(f"\nzapisano w {ASSETS}")
