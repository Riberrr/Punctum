"""Znaczniki przy nazwach zdjec - wspolne dla paska miniatur i listy w mapie.

Dwie listy w dwoch zakladkach pokazuja te same pliki, wiec musza mowic tym
samym jezykiem: gdyby kropka w Edycji znaczyla "poprawione", a w Mapie
"ma wspolrzedne", nie dalo by sie ich czytac obok siebie.

Znaczniki sa dwa i sa niezalezne:
    *  praca nad zdjeciem jest zapisana (sa nastawy w sidecarze)
    <>  zdjecie ma wspolrzedne (nadane u nas albo z aparatu)
"""

from __future__ import annotations

EDIT_MARK = "•"  # kropka
GEO_MARK = "◆"  # romb

LEGEND = (
    f"{EDIT_MARK}  zapisane poprawki\n"
    f"{GEO_MARK}  zdjęcie ma współrzędne"
)


def marks(edited: bool, located: bool, pad: bool = False) -> str:
    """Prefiks znacznikow. Z pad=True puste miejsca zostaja jako spacje.

    Wyrownanie ma sens tam, gdzie nazwy stoja jedna pod druga (lista w mapie);
    w pasku miniatur podpis jest wysrodkowany, wiec spacje tylko by go
    przesuwaly.
    """
    blank = " " if pad else ""
    return (EDIT_MARK if edited else blank) + (GEO_MARK if located else blank)


def caption(name: str, edited: bool = False, located: bool = False, pad: bool = False) -> str:
    """Nazwa pliku ze znacznikami z przodu."""
    prefix = marks(edited, located, pad)
    return f"{prefix} {name}" if prefix else name


def strip(text: str) -> str:
    """Sama nazwa - bez znacznikow i bez wyrownania."""
    return text.lstrip(f" {EDIT_MARK}{GEO_MARK}")
