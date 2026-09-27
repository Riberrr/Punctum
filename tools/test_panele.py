"""Uklad sekcji w panelach bez interfejsu: porzadkowanie zapisanego stanu.

Pilnuje obietnicy z punktu 23: zapis z innej wersji programu albo poprawiany
recznie nie moze rozsypac ukladu, a sekcja dodana pozniej ma trafic w swoje
domyslne miejsce, nie na koniec.

Uzycie:  python tools/test_panele.py [--pelny]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from wspolne import wypisz  # noqa: E402

from punctum.app.panele import (  # noqa: E402
    LEWY, PRAWY, SCHOWEK, TYTULY, UKLAD_DOMYSLNY, przenies, uporzadkuj, wstaw_domyslnie,
)
from punctum.core.settings import Settings  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def komplet(stan: dict) -> bool:
    wszystkie = stan[LEWY] + stan[PRAWY] + stan[SCHOWEK]
    return sorted(wszystkie) == sorted(TYTULY) and len(wszystkie) == len(set(wszystkie))


domyslny = uporzadkuj({})
check("pusty zapis = uklad domyslny",
      domyslny[LEWY] == UKLAD_DOMYSLNY[LEWY] and domyslny[PRAWY] == UKLAD_DOMYSLNY[PRAWY]
      and domyslny[SCHOWEK] == [], str(domyslny))
check("domyslnie nic zwiniete ani odblokowane, bez stanu ukrycia",
      domyslny["zwiniete"] == domyslny["odblokowane"] == [] and "ukryte" not in domyslny)

for nazwa, smiec in (("None", None), ("napis", "x"), ("lista", [1, 2]),
                     ("zle typy pol", {LEWY: "nawigator", "ukryte": "dane", "zwiniete": 5})):
    stan = uporzadkuj(smiec)
    check(f"smieci ({nazwa}) = uklad domyslny",
          stan[LEWY] == UKLAD_DOMYSLNY[LEWY] and stan[SCHOWEK] == [], str(stan))

stan = uporzadkuj({LEWY: ["dane", "nieznana", "dane", "nawigator"], PRAWY: ["dane", "histogram"]})
check("nieznane klucze i powtorki odpadaja", komplet(stan), str(stan))
check("pierwsze wystapienie wygrywa", stan[LEWY][:2] == ["dane", "nawigator"]
      and "dane" not in stan[PRAWY], str(stan))

zapis = {LEWY: list(UKLAD_DOMYSLNY[LEWY]),
         PRAWY: ["histogram", "kadrowanie", "balans", "ton", "obecnosc", "wyostrzanie"]}
stan = uporzadkuj(zapis)
check("nowa sekcja trafia za swojego poprzednika", stan[PRAWY][-1] == "szum", str(stan[PRAWY]))

zapis = {LEWY: list(UKLAD_DOMYSLNY[LEWY]),
         PRAWY: ["ton", "histogram", "kadrowanie", "obecnosc", "wyostrzanie", "szum"]}
stan = uporzadkuj(zapis)
check("nowa sekcja w przestawionym panelu: za poprzednikiem, reszta nietknieta",
      stan[PRAWY] == ["ton", "histogram", "kadrowanie", "balans", "obecnosc", "wyostrzanie", "szum"],
      str(stan[PRAWY]))

stan = uporzadkuj({PRAWY: ["kadrowanie", "balans"], LEWY: []})
check("brak poprzednika = na poczatek panelu", stan[PRAWY][0] == "histogram", str(stan[PRAWY]))

stan = uporzadkuj({SCHOWEK: ["szum"], PRAWY: ["histogram"], "ukryte": ["dane", "obca"],
                   "zwiniete": ["ton"], "odblokowane": [PRAWY, "srodek"]})
check("sekcja ze schowka zostaje w schowku", stan[SCHOWEK][0] == "szum" and "szum" not in stan[PRAWY])
check("dawne 'ukryte' trafiaja do schowka, obce odpadaja",
      stan[SCHOWEK] == ["szum", "dane"] and "dane" not in stan[LEWY] and komplet(stan), str(stan))
check("zwiniete, blokada: tylko znane klucze",
      stan["zwiniete"] == ["ton"] and stan["odblokowane"] == [PRAWY], str(stan))
check("uporzadkowanie jest stale", uporzadkuj(stan) == stan)

stan = uporzadkuj({})
przenies(stan, "obecnosc", LEWY, "dane")
check("przeniesienie przed wskazana sekcje", stan[LEWY][-2:] == ["obecnosc", "dane"]
      and "obecnosc" not in stan[PRAWY], str(stan))
przenies(stan, "obecnosc", SCHOWEK)
check("przeniesienie na koniec (schowek)", stan[SCHOWEK] == ["obecnosc"] and komplet(stan))
przenies(stan, "histogram", PRAWY, "nieznana")
check("nieznany cel wstawienia = koniec panelu", stan[PRAWY][-1] == "histogram", str(stan[PRAWY]))

stan = uporzadkuj({})
przenies(stan, "balans", SCHOWEK)
przenies(stan, "ton", LEWY)
wstaw_domyslnie(stan, "balans")
check("wlaczenie wraca za domyslnego poprzednika",
      stan[PRAWY][:3] == ["histogram", "kadrowanie", "balans"] and stan[SCHOWEK] == [], str(stan))
wstaw_domyslnie(stan, "histogram")
check("wlaczenie bez poprzednika = na poczatek", stan[PRAWY][0] == "histogram", str(stan[PRAWY]))

check("ustawienia: uklad inny niz slownik zerowany",
      Settings(panel_layout="x").normalised().panel_layout == {})
check("ustawienia: domyslnie pusty uklad", Settings().panel_layout == {})

sys.exit(wypisz(results))
