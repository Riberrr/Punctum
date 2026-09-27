"""Cofnij / ponow bez interfejsu: obie historie i lata na stare sidecary.

Pilnuje zasad z punktu 25: kazde zdjecie ma wlasna historie, powtorzony stan
nie jest krokiem, nowa zmiana po cofnieciu odcina ponawianie, a przypisanie
lokalizacji wielu zdjeciom cofa sie jednym ruchem. Do tego falszywe
`Orientation=1` ze starych sidecarow (punctum-exif.md).

Uzycie:  python tools/test_historia.py [--pelny]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from wspolne import wypisz  # noqa: E402

from punctum.core import EditParams  # noqa: E402
from punctum.core import exif_edit, sidecar  # noqa: E402
from punctum.core.historia import HistoriaKrokow, HistoriaStanow  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# --- historia stanow (Edycja) ---------------------------------------------

h = HistoriaStanow()
a0, a1, a2 = EditParams(), EditParams(exposure=1.0), EditParams(exposure=2.0)
check("pierwszy stan to punkt wyjscia, nie krok", h.zapamietaj("A", a0)
      and not h.mozna_cofnac("A"))
check("ten sam stan drugi raz nic nie dodaje", not h.zapamietaj("A", EditParams()))
h.zapamietaj("A", a1)
h.zapamietaj("A", a2)
check("po dwoch zmianach mozna cofnac", h.mozna_cofnac("A") and not h.mozna_ponowic("A"))

a2.exposure = 99.0  # historia ma kopie, nie obiekt z panelu
back = h.cofnij("A")
check("cofniecie oddaje poprzedni stan", back == EditParams(exposure=1.0), str(back.exposure))
check("zmiana obiektu po zapisie nie psuje historii",
      h.ponow("A") == EditParams(exposure=2.0))
h.cofnij("A")
back.exposure = 50.0  # oddany stan tez jest kopia
check("oddany stan to kopia", h.ponow("A") == EditParams(exposure=2.0))

h.cofnij("A")
h.cofnij("A")
check("na poczatku dalej sie nie cofa", h.cofnij("A") is None and h.mozna_ponowic("A"))
h.zapamietaj("A", EditParams(contrast=10.0))
check("nowa zmiana po cofnieciu odcina ponawianie", not h.mozna_ponowic("A"))

h.zapamietaj("B", EditParams(saturation=5.0))
check("kazde zdjecie ma osobna historie",
      not h.mozna_cofnac("B") and h.mozna_cofnac("A"))
check("zdjecie bez historii i brak zdjecia", not h.mozna_cofnac("C") and not h.mozna_cofnac(None)
      and not h.mozna_ponowic(None))

maly = HistoriaStanow(limit=3)
for i in range(10):
    maly.zapamietaj("A", EditParams(exposure=float(i)))
steps = 0
while maly.cofnij("A") is not None:
    steps += 1
check("limit krokow", steps == 2, f"{steps} krokow wstecz")

h.wyczysc()
check("wyczyszczenie", not h.mozna_cofnac("A") and not h.mozna_ponowic("A"))

# --- historia krokow (Mapa) -----------------------------------------------

m = HistoriaKrokow()
P = (49.3, 19.95)
check("krok bez zmian nie powstaje", not m.zapamietaj({"x": (None, None)}))
m.zapamietaj({"x": (None, P), "y": (None, P), "z": (P, P)})
check("przypisanie wielu zdjeciom to jeden krok", m.mozna_cofnac())
undo = m.cofnij()
check("cofniecie oddaje stan przed dla wszystkich zmienionych",
      undo == {"x": None, "y": None}, str(undo))
check("niezmienione zdjecie nie wchodzi do kroku", "z" not in undo)
check("i wtedy mozna ponowic", m.mozna_ponowic() and not m.mozna_cofnac())
check("ponowienie oddaje stan po", m.ponow() == {"x": P, "y": P})
m.cofnij()
m.zapamietaj({"x": (None, (1.0, 2.0))})
check("nowy krok po cofnieciu odcina ponawianie", not m.mozna_ponowic())
m.wyczysc()
check("wyczyszczenie mapy", not m.mozna_cofnac() and not m.mozna_ponowic())

# --- falszywe Orientation=1 ze starych sidecarow ----------------------------

in_file = {"Orientation": "6"}
original = exif_edit.current_values
exif_edit.current_values = lambda path: dict(in_file)
try:
    meta = {"Orientation": "1", "Artist": "A"}
    fixed = sidecar._bez_falszywej_orientacji("x.jpg", meta)
    check("Orientation=1 przy pliku obroconym jest pomijane",
          "Orientation" not in fixed and fixed.get("Artist") == "A", str(fixed))
    check("reszta pol zostaje nietknieta", meta == {"Orientation": "1", "Artist": "A"})
    check("inna orientacja z sidecara zostaje",
          sidecar._bez_falszywej_orientacji("x.jpg", {"Orientation": "8"}) == {"Orientation": "8"})
    in_file = {"Orientation": "1"}
    check("przy pliku bez obrotu 1 zostaje",
          sidecar._bez_falszywej_orientacji("x.jpg", {"Orientation": "1"}) == {"Orientation": "1"})
    in_file = {}
    check("przy pliku bez pola orientacji 1 zostaje",
          sidecar._bez_falszywej_orientacji("x.jpg", {"Orientation": "1"}) == {"Orientation": "1"})

    def broken(path):
        raise OSError("brak pliku")

    exif_edit.current_values = broken
    check("blad odczytu pliku nie blokuje nastaw",
          sidecar._bez_falszywej_orientacji("x.jpg", {"Orientation": "1"}) == {"Orientation": "1"})
finally:
    exif_edit.current_values = original

sys.exit(wypisz(results))
