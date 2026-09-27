"""Slad GPS z pliku GPX i dopasowanie do niego zdjec po czasie.

Aparat zapisuje czas "z zegarka na scianie": bez strefy i czesto
z kilkuminutowym bledem. GPX podaje czas UTC. Dlatego dopasowanie zawsze
bierze przesuniecie (strefa aparatu plus poprawka jego zegara) od
uzytkownika, a my podpowiadamy tylko strefe systemu z dnia zdjecia.
"""

from __future__ import annotations

import bisect
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Tyle punktow wysylamy na mape do narysowania linii. Slad z zegarka
# potrafi miec sto tysiecy punktow, a linia z dwoch tysiecy wyglada tak samo.
PUNKTY_NA_MAPE = 2000


@dataclass(frozen=True)
class Punkt:
    czas: datetime  # UTC, ze strefa
    lat: float
    lon: float


def _nazwa(element) -> str:
    # GPX 1.0 i 1.1 maja rozne przestrzenie nazw, a programy dopisuja
    # wlasne - porownujemy wiec sama nazwe znacznika.
    return element.tag.rsplit("}", 1)[-1]


def _czas_gpx(tekst: str) -> datetime:
    tekst = tekst.strip()
    if tekst.endswith("Z"):
        tekst = tekst[:-1] + "+00:00"
    czas = datetime.fromisoformat(tekst)
    if czas.tzinfo is None:  # GPX z definicji podaje UTC
        czas = czas.replace(tzinfo=timezone.utc)
    return czas.astimezone(timezone.utc)


class Slad:
    """Punkty sladu posortowane po czasie, z szybkim szukaniem sasiadow."""

    def __init__(self, punkty: list[Punkt]):
        self.punkty = sorted(punkty, key=lambda p: p.czas)
        self._czasy = [p.czas for p in self.punkty]

    def __len__(self) -> int:
        return len(self.punkty)

    @property
    def poczatek(self) -> datetime | None:
        return self._czasy[0] if self._czasy else None

    @property
    def koniec(self) -> datetime | None:
        return self._czasy[-1] if self._czasy else None

    def polozenie(self, czas_utc: datetime, tolerancja: timedelta) -> tuple[float, float] | None:
        """Wspolrzedne w danej chwili albo None, gdy slad wtedy milczal.

        Miedzy dwoma bliskimi punktami interpolujemy liniowo. Gdy odbiornik
        mial dziure (tunel, wylaczony zegarek) dluzsza niz tolerancja, nie
        zgadujemy polozenia z prostej przez pol kraju - bierzemy najblizszy
        punkt, o ile jest dosc blisko w czasie.
        """
        if not self.punkty:
            return None
        i = bisect.bisect_left(self._czasy, czas_utc)
        przed = self.punkty[i - 1] if i > 0 else None
        po = self.punkty[i] if i < len(self.punkty) else None
        if po is not None and po.czas == czas_utc:
            return po.lat, po.lon
        blisko_przed = przed is not None and czas_utc - przed.czas <= tolerancja
        blisko_po = po is not None and po.czas - czas_utc <= tolerancja
        if blisko_przed and blisko_po:
            udzial = (czas_utc - przed.czas) / (po.czas - przed.czas)
            return (przed.lat + (po.lat - przed.lat) * udzial,
                    przed.lon + (po.lon - przed.lon) * udzial)
        if blisko_przed or blisko_po:
            if not blisko_po or (blisko_przed and czas_utc - przed.czas <= po.czas - czas_utc):
                return przed.lat, przed.lon
            return po.lat, po.lon
        return None

    def do_mapy(self) -> list[list[float]]:
        """Przerzedzona lista [lat, lon] do narysowania linii."""
        krok = max(1, len(self.punkty) // PUNKTY_NA_MAPE)
        wybrane = self.punkty[::krok]
        if self.punkty and wybrane[-1] is not self.punkty[-1]:
            wybrane.append(self.punkty[-1])
        return [[round(p.lat, 6), round(p.lon, 6)] for p in wybrane]


def wczytaj_gpx(sciezka: str) -> Slad:
    """Punkty z czasem ze sladow i tras. Punkty bez czasu nic nie dopasuja."""
    punkty: list[Punkt] = []
    for element in ET.parse(sciezka).iter():
        if _nazwa(element) not in ("trkpt", "rtept"):
            continue
        czas = next((c.text for c in element if _nazwa(c) == "time" and c.text), None)
        if czas is None:
            continue
        try:
            punkty.append(Punkt(_czas_gpx(czas), float(element.get("lat")),
                                float(element.get("lon"))))
        except (TypeError, ValueError):
            continue  # jeden zepsuty punkt nie przekresla calego sladu
    return Slad(punkty)


# Wspolrzedne wklejane ze schowka: "50.0686, 22.2290" (Google Maps, nasza
# kopia) albo po polsku "50,0686 22,2290". Przy przecinku dziesietnym
# separatorem musi byc odstep, inaczej "50,06,22,22" byloby nie do rozplatania.
_KROPKA = re.compile(r"(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)")
_PRZECINEK = re.compile(r"(-?\d{1,3},\d+)\s*[;\s]\s*(-?\d{1,3},\d+)")


def wspolrzedne_z_tekstu(tekst: str) -> tuple[float, float] | None:
    """Szerokosc i dlugosc z wklejonego tekstu albo None."""
    tekst = (tekst or "").strip()
    for wzor in (_PRZECINEK, _KROPKA):
        dopasowanie = wzor.fullmatch(tekst)
        if dopasowanie:
            lat, lon = (float(x.replace(",", ".")) for x in dopasowanie.groups())
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                return lat, lon
    return None


def strefa_systemu(czas_lokalny: datetime | None) -> timedelta:
    """Przesuniecie strefy komputera w dniu zdjecia (z czasem letnim)."""
    czas = czas_lokalny or datetime.now()
    return czas.astimezone().utcoffset() or timedelta(0)


def dopasuj(slad: Slad, czasy: dict[str, datetime], przesuniecie: timedelta,
            tolerancja: timedelta) -> dict[str, tuple[float, float]]:
    """Zdjecia (czas z aparatu, bez strefy) -> wspolrzedne ze sladu.

    `przesuniecie` to o ile czas aparatu wyprzedza UTC: strefa plus
    ewentualny blad zegara. Zdjecia spoza sladu po prostu nie trafiaja
    do wyniku.
    """
    wynik: dict[str, tuple[float, float]] = {}
    for sciezka, czas in czasy.items():
        if czas is None:
            continue
        utc = (czas.replace(tzinfo=None) - przesuniecie).replace(tzinfo=timezone.utc)
        miejsce = slad.polozenie(utc, tolerancja)
        if miejsce is not None:
            wynik[sciezka] = miejsce
    return wynik
