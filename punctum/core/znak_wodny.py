"""Znak wodny nakladany na plik wynikowy eksportu (punkt 11).

Znak trafia wylacznie do pliku wynikowego, na samym koncu: po odszumianiu,
wyostrzaniu i zmniejszeniu. Gdyby szedl przed zmniejszeniem, cienkie litery
rozmylyby sie przy przeskalowaniu, a rozmiar zalezalby od rozdzielczosci
zrodla zamiast od tego, co widzi odbiorca. Stad tez rozmiar w procentach
dluzszego boku - ten sam wzor wyglada tak samo w pliku 1200 px i 6000 px.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from PIL import Image, ImageDraw, ImageFont

RODZAJ_TEKST = "tekst"
RODZAJ_OBRAZ = "obraz"

# Pozycje w siatce 3 x 3, wierszami od gory: g = gora, d = dol, l = lewo,
# p = prawo, s = srodek. Kolejnosc jest kolejnoscia przyciskow w siatce.
POZYCJE = ("lg", "g", "pg", "l", "s", "p", "ld", "d", "pd")

KOLORY = {"bialy": (255, 255, 255), "czarny": (0, 0, 0)}

# (najmniej, najwiecej) - w procentach
ZAKRESY = {"rozmiar": (2, 60), "krycie": (5, 100), "margines": (0, 20)}

# Kafelki biegna ukosem: poziome paski latwo wyciac albo zamalowac
# jednym pociagnieciem, ukosne przecinaja caly kadr.
KAT_KAFELKOW = 30.0

# Kolejnosc prob: pismo interfejsu Windows (polzgrube czyta sie lepiej przy
# niskim kryciu), potem pisma, ktore sa prawie wszedzie. Wszystkie maja
# polskie znaki; wbudowane pismo Pillow jest tylko ostatnia deska ratunku.
CZCIONKI = ("seguisb.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")


@dataclass
class ZnakWodny:
    rodzaj: str = RODZAJ_TEKST
    # Pusty tekst = prawa autorskie z ustawien, a bez nich "(c) autor"
    # (patrz ExportOptions.znak_do_eksportu). Dzieki temu domyslny znak
    # dziala od razu, gdy ktos wpisal juz autora dla metadanych.
    tekst: str = ""
    obraz: str = ""  # sciezka do PNG z przezroczystoscia
    kolor: str = "bialy"
    pozycja: str = "pd"
    kafelki: bool = False
    rozmiar: int = 15  # szerokosc znaku w % dluzszego boku
    krycie: int = 60
    margines: int = 3  # odstep od krawedzi w % krotszego boku

    def do_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def z_dict(cls, dane) -> "ZnakWodny":
        """Wzor z ustawien - obce pola pomijamy, zle wartosci poprawiamy."""
        znak = cls()
        if not isinstance(dane, dict):
            return znak
        for nazwa, domyslna in asdict(znak).items():
            if nazwa not in dane:
                continue
            wartosc = dane[nazwa]
            try:
                if isinstance(domyslna, bool):
                    wartosc = bool(wartosc)
                elif isinstance(domyslna, int):
                    lo, hi = ZAKRESY[nazwa]
                    wartosc = max(lo, min(hi, int(wartosc)))
                else:
                    wartosc = str(wartosc or "")
            except (TypeError, ValueError):
                continue
            setattr(znak, nazwa, wartosc)
        if znak.rodzaj not in (RODZAJ_TEKST, RODZAJ_OBRAZ):
            znak.rodzaj = RODZAJ_TEKST
        if znak.pozycja not in POZYCJE:
            znak.pozycja = "pd"
        if znak.kolor not in KOLORY:
            znak.kolor = "bialy"
        return znak


# ------------------------------------------------------------- rysowanie


def _czcionka(rozmiar: int):
    for nazwa in CZCIONKI:
        try:
            return ImageFont.truetype(nazwa, rozmiar)
        except OSError:
            continue
    return ImageFont.load_default(rozmiar)


def _maska_tekstu(tekst: str, szerokosc: int) -> Image.Image | None:
    """Napis jako maska L o zadanej szerokosci (wysokosc wynika z pisma).

    Najpierw mierzymy napis w duzym stopniu, potem dobieramy stopien tak,
    zeby trafic w szerokosc - pismo nie skaluje sie idealnie liniowo, ale
    blad jest ponizej piksela na kazde sto.
    """
    tekst = tekst.strip()
    if not tekst or szerokosc < 4:
        return None
    probna = _czcionka(200)
    l, g, p, d = probna.getbbox(tekst)
    if p - l <= 0:
        return None
    stopien = max(6, round(200 * szerokosc / (p - l)))
    czcionka = _czcionka(stopien)
    l, g, p, d = czcionka.getbbox(tekst)
    maska = Image.new("L", (max(1, p - l), max(1, d - g)), 0)
    ImageDraw.Draw(maska).text((-l, -g), tekst, font=czcionka, fill=255)
    return maska


def znak_rgba(znak: ZnakWodny, dluzszy_bok: int) -> Image.Image | None:
    """Sam znak (RGBA, juz z kryciem) w rozmiarze dla obrazu o danym boku.

    Krycie wchodzi w kanal alfa, a nie w mieszanie przy nakladaniu - wtedy
    nakladanie jest zwyklym wklejeniem z maska, takim samym dla tekstu,
    obrazu i kafelkow.
    """
    szerokosc = max(1, round(dluzszy_bok * znak.rozmiar / 100))
    krycie = znak.krycie / 100
    if znak.rodzaj == RODZAJ_OBRAZ:
        if not znak.obraz:
            return None
        try:
            with Image.open(znak.obraz) as plik:
                obraz = plik.convert("RGBA")
        except (OSError, ValueError):
            return None
        wysokosc = max(1, round(obraz.height * szerokosc / obraz.width))
        obraz = obraz.resize((szerokosc, wysokosc), Image.LANCZOS)
        alfa = obraz.getchannel("A").point(lambda a: round(a * krycie))
        obraz.putalpha(alfa)
        return obraz
    maska = _maska_tekstu(znak.tekst, szerokosc)
    if maska is None:
        return None
    wynik = Image.new("RGBA", maska.size, KOLORY[znak.kolor] + (0,))
    wynik.putalpha(maska.point(lambda a: round(a * krycie)))
    return wynik


def _polozenie(znak: ZnakWodny, obraz: tuple[int, int], rozmiar: tuple[int, int]
               ) -> tuple[int, int]:
    szer, wys = obraz
    w, h = rozmiar
    m = round(min(szer, wys) * znak.margines / 100)
    kolumna, wiersz = POZYCJE.index(znak.pozycja) % 3, POZYCJE.index(znak.pozycja) // 3
    x = (m, (szer - w) // 2, szer - w - m)[kolumna]
    y = (m, (wys - h) // 2, wys - h - m)[wiersz]
    return x, y


def naloz(obraz: Image.Image, znak: ZnakWodny | None) -> Image.Image:
    """Obraz RGB ze znakiem; bez znaku (albo gdy nie ma czego nalozyc) - ten sam."""
    if znak is None:
        return obraz
    znaczek = znak_rgba(znak, max(obraz.size))
    if znaczek is None:
        return obraz
    wynik = obraz.convert("RGB") if obraz.mode != "RGB" else obraz.copy()
    szer, wys = wynik.size

    if znak.kafelki:
        obrocony = znaczek.rotate(KAT_KAFELKOW, resample=Image.BICUBIC, expand=True)
        # Siatke ukladamy w ukladzie obroconym (u wzdluz napisu, v w poprzek)
        # i dopiero srodki przenosimy na obraz. Odstepy liczone z ramki po
        # obrocie albo nachodzily na siebie, albo robily rzadka szachownice,
        # zaleznie od dlugosci napisu.
        w, h = znaczek.size
        krok_u = w + max(8, h * 3)
        krok_v = max(8, h * 5)
        kat = math.radians(KAT_KAFELKOW)
        cos_k, sin_k = math.cos(kat), math.sin(kat)
        zasieg = math.hypot(szer, wys) / 2 + w
        n_u, n_v = math.ceil(zasieg / krok_u) + 1, math.ceil(zasieg / krok_v) + 1
        sx, sy = szer / 2, wys / 2
        for j in range(-n_v, n_v + 1):
            przesun = krok_u / 2 if j % 2 else 0.0
            for i in range(-n_u, n_u + 1):
                u, v = i * krok_u + przesun, j * krok_v
                # obrot przeciwny do wskazowek zegara, os y w dol
                cx = sx + u * cos_k + v * sin_k
                cy = sy - u * sin_k + v * cos_k
                x, y = round(cx - obrocony.width / 2), round(cy - obrocony.height / 2)
                if x < szer and y < wys and x + obrocony.width > 0 and y + obrocony.height > 0:
                    wynik.paste(obrocony, (x, y), obrocony)
        return wynik

    # Znak wiekszy niz miejsce miedzy marginesami zmniejszamy, zamiast
    # ucinac - uciety podpis wyglada na blad, nie na decyzje.
    m = round(min(szer, wys) * znak.margines / 100)
    miejsce_w, miejsce_h = max(1, szer - 2 * m), max(1, wys - 2 * m)
    if znaczek.width > miejsce_w or znaczek.height > miejsce_h:
        skala = min(miejsce_w / znaczek.width, miejsce_h / znaczek.height)
        znaczek = znaczek.resize(
            (max(1, math.floor(znaczek.width * skala)), max(1, math.floor(znaczek.height * skala))),
            Image.LANCZOS,
        )
    wynik.paste(znaczek, _polozenie(znak, (szer, wys), znaczek.size), znaczek)
    return wynik
