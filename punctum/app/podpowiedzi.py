"""Podpowiedzi (dymki) calego programu - tu tylko mechanika, teksty w plikach.

Kod zna wylacznie klucze. Teksty leza w `punctum/lang/podpowiedzi.<jezyk>.json`:
polski jest bazowy i kompletny, kazdy kolejny jezyk to jeden dodatkowy plik,
bez zmian w kodzie. Brakujacy wpis albo pole w jezyku docelowym zastepuje
polski - niepelny przeklad niczego nie psuje, najwyzej miesza jezyki.
Ta sama droga ma posluzyc przekladowi calego interfejsu (punkt 27).

Kazdy widzet z podpowiedzia dostaje wlasciwosc z kluczem; po niej test
sprawdza pokrycie i to, ze w katalogu nie wisza teksty, ktorych nikt nie uzywa.
"""

from __future__ import annotations

import glob
import html
import json
import os

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QProxyStyle, QStyle

LANG_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lang")
BAZOWY = "pl"
WLASCIWOSC = "punctum_podpowiedz"
SUWAK = "wspolne.suwak"

# Dluzsze opisy lamiemy na stala szerokosc. Bez tego Qt sklada dymek
# w linie po 80 znakow - czyta sie to jak pasek, nie jak notatke.
SZEROKOSC_PX = 320
DLUGI_OPIS = 70
KOLOR_UWAGI = "#9a9aa0"

_katalogi: dict[str, dict] = {}
# Slowo, od ktorego zaczyna sie rada w opisie ("Rada:", "Tip:") - lamiemy
# przed nim linie, wiec kazdy jezyk podaje wlasne.
_rady: dict[str, str] = {}
_jezyk = BAZOWY


def plik(jezyk: str) -> str:
    return os.path.join(LANG_DIRECTORY, f"podpowiedzi.{jezyk}.json")


def jezyki() -> list[str]:
    """Jezyki, dla ktorych lezy plik z tekstami; bazowy zawsze pierwszy."""
    kody = {os.path.basename(p).split(".")[1] for p in glob.glob(plik("*"))}
    return [BAZOWY] + sorted(kody - {BAZOWY})


def katalog(jezyk: str = BAZOWY) -> dict[str, dict]:
    if jezyk not in _katalogi:
        try:
            with open(plik(jezyk), encoding="utf-8") as handle:
                dane = json.load(handle)
        except (OSError, ValueError):
            if jezyk == BAZOWY:
                raise  # bez bazowego katalogu to blad instalacji, nie brak przekladu
            dane = {}
        # klucze z podkreslnikiem to komentarze i ustawienia pliku (np. "_rada")
        _katalogi[jezyk] = {k: v for k, v in dane.items() if not k.startswith("_")}
        _rady[jezyk] = dane.get("_rada", "Rada:")
    return _katalogi[jezyk]


def ustaw_jezyk(jezyk: str) -> None:
    global _jezyk
    _jezyk = jezyk if jezyk in jezyki() else BAZOWY


def wpis(klucz: str) -> dict[str, str]:
    """Wpis w biezacym jezyku, uzupelniony polskim pole po polu.

    Nieznany klucz to blad w kodzie, nie w przekladzie - KeyError ma go
    wywrocic od razu, a nie pokazac pusty dymek.
    """
    bazowy = katalog(BAZOWY)[klucz]
    if _jezyk == BAZOWY:
        return bazowy
    return {**bazowy, **katalog(_jezyk).get(klucz, {})}


def tekst(klucz: str, suwak: bool = False, dopisek: str | None = None) -> str:
    """Dymek jako rich text: pogrubiony tytul, opis, szara linia uwag."""
    w = wpis(klucz)
    opis = w.get("opis", "")
    if dopisek:
        opis = f"{opis} {wpis(dopisek).get('opis', '')}".strip()
    # Suwak dostaje wspolna linie o dwukliku i kolku; wpis moze ja zastapic
    # wlasna ("uwaga_suwaka"), gdy dwuklik wraca do czegos innego niz zero.
    uwagi = [w.get("uwaga_suwaka") or wpis(SUWAK)["uwaga"]] if suwak else []
    if w.get("uwaga"):
        uwagi.append(w["uwaga"])

    czesci = []
    if w.get("tytul"):
        czesci.append(f"<b>{html.escape(w['tytul'])}</b>")
    if opis:
        # rada w osobnej linii - wtedy dzialanie i wskazowka nie zlewaja sie
        katalog(_jezyk)  # wczytuje tez slowo rady tego jezyka
        rada = _rady.get(_jezyk, "Rada:")
        czesci.append(html.escape(opis).replace(f" {rada}", f"<br>{rada}"))
    tresc = "<br>".join(czesci)
    if uwagi:
        # kreska oddziela opis od "instrukcji obslugi" (skroty, gesty, format)
        tresc += (f"<hr><span style='color:{KOLOR_UWAGI}'>"
                  f"{html.escape(' · '.join(uwagi))}</span>")
    if len(opis) > DLUGI_OPIS:
        tresc = (f"<table width='{SZEROKOSC_PX}' cellspacing='0' cellpadding='0'>"
                 f"<tr><td>{tresc}</td></tr></table>")
    return f"<qt>{tresc}</qt>"


def podpowiedz(widget, klucz: str, *, suwak: bool = False, dopisek: str | None = None,
               etykieta=None) -> None:
    """Przypina podpowiedz do widzetu (i do jego etykiety w formularzu).

    Etykieta dostaje ten sam dymek, bo w formularzu naturalnie najezdza sie
    na napis, a nie na pole obok niego.
    """
    tresc = tekst(klucz, suwak=suwak, dopisek=dopisek)
    widget.setToolTip(tresc)
    widget.setProperty(WLASCIWOSC, klucz)
    if etykieta is not None:
        etykieta.setToolTip(tresc)


def podpowiedz_wiersza(form, pole, klucz: str) -> None:
    """Podpowiedz dla pola formularza i jego etykiety (QFormLayout)."""
    podpowiedz(pole, klucz, etykieta=form.labelForField(pole))


class StylPodpowiedzi(QProxyStyle):
    """Nakladka na styl aplikacji, ktora podaje wlasne opoznienie dymka.

    Qt nie ma do tego osobnego ustawienia - czas czytany jest ze stylu
    (SH_ToolTip_WakeUpDelay) przy kazdym ruchu myszy, wiec zmiana pola
    `opoznienie_ms` dziala od razu. Nakladka na styl o tej samej nazwie,
    zeby wyglad okien sie nie zmienil.
    """

    def __init__(self, nazwa_stylu: str, opoznienie_ms: int = 700):
        super().__init__(nazwa_stylu)
        self.opoznienie_ms = opoznienie_ms

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return self.opoznienie_ms
        return super().styleHint(hint, option, widget, returnData)


class WylacznikPodpowiedzi(QObject):
    """Filtr zdarzen na calej aplikacji: gdy podpowiedzi sa wylaczone,
    zjada zdarzenie ToolTip, zanim dotrze do widzetu.

    Filtr zamiast czyszczenia tekstow: wlaczenie z powrotem dziala od razu,
    bez odtwarzania dymkow w kazdym oknie.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wlaczone = True

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - nazwa z Qt
        return event.type() == QEvent.ToolTip and not self.wlaczone
