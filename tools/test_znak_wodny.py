"""Znak wodny (punkt 11) bez interfejsu.

Wzor z ustawien jest poprawiany, znak laduje w wybranym rogu z marginesem,
ma zadana szerokosc (w % dluzszego boku, takze po zmniejszeniu w eksporcie)
i krycie, obraz PNG zachowuje przezroczystosc, kafelki pokrywaja caly kadr,
pusty tekst bierze prawa autorskie albo autora, a wylaczony znak nie rusza
ani piksela.

Uzycie:  python tools/test_znak_wodny.py [--pelny]
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wspolne import wypisz  # noqa: E402

from punctum.core.export import ExportOptions, save_image  # noqa: E402
from punctum.core.settings import Settings  # noqa: E402
from punctum.core.znak_wodny import ZnakWodny, naloz  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def tlo(szer: int, wys: int, jasnosc: int = 0) -> Image.Image:
    return Image.new("RGB", (szer, wys), (jasnosc, jasnosc, jasnosc))


def ramka(przed: Image.Image, po: Image.Image):
    """(lewo, gora, prawo, dol) zmienionych pikseli albo None."""
    roznica = np.abs(np.asarray(po, np.int16) - np.asarray(przed, np.int16)).max(axis=2)
    ys, xs = np.nonzero(roznica > 8)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# --- wzor z ustawien ------------------------------------------------------

znak = ZnakWodny.z_dict({"rozmiar": 500, "krycie": -3, "pozycja": "xx", "kolor": "zielony",
                         "obce": 1, "kafelki": 1, "tekst": None})
check("zakresy przyciete", (znak.rozmiar, znak.krycie) == (60, 5), f"{znak.rozmiar} {znak.krycie}")
check("zla pozycja i kolor -> domyslne", (znak.pozycja, znak.kolor) == ("pd", "bialy"))
check("tekst None -> pusty, kafelki bool", znak.tekst == "" and znak.kafelki is True)
check("nie slownik -> domyslny", ZnakWodny.z_dict("x") == ZnakWodny())
check("ustawienia przepuszczaja wzor przez z_dict",
      Settings(export_watermark={"krycie": 1000}).normalised().export_watermark["krycie"] == 100)
check("wzor przezywa zapis", ZnakWodny.z_dict(ZnakWodny(tekst="x", pozycja="s").do_dict())
      == ZnakWodny(tekst="x", pozycja="s"))

# --- tekst w rogu ---------------------------------------------------------

baza = tlo(1200, 800)
check("bez znaku obraz bez zmian", naloz(baza, None) is baza)
znak = ZnakWodny(tekst="© 2026 Łukasz", rozmiar=15, krycie=60, margines=3, pozycja="pd")
wynik = naloz(baza, znak)
r = ramka(baza, wynik)
check("znak narysowany", r is not None)
if r:
    l, g, p, d = r
    check("prawy dolny rog", l > 600 and g > 400, str(r))
    check("margines 3 % krotszego boku", 1200 - p >= 23 and 800 - d >= 23 and 1200 - p <= 30, str(r))
    check("szerokosc 15 % dluzszego boku", abs((p - l) - 180) <= 6, f"{p - l}")
najjasniejszy = int(np.asarray(wynik).max())
check("krycie 60 %", abs(najjasniejszy - 153) <= 3, str(najjasniejszy))
check("oryginal nie ruszony", ramka(baza, tlo(1200, 800)) is None)

wynik = naloz(tlo(1200, 800, 255), ZnakWodny(tekst="x y z", kolor="czarny", krycie=100))
check("czarny na bialym", int(np.asarray(wynik).min()) <= 5)

r = ramka(baza, naloz(baza, ZnakWodny(tekst="Srodek", pozycja="s")))
check("srodek", r is not None and abs((r[0] + r[2]) / 2 - 600) <= 3
      and abs((r[1] + r[3]) / 2 - 400) <= 8, str(r))
r = ramka(baza, naloz(baza, ZnakWodny(tekst="Lewy gorny", pozycja="lg", margines=0)))
check("lewy gorny bez marginesu", r is not None and r[0] <= 3 and r[1] <= 12, str(r))
# pion 400 x 1200: znak ma 720 px, a miedzy marginesami jest 240
pion = tlo(400, 1200)
r = ramka(pion, naloz(pion, ZnakWodny(tekst="Bardzo dlugi podpis", rozmiar=60, margines=20)))
check("za duzy znak zmniejszony do marginesow",
      r is not None and r[0] >= 78 and r[2] <= 322, str(r))

# --- obraz PNG ------------------------------------------------------------

with tempfile.TemporaryDirectory() as katalog:
    logo = os.path.join(katalog, "logo.png")
    rys = Image.new("RGBA", (200, 100), (255, 0, 0, 0))
    rys.paste((255, 0, 0, 255), (50, 0, 150, 100))  # pelny srodek, przezroczyste boki
    rys.save(logo)
    wynik = naloz(baza, ZnakWodny(rodzaj="obraz", obraz=logo, rozmiar=20, krycie=100,
                                  pozycja="lg", margines=0))
    r = ramka(baza, wynik)
    check("obraz: szerokosc kryjacej czesci", r is not None and abs((r[2] - r[0]) - 120) <= 3,
          str(r))
    check("obraz: kolor i przezroczyste boki",
          tuple(wynik.getpixel((120, 30))) == (255, 0, 0) and wynik.getpixel((10, 30)) == (0, 0, 0))
    check("brak pliku obrazu = bez znaku",
          naloz(baza, ZnakWodny(rodzaj="obraz", obraz=os.path.join(katalog, "nie.png"))) is baza)

    # --- eksport: znak po zmniejszeniu ------------------------------------
    plik = os.path.join(katalog, "wynik.png")
    rgb8 = np.zeros((1600, 2400, 3), np.uint8)
    opcje = ExportOptions(add_watermark=True, znak=ZnakWodny(tekst="Test", rozmiar=10))
    save_image(rgb8, plik, max_side=1200, znak=opcje.znak_do_eksportu())
    with Image.open(plik) as zapisany:
        r = ramka(tlo(1200, 800), zapisany.convert("RGB"))
    check("eksport: 10 % boku po zmniejszeniu", r is not None and abs((r[2] - r[0]) - 120) <= 5,
          str(r))

# --- kafelki --------------------------------------------------------------

wynik = np.asarray(naloz(baza, ZnakWodny(tekst="Punctum", kafelki=True, rozmiar=12)))
cwiartki = [wynik[:400, :600].max(), wynik[:400, 600:].max(),
            wynik[400:, :600].max(), wynik[400:, 600:].max()]
check("kafelki w kazdej cwiartce", min(cwiartki) > 50, str(cwiartki))
pokrycie = float((wynik.max(axis=2) > 8).mean())
check("kafelki nie zalewaja kadru", 0.02 < pokrycie < 0.35, f"{pokrycie:.3f}")

# --- tekst domyslny i wlacznik --------------------------------------------

check("wylaczony = None", ExportOptions(znak=ZnakWodny(tekst="x")).znak_do_eksportu() is None)
o = ExportOptions(add_watermark=True, copyright="© 2026 A", author="B")
check("pusty tekst -> prawa autorskie", o.znak_do_eksportu().tekst == "© 2026 A")
o.copyright = ""
check("bez praw -> (c) autor", o.znak_do_eksportu().tekst == "© B")
o.author = ""
check("bez niczego -> brak znaku", o.znak_do_eksportu() is None)
check("wzor w opcjach nietkniety", o.znak.tekst == "")

sys.exit(wypisz(results))
