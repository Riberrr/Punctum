"""Przeklad napisow interfejsu (punkt 27) - ta sama zasada co podpowiedzi.

Kluczem jest sam polski tekst: `t("Zapisz")`. Dzieki temu kod czyta sie
jak dotad, a polski nie potrzebuje wlasnego pliku - jest bazowy z definicji.
Kolejny jezyk to `punctum/lang/interfejs.<kod>.json` z parami
polski -> przeklad; brakujacy wpis zostaje po polsku, wiec niepelny
przeklad niczego nie psuje.

Zmiana polskiego tekstu w kodzie gubi jego przeklad - wylapuje to test
(`tools/test_przeklad.py`), ktory zna wszystkie napisy z kodu.

Modul nie zalezy od Qt, bo korzysta z niego tez `core`.
"""

from __future__ import annotations

import glob
import json
import os

LANG_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")
BAZOWY = "pl"
NAZWA_BAZOWEGO = "Polski"

# Liczba mnoga: numer formy dla danej liczby. Polski ma trzy formy
# (1 zdjecie, 2 zdjecia, 5 zdjec), angielski dwie. Jezyk bez reguly
# dostaje angielska - to najczestszy uklad i najmniej razi, gdy sie myli.
REGULY_MNOGIEJ = {
    "pl": lambda n: 0 if n == 1 else (
        1 if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else 2),
    "en": lambda n: 0 if n == 1 else 1,
}

_jezyk = BAZOWY
_katalog: dict[str, str] = {}
_meta: dict[str, str] = {"_separator": ","}


def plik(jezyk: str) -> str:
    return os.path.join(LANG_DIRECTORY, f"interfejs.{jezyk}.json")


def jezyki() -> list[str]:
    """Jezyki z plikiem przekladu na dysku; bazowy zawsze pierwszy."""
    kody = {os.path.basename(p).split(".")[1] for p in glob.glob(plik("*"))}
    return [BAZOWY] + sorted(kody - {BAZOWY})


def wczytaj(jezyk: str) -> tuple[dict[str, str], dict[str, str]]:
    """Wpisy przekladu i metadane pliku (klucze z `_`, np. `_nazwa`)."""
    if jezyk == BAZOWY:
        return {}, {"_nazwa": NAZWA_BAZOWEGO, "_separator": ","}
    try:
        with open(plik(jezyk), encoding="utf-8") as handle:
            dane = json.load(handle)
    except (OSError, ValueError):
        return {}, {}  # uszkodzony plik = zostajemy przy polskim
    wpisy = {k: v for k, v in dane.items() if not k.startswith("_") and v}
    meta = {k: v for k, v in dane.items() if k.startswith("_")}
    return wpisy, meta


def nazwa_jezyka(jezyk: str) -> str:
    """Nazwa jezyka w nim samym - tak wybiera sie jezyk, ktorego sie nie zna."""
    return wczytaj(jezyk)[1].get("_nazwa", jezyk)


def ustaw_jezyk(jezyk: str) -> str:
    """Ustawia jezyk napisow; nieznany kod konczy sie polskim. Zwraca kod."""
    global _jezyk, _katalog, _meta
    _jezyk = jezyk if jezyk in jezyki() else BAZOWY
    _katalog, _meta = wczytaj(_jezyk)
    return _jezyk


def jezyk() -> str:
    return _jezyk


def dobierz_jezyk(zapisany: str, systemowy: str) -> str:
    """Jezyk przy starcie: zapisany w ustawieniach, inaczej systemowy.

    Gdy systemowego nie mamy, angielski - uzytkownik spoza Polski lepiej
    poradzi sobie z nim niz z polskim.
    """
    dostepne = jezyki()
    for kod in (zapisany, systemowy[:2].lower()):
        if kod in dostepne:
            return kod
    return "en" if "en" in dostepne else BAZOWY


def t(tekst: str, **pola) -> str:
    """Napis w biezacym jezyku; pola wstawiane przez `{nazwa}`.

    Pola podaje sie po nazwie, a nie doklejaniem kawalkow - w innym jezyku
    liczba albo nazwa pliku stoja czesto w innym miejscu zdania.
    """
    wynik = _katalog.get(tekst, tekst)
    return wynik.format(**pola) if pola else wynik


def N_(tekst: str) -> str:  # noqa: N802 - nazwa zwyczajowa z gettext
    """Znacznik napisu do przekladu w stalej modulu, tlumaczonej dopiero przy uzyciu.

    Stale licza sie przy imporcie, zanim wiadomo, jaki jest jezyk - dlatego
    trzymaja polski, a `t(stala)` wola sie tam, gdzie napis trafia na ekran.
    """
    return tekst


def mnoga(n: int, formy: str, **pola) -> str:
    """Napis z liczba: `mnoga(n, "{n} zdjecie|{n} zdjecia|{n} zdjec")`.

    Kluczem sa polskie formy rozdzielone `|`; przeklad podaje tyle form,
    ile ma jego jezyk (angielski dwie).
    """
    przeklad = _katalog.get(formy)
    if przeklad:
        warianty = przeklad.split("|")
        regula = REGULY_MNOGIEJ.get(_jezyk, REGULY_MNOGIEJ["en"])
    else:
        warianty = formy.split("|")
        regula = REGULY_MNOGIEJ[BAZOWY]
    wybrany = warianty[min(regula(abs(n)), len(warianty) - 1)]
    return wybrany.format(n=n, **pola)


def liczba(wartosc: float, miejsca: int = 0, znak: bool = False) -> str:
    """Liczba z separatorem dziesietnym biezacego jezyka (2,50 / 2.50)."""
    tekst = f"{wartosc:{'+' if znak else ''}.{miejsca}f}"
    return tekst.replace(".", _meta.get("_separator", "."))
