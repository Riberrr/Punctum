"""Presety: zapisane zestawy nastaw, nakladane jednym ruchem.

Preset trzyma tylko wybrane grupy suwakow (np. sam kolor i monochrom), nie
komplet `EditParams`. Dzieki temu kladzie sie na to, co juz jest na
zdjeciu - na wynik automatu albo reczne poprawki ekspozycji - zamiast je
nadpisywac. Geometria, lokalizacja i metadane nie naleza do zadnej grupy:
kadr z jednego zdjecia nic nie znaczy na innym.

Wlasne presety leza po jednym w pliku JSON w katalogu ustawien; ten sam
plik jest formatem eksportu i importu, wiec wymiana presetu to skopiowanie
pliku.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .params import MONO_FIELDS
from .settings import config_directory
from ..przeklad import N_

FORMAT = "punctum-preset"
WERSJA = 1
ROZSZERZENIE = ".json"

# Grupy w kolejnosci sekcji w panelu. Klucze sa takie jak klucze sekcji
# (app/panele.py), zeby nazwy grup w oknie zapisu byly tymi samymi, ktore
# fotograf widzi nad suwakami.
GRUPY: dict[str, tuple[str, ...]] = {
    "balans": ("temperature", "tint"),
    "ton": ("exposure", "contrast", "highlights", "shadows", "whites", "blacks"),
    "obecnosc": ("vibrance", "saturation"),
    "monochrom": ("mono", *MONO_FIELDS),
    "wyostrzanie": ("sharpen_amount", "sharpen_radius", "sharpen_detail", "sharpen_masking"),
    "szum": ("noise_luminance", "noise_color"),
}

# Domyslnie zaznaczone przy zapisie: wyglad zdjecia. Balans bieli, ostrosc
# i szum zaleza od swiatla i ISO konkretnego ujecia - przeniesione na inne
# zdjecie czesciej szkodza, niz pomagaja.
GRUPY_DOMYSLNE = ("ton", "obecnosc", "monochrom")

# Zakresy suwakow, do przyciecia wartosci z obcego pliku.
_ZAKRESY = {
    "temperature": (2000.0, 15000.0),
    "tint": (-100.0, 100.0),
    "exposure": (-5.0, 5.0),
    "sharpen_amount": (0.0, 150.0),
    "sharpen_radius": (0.5, 3.0),
    "sharpen_detail": (0.0, 100.0),
    "sharpen_masking": (0.0, 100.0),
    "noise_luminance": (0.0, 100.0),
    "noise_color": (0.0, 100.0),
}
_ZAKRES_DOMYSLNY = (-100.0, 100.0)

# Klasyczne filtry do fotografii czarno-bialej, jako nastawy suwakow barw
# (czerwien, zolc, ziele, turkus, blekit, fiolet). Filtr przepuszcza swoja
# barwe i barwy sasiednie (jasnieja), a zatrzymuje dopelniajaca (ciemnieje):
# zolty przyciemnia niebo, czerwony robi z niego prawie czern, zielony
# rozjasnia liscie i przyciemnia skore.
FILTRY: dict[str, tuple[float, float, float, float, float, float]] = {
    "zolty": (15.0, 30.0, 10.0, -10.0, -40.0, -15.0),
    "pomaranczowy": (40.0, 30.0, -10.0, -30.0, -60.0, -5.0),
    "czerwony": (60.0, 20.0, -30.0, -50.0, -80.0, 20.0),
    "zielony": (-30.0, 10.0, 50.0, 10.0, -20.0, -40.0),
}


def wartosci_filtra(klucz: str) -> dict[str, float]:
    return dict(zip(MONO_FIELDS, FILTRY[klucz]))


@dataclass
class Preset:
    nazwa: str
    wartosci: dict[str, float | bool] = field(default_factory=dict)
    wbudowany: bool = False
    plik: str | None = None  # tylko wlasne

    def etykieta(self) -> str:
        """Nazwa na ekranie. Wbudowane ida przez przeklad, wlasne nie -
        to tekst wpisany przez uzytkownika."""
        if self.wbudowany:
            from ..przeklad import t
            return t(self.nazwa)
        return self.nazwa


# Wbudowane presety wylaczaja albo wlaczaja monochrom jawnie: "Zywy"
# nalozony na zdjecie czarno-biale ma dac kolor, nie podbite nasycenie,
# ktorego nie widac.
WBUDOWANE = (
    Preset(N_("Żywy"), {"mono": False, "contrast": 12.0, "vibrance": 35.0,
                        "saturation": 8.0}, wbudowany=True),
    Preset(N_("Stonowany"), {"mono": False, "contrast": -12.0, "highlights": -15.0,
                             "vibrance": -25.0, "saturation": -10.0}, wbudowany=True),
    Preset(N_("Monochrom"), {"mono": True, "contrast": 10.0,
                             **dict.fromkeys(MONO_FIELDS, 0.0)}, wbudowany=True),
    Preset(N_("Monochrom kontrastowy"), {"mono": True, "contrast": 25.0,
                                         **wartosci_filtra("czerwony")}, wbudowany=True),
)


def wartosci_z_grup(params, grupy) -> dict[str, float | bool]:
    """Wycina z nastaw pola wybranych grup - tresc nowego presetu."""
    wynik: dict[str, float | bool] = {}
    for grupa in grupy:
        for pole in GRUPY[grupa]:
            wynik[pole] = getattr(params, pole)
    return wynik


def _oczysc(dane) -> dict[str, float | bool]:
    """Zostawia tylko znane pola z sensownymi wartosciami.

    Plik mogl przyjsc od kogos innego albo z nowszej wersji programu -
    nieznane pola pomijamy, liczby przycinamy do zakresu suwaka.
    """
    znane = {pole for pola in GRUPY.values() for pole in pola}
    wynik: dict[str, float | bool] = {}
    if not isinstance(dane, dict):
        return wynik
    for pole, wartosc in dane.items():
        if pole not in znane:
            continue
        if pole == "mono":
            wynik[pole] = bool(wartosc)
        elif pole == "temperature" and wartosc is None:
            wynik[pole] = None  # "jak na ujeciu"
        elif isinstance(wartosc, (int, float)) and not isinstance(wartosc, bool):
            lo, hi = _ZAKRESY.get(pole, _ZAKRES_DOMYSLNY)
            wynik[pole] = min(max(float(wartosc), lo), hi)
    return wynik


# ------------------------------------------------------------------ pliki


def katalog_presetow(baza: str | None = None) -> str:
    return os.path.join(baza or config_directory(), "presety")


def nazwa_pliku(nazwa: str) -> str:
    """Nazwa pliku z nazwy presetu: bez znakow, ktorych Windows nie przyjmie."""
    czysta = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nazwa).strip(" .") or "preset"
    return czysta[:80] + ROZSZERZENIE


def wczytaj_plik(sciezka: str) -> Preset | None:
    """Preset z pliku; None, gdy plik nie jest presetem Punctum."""
    try:
        with open(sciezka, encoding="utf-8") as plik:
            dane = json.load(plik)
    except (OSError, ValueError):
        return None
    if not isinstance(dane, dict) or dane.get("format") != FORMAT:
        return None
    nazwa = str(dane.get("nazwa", "")).strip()
    wartosci = _oczysc(dane.get("wartosci"))
    if not nazwa or not wartosci:
        return None
    return Preset(nazwa, wartosci, plik=sciezka)


def zapisz_plik(preset: Preset, sciezka: str) -> bool:
    dane = {"format": FORMAT, "wersja": WERSJA, "nazwa": preset.nazwa,
            "wartosci": preset.wartosci}
    try:
        os.makedirs(os.path.dirname(sciezka) or ".", exist_ok=True)
        tymczasowy = sciezka + ".tmp"
        with open(tymczasowy, "w", encoding="utf-8") as plik:
            json.dump(dane, plik, ensure_ascii=False, indent=2)
        os.replace(tymczasowy, sciezka)
        return True
    except OSError:
        return False


def wlasne(baza: str | None = None) -> list[Preset]:
    """Wlasne presety uzytkownika, po nazwie."""
    katalog = katalog_presetow(baza)
    try:
        pliki = sorted(os.listdir(katalog))
    except OSError:
        return []
    wynik = [wczytaj_plik(os.path.join(katalog, p)) for p in pliki if p.endswith(ROZSZERZENIE)]
    return sorted((p for p in wynik if p is not None), key=lambda p: p.nazwa.casefold())


def zapisz_wlasny(nazwa: str, wartosci: dict, baza: str | None = None) -> Preset | None:
    """Zapisuje (albo nadpisuje) wlasny preset o tej nazwie."""
    sciezka = os.path.join(katalog_presetow(baza), nazwa_pliku(nazwa))
    preset = Preset(nazwa.strip(), _oczysc(wartosci), plik=sciezka)
    if not preset.nazwa or not preset.wartosci:
        return None
    return preset if zapisz_plik(preset, sciezka) else None


def importuj(sciezka: str, baza: str | None = None) -> Preset | None:
    """Kopiuje preset z pliku do wlasnych. Istniejacy o tej nazwie nadpisuje."""
    preset = wczytaj_plik(sciezka)
    if preset is None:
        return None
    return zapisz_wlasny(preset.nazwa, preset.wartosci, baza)


def usun(preset: Preset) -> bool:
    if preset.wbudowany or not preset.plik:
        return False
    try:
        os.remove(preset.plik)
        return True
    except OSError:
        return False


def istnieje(nazwa: str, baza: str | None = None) -> bool:
    return os.path.exists(os.path.join(katalog_presetow(baza), nazwa_pliku(nazwa)))


def wszystkie(baza: str | None = None) -> list[Preset]:
    return [*WBUDOWANE, *wlasne(baza)]
