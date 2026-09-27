"""Monochrom (12) i presety (4) bez interfejsu.

Monochrom: szarosci nie zmienia, suwak barwy rusza tylko swoja barwe,
wynik ma rowne kanaly, sidecar przenosi nastawy. Presety: wbudowane sa
poprawne, zapis wycina tylko wybrane grupy, obcy albo zepsuty plik jest
odrzucany, wartosci spoza zakresu przyciete, import i usuwanie dzialaja.

Uzycie:  python tools/test_presety.py [--pelny]
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from wspolne import wypisz  # noqa: E402

from punctum.core import EditParams, sidecar  # noqa: E402
from punctum.core import presety  # noqa: E402
from punctum.core.params import MONO_FIELDS  # noqa: E402
from punctum.core.pipeline import apply_mono, _luminance  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# --- monochrom ----------------------------------------------------------

# piksele liniowe: szary, czerwony, zolty, zielony, turkusowy, niebieski, fioletowy
KOLORY = np.array([[
    [0.18, 0.18, 0.18], [0.40, 0.03, 0.03], [0.40, 0.35, 0.03], [0.03, 0.30, 0.03],
    [0.03, 0.30, 0.30], [0.03, 0.05, 0.40], [0.30, 0.03, 0.40],
]], dtype=np.float32)
BAZA = _luminance(KOLORY)[0]

check("wylaczony monochrom nie rusza obrazu",
      apply_mono(KOLORY, EditParams()) is KOLORY)

neutralny = apply_mono(KOLORY, EditParams(mono=True))
check("wynik ma rowne kanaly",
      bool(np.allclose(neutralny[..., 0], neutralny[..., 1]) and np.allclose(neutralny[..., 1], neutralny[..., 2])))
check("bez suwakow = sama luminancja", bool(np.allclose(neutralny[0, :, 0], BAZA, atol=1e-6)))

for i, pole in enumerate(MONO_FIELDS, start=1):
    jasniej = apply_mono(KOLORY, EditParams(mono=True, **{pole: 100.0}))[0, :, 0]
    ciemniej = apply_mono(KOLORY, EditParams(mono=True, **{pole: -100.0}))[0, :, 0]
    check(f"{pole}: swoja barwa jasnieje i ciemnieje",
          jasniej[i] > BAZA[i] * 1.5 and ciemniej[i] < BAZA[i] / 1.5,
          f"{BAZA[i]:.4f} -> {ciemniej[i]:.4f} / {jasniej[i]:.4f}")
    check(f"{pole}: szarosc bez zmian", abs(jasniej[0] - BAZA[0]) < 1e-6)
    # barwa po przeciwnej stronie kola (o 180 stopni) nie dostaje nic
    naprzeciw = (i - 1 + 3) % 6 + 1
    check(f"{pole}: barwa dopelniajaca bez zmian",
          abs(jasniej[naprzeciw] - BAZA[naprzeciw]) < 1e-3 * max(BAZA[naprzeciw], 1e-3) + 1e-6,
          f"{BAZA[naprzeciw]:.5f} -> {jasniej[naprzeciw]:.5f}")

with tempfile.TemporaryDirectory() as katalog:
    zdjecie = os.path.join(katalog, "a.rw2")
    open(zdjecie, "wb").close()
    nastawy = EditParams(mono=True, mono_red=33.0, mono_blue=-71.5)
    sidecar.write_sidecar(zdjecie, nastawy)
    odczyt = sidecar.read_sidecar(zdjecie)
    check("sidecar przenosi monochrom",
          odczyt is not None and odczyt.mono and odczyt.mono_red == 33.0 and odczyt.mono_blue == -71.5,
          str(odczyt and odczyt.mono_mix))
    sidecar.write_sidecar(zdjecie, EditParams(exposure=0.5))
    odczyt = sidecar.read_sidecar(zdjecie)
    check("sidecar bez monochromu czyta sie jako kolor",
          odczyt is not None and not odczyt.mono and odczyt.mono_mix == (0.0,) * 6)

# --- presety --------------------------------------------------------------

znane = {pole for pola in presety.GRUPY.values() for pole in pola}
check("grupy obejmuja tylko pola EditParams",
      znane <= set(EditParams.__dataclass_fields__), str(znane - set(EditParams.__dataclass_fields__)))
check("geometria, lokalizacja i metadane poza grupami",
      not znane & {"orientation", "rotation", "crop", "latitude", "longitude", "metadata"})
for preset in presety.WBUDOWANE:
    check(f"wbudowany {preset.nazwa!r}: znane pola, jawny monochrom",
          set(preset.wartosci) <= znane and "mono" in preset.wartosci, str(preset.wartosci))
check("filtry maja po szesc wartosci", all(len(f) == 6 for f in presety.FILTRY.values()))

with tempfile.TemporaryDirectory() as baza:
    check("brak katalogu = brak wlasnych", presety.wlasne(baza) == [])
    params = EditParams(exposure=1.2, contrast=30, vibrance=15, mono=True, mono_blue=-40,
                        temperature=4800.0, crop=(0.1, 0.1, 0.9, 0.9))
    wartosci = presety.wartosci_z_grup(params, ["obecnosc", "monochrom"])
    check("zapis wycina tylko wybrane grupy",
          set(wartosci) == {"vibrance", "saturation", "mono", *MONO_FIELDS}, str(sorted(wartosci)))

    zapisany = presety.zapisz_wlasny("Mój: niebo/noc?", wartosci, baza)
    check("nazwa z niedozwolonymi znakami daje poprawny plik",
          zapisany is not None and os.path.exists(zapisany.plik)
          and os.path.basename(zapisany.plik) == "Mój_ niebo_noc_.json", str(zapisany and zapisany.plik))
    wlasne = presety.wlasne(baza)
    check("wlasny preset wraca z dysku z nazwa i wartosciami",
          len(wlasne) == 1 and wlasne[0].nazwa == "Mój: niebo/noc?" and wlasne[0].wartosci == wartosci,
          str(wlasne))
    check("istnieje() widzi zapisany", presety.istnieje("Mój: niebo/noc?", baza))
    check("wszystkie = wbudowane + wlasne", len(presety.wszystkie(baza)) == len(presety.WBUDOWANE) + 1)

    obcy = os.path.join(baza, "obcy.json")
    with open(obcy, "w", encoding="utf-8") as plik:
        json.dump({"format": presety.FORMAT, "wersja": 9, "nazwa": "Z daleka",
                   "wartosci": {"exposure": 12, "contrast": "duzo", "crop": [0, 0, 1, 1],
                                "nieznane": 1, "mono": 1, "temperature": None}}, plik)
    zaimportowany = presety.importuj(obcy, baza)
    check("import przycina zakres, gubi obce pola",
          zaimportowany is not None and zaimportowany.wartosci == {"exposure": 5.0, "mono": True,
                                                                     "temperature": None},
          str(zaimportowany and zaimportowany.wartosci))

    zepsuty = os.path.join(baza, "zepsuty.json")
    with open(zepsuty, "w", encoding="utf-8") as plik:
        plik.write("{nie json")
    inny = os.path.join(baza, "inny.json")
    with open(inny, "w", encoding="utf-8") as plik:
        json.dump({"nazwa": "x", "wartosci": {"exposure": 1}}, plik)
    check("zepsuty plik odrzucony", presety.importuj(zepsuty, baza) is None)
    check("plik bez formatu Punctum odrzucony", presety.importuj(inny, baza) is None)

    check("wbudowanego nie da sie usunac", not presety.usun(presety.WBUDOWANE[0]))
    check("usuniecie wlasnego", presety.usun(presety.wlasne(baza)[0])
          and len(presety.wlasne(baza)) == 1)

    # nalozenie presetu = podmiana tylko jego pol
    wynik = EditParams.from_dict({**params.to_dict(), **presety.WBUDOWANE[0].wartosci})
    check("preset nie rusza ekspozycji ani kadru",
          wynik.exposure == 1.2 and wynik.crop == (0.1, 0.1, 0.9, 0.9) and not wynik.mono)

sys.exit(wypisz(results))
