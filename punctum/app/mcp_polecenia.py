"""Dzialanie narzedzi MCP na otwartym oknie Punctum.

Serwer HTTP (mcp/protokol.py) przyjmuje wywolania we wlasnych watkach.
Wszystko, co dotyka okna - suwaki, historie, pasek miniatur, sidecary
zapisywane przez okno - wykonuje sie w watku GUI przez `w_gui`; ciezkie
liczenie bez okna (wczytanie RAW-a, automat, kodowanie JPEG podgladu)
zostaje w watku serwera, zeby okno nie stawalo.

Zmiana nastaw idzie tymi samymi drogami co reka uzytkownika: biezace
zdjecie przez `EditPanel.load_params` + krok historii + sidecar, pozostale
wprost do `edits` i sidecara, z krokiem w ich historii - Ctrl+Z po
otwarciu takiego zdjecia cofa zmiane zrobiona przez AI.
"""

from __future__ import annotations

import base64
import copy
import io
import os
import threading
import time
from datetime import datetime
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, Qt, Signal, Slot

from ..core import (
    auto_tone, default_params_for, develop, develop_region, geometry_size, is_jpeg, load_photo,
)
from ..core import presety
from ..core.denoise import apply_detail
from ..core.params import MONO_FIELDS, EditParams
from ..mcp import narzedzia
from ..mcp.protokol import (
    BladNarzedzia, SerwerMCP, dane, obraz, tekst, token_z_pliku, zapisz_polaczenie,
)

PELNY_KADR = (0.0, 0.0, 1.0, 1.0)

# Tyle miejsc po przecinku maja suwaki. Wartosc zapisana dokladniej niz suwak
# pokazuje zmienilaby sie przy pierwszym otwarciu zdjecia (suwak ja zaokragli)
# i historia dostalaby pusty krok.
MIEJSCA = {"exposure": 2, "sharpen_radius": 1, "rotation": 1}

# Domyslnie kopiujemy wszystko poza balansem bieli - balans zalezy od swiatla
# konkretnego ujecia (ta sama decyzja co GRUPY_DOMYSLNE presetow).
GRUPY_KOPIOWANIA = ("ton", "obecnosc", "monochrom", "wyostrzanie", "szum")


class _WatekGUI(QObject):
    """Przenosi wywolanie z watku serwera do watku okna."""

    zadanie = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zadanie.connect(self._wykonaj, Qt.QueuedConnection)

    @Slot(object)
    def _wykonaj(self, funkcja) -> None:
        funkcja()


def _kopia(p: EditParams) -> EditParams:
    return copy.deepcopy(p)


def _stan(p: EditParams) -> EditParams:
    """Stan do historii - bez lokalizacji i metadanych, jak `_stan_edycji`."""
    s = _kopia(p)
    s.latitude = s.longitude = None
    s.metadata = {}
    return s


def _ustaw(p: EditParams, pole: str, wartosc: float) -> None:
    lo, hi = narzedzia.ZAKRESY[pole]
    wartosc = round(min(hi, max(lo, float(wartosc))), MIEJSCA.get(pole, 0))
    setattr(p, pole, wartosc)
    # Jak w panelu: ruch suwaka barwy wlacza monochrom, inaczej zmiana
    # bylaby niewidoczna i model uznalby, ze narzedzie nie dziala.
    if pole in MONO_FIELDS:
        p.mono = True


def _data(tekst_daty: str, koniec: bool) -> datetime:
    tekst_daty = tekst_daty.strip().replace("T", " ")
    for wzor in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            chwila = datetime.strptime(tekst_daty, wzor)
        except ValueError:
            continue
        if wzor == "%Y-%m-%d" and koniec:
            chwila = chwila.replace(hour=23, minute=59, second=59)
        return chwila
    raise BladNarzedzia(f"Cannot read date '{tekst_daty}', use YYYY-MM-DD or YYYY-MM-DD HH:MM.")


def _proporcja(tekst_proporcji: str) -> float:
    try:
        a, b = tekst_proporcji.replace("x", ":").replace("/", ":").split(":")
        wynik = float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        raise BladNarzedzia(f"Cannot read aspect ratio '{tekst_proporcji}', use e.g. '3:2'.")
    if not 0.1 <= wynik <= 10:
        raise BladNarzedzia("Aspect ratio out of range.")
    return wynik


def kadr_o_proporcji(szer: int, wys: int, proporcja: float) -> tuple[float, float, float, float]:
    """Najwiekszy wysrodkowany kadr o danej proporcji, jako ulamki obrazu.

    Proporcje podaje sie jak na odbitce ("3:2"), a zdjecie pionowe tez ma
    wyjsc pionowe - dlatego proporcja jest odwracana dla pionu.
    """
    if (wys > szer) != (proporcja < 1) and abs(proporcja - 1) > 1e-6:
        proporcja = 1 / proporcja
    if szer / wys > proporcja:
        ulamek = proporcja * wys / szer
        return ((1 - ulamek) / 2, 0.0, (1 + ulamek) / 2, 1.0)
    ulamek = szer / proporcja / wys
    return (0.0, (1 - ulamek) / 2, 1.0, (1 + ulamek) / 2)


class PoleceniaMCP:
    """Serwer MCP przypiety do glownego okna."""

    LIMIT_GUI_S = 120

    def __init__(self, okno):
        self.okno = okno
        self._gui = _WatekGUI(okno)
        # Jedno narzedzie naraz: dwa rownolegle wywolania ruszalyby te same
        # suwaki i historie w przeplocie.
        self._jedno = threading.Lock()
        self.serwer: SerwerMCP | None = None

    # ------------------------------------------------------------ serwer

    def uruchom(self, port: int, katalog: str | None = None) -> str | None:
        """Startuje serwer; zwraca opis bledu albo None."""
        token = token_z_pliku(katalog)
        try:
            self.serwer = SerwerMCP(self.wykonaj, token, port)
        except OSError as exc:
            return str(exc)
        zapisz_polaczenie(self.serwer.port, token, katalog)
        self.serwer.uruchom()
        return None

    def zatrzymaj(self) -> None:
        if self.serwer is not None:
            self.serwer.zatrzymaj()
            self.serwer = None

    def w_gui(self, funkcja: Callable[[], Any], limit: float | None = None) -> Any:
        """Wykonuje funkcje w watku okna i czeka na wynik."""
        if threading.current_thread() is threading.main_thread():
            return funkcja()  # testy wolaja narzedzia wprost
        gotowe = threading.Event()
        wynik: dict[str, Any] = {}

        def zadanie() -> None:
            try:
                wynik["w"] = funkcja()
            except BaseException as exc:  # przekazujemy do watku serwera
                wynik["e"] = exc
            finally:
                gotowe.set()

        self._gui.zadanie.emit(zadanie)
        if not gotowe.wait(limit or self.LIMIT_GUI_S):
            raise BladNarzedzia("Punctum window did not respond in time (busy?).")
        if "e" in wynik:
            raise wynik["e"]
        return wynik.get("w")

    def _czekaj(self, warunek: Callable[[], Any], limit: float, opis: str) -> Any:
        koniec = time.monotonic() + limit
        while True:
            wynik = self.w_gui(warunek)
            # Porownanie z None/False, nie "if wynik": warunek moze oddac
            # tablice numpy (obraz), a ta nie ma wartosci logicznej.
            if wynik is not None and wynik is not False:
                return wynik
            if time.monotonic() > koniec:
                raise BladNarzedzia(f"Timed out waiting for {opis}.")
            if threading.current_thread() is threading.main_thread():
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            time.sleep(0.05)

    def wykonaj(self, nazwa: str, argumenty: dict) -> list[dict]:
        metoda = getattr(self, "n_" + nazwa, None)
        if metoda is None:
            raise BladNarzedzia(f"Tool {nazwa} is not available in this version.")
        with self._jedno:
            return metoda(argumenty)

    # ---------------------------------------------------------- pomocnicze
    # (wszystkie ponizej wolane w watku GUI)

    def _sciezka(self, nazwa: str) -> str:
        nazwa = os.path.basename(str(nazwa)).lower()
        for sciezka in self.okno.folder_paths:
            if os.path.basename(sciezka).lower() == nazwa:
                return sciezka
        raise BladNarzedzia(f"No photo named '{nazwa}' in the open folder.")

    def _cele(self, arg: dict) -> list[str]:
        o = self.okno
        if arg.get("photos"):
            return [self._sciezka(n) for n in arg["photos"]]
        if arg.get("target") == "selected":
            wybrane = o.filmstrip.selected_paths()
            if not wybrane:
                raise BladNarzedzia("No photos are selected in the filmstrip.")
            return wybrane
        if not o.current_path:
            raise BladNarzedzia("No photo is open. Use open_photo or pass `photos`.")
        return [o.current_path]

    def _nastawy(self, sciezka: str) -> EditParams:
        o = self.okno
        if sciezka == o.current_path and o.full_raw is not None:
            return o.export_params()
        return _kopia(o._params_for(sciezka) or default_params_for(sciezka))

    def _zmien(self, sciezki: list[str], zmiana: Callable[[EditParams, str], EditParams]) -> list[str]:
        """Naklada zmiane na zdjecia; kazde dostaje jeden krok historii."""
        o = self.okno
        zmienione = []
        for s in sciezki:
            stary = self._nastawy(s)
            nowy = zmiana(_kopia(stary), s)
            if _stan(nowy) == _stan(stary):
                continue
            zmienione.append(os.path.basename(s))
            if s == o.current_path and o.full_raw is not None:
                o._zatwierdz_krok(sila=True)
                o.orientation, o.crop = nowy.orientation, nowy.crop
                o.edit_panel.load_params(nowy)
                o.view.set_crop_fractions(o.crop)
                o.view.set_rotation(nowy.rotation)
                o.edits[s] = o.export_params()
                o._store_edits(s)
                o._zatwierdz_krok(sila=True)
                o._render_preview()
            else:
                o.historia.zapamietaj(s, _stan(stary))
                o.historia.zapamietaj(s, _stan(nowy))
                o.edits[s] = nowy
                o._store_edits(s)
        o._odswiez_historie()
        return zmienione

    def _opis(self, s: str, poprawione: set[str], wybrane: set[str]) -> dict:
        o = self.okno
        m = o.metadata.get(s)
        opis: dict[str, Any] = {
            "name": os.path.basename(s),
            "format": "jpeg" if is_jpeg(s) else "raw",
            "edited": s in poprawione,
            "located": o._has_location(s),
            "selected": s in wybrane,
            "open": s == o.current_path,
        }
        if m is None:
            opis["exif"] = "not read yet"
        else:
            opis.update({
                "date": m.shot_at.strftime("%Y-%m-%d %H:%M:%S") if m.shot_at else None,
                "camera": m.camera or None, "lens": m.lens or None, "iso": m.iso,
                "shutter": m.shutter_text, "aperture": m.aperture_text,
                "focal_length": m.focal_text, "exposure_bias": m.exposure_bias,
            })
        return opis

    @staticmethod
    def _nastawy_jako_dane(p: EditParams) -> dict:
        d = p.to_dict()
        if d.get("temperature") is None:
            d["temperature"] = "as shot"
        if not d.get("metadata"):
            d.pop("metadata", None)
        return d

    # ------------------------------------------------------- 1. rozpoznanie

    def n_get_status(self, arg: dict) -> list[dict]:
        def stan() -> dict:
            o = self.okno
            katalog = os.path.dirname(o.folder_paths[0]) if o.folder_paths else None
            return {
                "folder": katalog,
                "photos_in_folder": len(o.folder_paths),
                "photos_in_filmstrip": len(o.paths),
                "format_filter": o.settings.format_filter,
                "open_photo": os.path.basename(o.current_path) if o.current_path else None,
                "open_photo_loaded": o.full_raw is not None,
                "selected": [os.path.basename(s) for s in o.filmstrip.selected_paths()],
                "edited_count": o.filmstrip.edited_count(),
                "edits_saved_next_to_photos": o.settings.store_edits,
            }
        return [dane(self.w_gui(stan))]

    def n_list_photos(self, arg: dict) -> list[dict]:
        od = max(0, int(arg.get("offset", 0)))
        ile = min(1000, max(1, int(arg.get("limit", 200))))

        def lista() -> dict:
            o = self.okno
            wybrane = set(o.filmstrip.selected_paths())
            poprawione = o.filmstrip.edited_paths()
            sciezki = [s for s in o.paths if s in wybrane] if arg.get("only_selected") else o.paths
            return {
                "total": len(sciezki), "offset": od,
                "photos": [self._opis(s, poprawione, wybrane) for s in sciezki[od:od + ile]],
            }
        return [dane(self.w_gui(lista))]

    def n_get_photo_info(self, arg: dict) -> list[dict]:
        def info() -> dict:
            o = self.okno
            s = self._sciezka(arg["photo"]) if arg.get("photo") else o.current_path
            if not s:
                raise BladNarzedzia("No photo is open; pass `photo`.")
            opis = self._opis(s, o.filmstrip.edited_paths(), set(o.filmstrip.selected_paths()))
            opis["adjustments"] = self._nastawy_jako_dane(self._nastawy(s))
            if s == o.current_path and o.full_raw is not None:
                opis["size"] = [o.full_raw.raw_width, o.full_raw.raw_height]
                opis["as_shot_temperature"] = round(o.edit_panel._as_shot_temp)
            return opis
        return [dane(self.w_gui(info))]

    def _obraz_biezacy(self) -> np.ndarray:
        def gotowy():
            o = self.okno
            if not o.current_path:
                raise BladNarzedzia("No photo is open. Use open_photo first.")
            if o._failed_path == o.current_path:
                raise BladNarzedzia("The open photo could not be loaded.")
            return None if o.current_image is None else o.current_image.copy()
        return self._czekaj(gotowy, 30, "the photo to load")

    def n_get_preview(self, arg: dict) -> list[dict]:
        bok = min(2048, max(256, int(arg.get("max_size", 1200))))
        widok = arg.get("view", "after")
        if widok not in ("after", "before", "side_by_side"):
            raise BladNarzedzia("view must be after, before or side_by_side.")
        podglad = self._obraz_biezacy()

        def stan() -> tuple:
            o = self.okno
            return (os.path.basename(o.current_path), o.full_raw, o.proxy,
                    o.display_params(), o._before_params(), o.settings.preview_noise_quality,
                    o._podglad_dokladka)
        nazwa, raw, proxy, nastawy, przed_nastawy, jakosc, dokladka = self.w_gui(stan)
        if raw is None:
            raise BladNarzedzia("The open photo is still loading.")
        szer, wys = geometry_size(raw, nastawy)
        wycinek = arg.get("crop_100")

        if wycinek:
            bok_w = int(min(1024, max(128, int(wycinek.get("size", 600))), szer, wys))
            x = int(float(wycinek.get("x", 0.5)) * szer) - bok_w // 2
            y = int(float(wycinek.get("y", 0.5)) * wys) - bok_w // 2
            prostokat = (min(max(0, x), szer - bok_w), min(max(0, y), wys - bok_w), bok_w, bok_w)
            po = develop_region(raw, nastawy, prostokat, 1.0, denoise=True, quality="balanced")
            przed = (develop_region(raw, przed_nastawy, prostokat, 1.0, denoise=False)
                     if widok != "after" else None)
            opis = f"{nazwa} - 1:1 crop {bok_w}x{bok_w} px at ({prostokat[0]}, {prostokat[1]})"
        else:
            # Podglad w oknie liczy odszumianie i wyostrzanie z opoznieniem
            # (osobny przebieg) - tu dokladamy je od razu, zeby model widzial
            # to samo co uzytkownik po chwili.
            po = podglad
            skala = po.shape[1] / float(max(1, szer))
            # Okno wie, czego podgladowi brakuje (kolor mogla juz odszumic
            # karta, a przebieg procesora mogl juz dojsc) - bez tego
            # odszumialibysmy drugi raz.
            if dokladka is not None and dokladka.needs_detail_pass(skala):
                po = apply_detail(po, dokladka, jakosc, skala)
            przed = develop(proxy, przed_nastawy, denoise=False) if widok != "after" else None
            opis = f"{nazwa} - whole frame ({szer}x{wys} px full size)"

        if widok == "before":
            wynik, opis = przed, opis + ", BEFORE adjustments."
        elif widok == "side_by_side":
            wynik, opis = _obok_siebie(przed, po), opis + ", left = before, right = after."
        else:
            wynik, opis = po, opis + ", with current adjustments."
        return [tekst(opis), obraz(_jpeg(wynik, min(2048, bok * 2) if widok == "side_by_side"
                                         else bok))]

    def n_get_image_stats(self, arg: dict) -> list[dict]:
        return [dane(statystyki(self._obraz_biezacy()))]

    # --------------------------------------------------------- 2. nawigacja

    def n_open_folder(self, arg: dict) -> list[dict]:
        katalog = str(arg.get("path", ""))
        if not os.path.isdir(katalog):
            raise BladNarzedzia(f"Folder does not exist: {katalog}")
        self.w_gui(lambda: self.okno.load_folder(katalog))
        liczba = self.w_gui(lambda: len(self.okno.paths))
        if liczba:
            try:
                self._czekaj(lambda: self.okno.full_raw is not None
                             or self.okno._failed_path == self.okno.current_path,
                             30, "the first photo")
            except BladNarzedzia:
                pass  # katalog jest otwarty, zdjecie doczyta sie samo
        return self.n_get_status({})

    def n_open_photo(self, arg: dict) -> list[dict]:
        def otworz() -> str:
            o = self.okno
            s = self._sciezka(arg["photo"])
            if s in o.paths:
                # Przez pasek miniatur, zeby zaznaczenie w pasku pokazywalo
                # to samo zdjecie co podglad.
                o.filmstrip.setCurrentRow(o.paths.index(s))
            o.open_photo(s)
            return s
        s = self.w_gui(otworz)

        def wczytane() -> bool:
            o = self.okno
            if o._failed_path == s:
                raise BladNarzedzia(f"Could not load {os.path.basename(s)}.")
            return o.current_path == s and o.current_image is not None
        self._czekaj(wczytane, 60, "the photo to load")
        return self.n_get_photo_info({})

    def n_select_photos(self, arg: dict) -> list[dict]:
        od = _data(arg["date_from"], False) if arg.get("date_from") else None
        do = _data(arg["date_to"], True) if arg.get("date_to") else None

        def zaznacz() -> dict:
            o = self.okno
            nazwy = {os.path.basename(self._sciezka(n)) for n in arg.get("photos") or []}
            kryteria = [k for k in ("date_from", "date_to", "iso_min", "iso_max", "camera",
                                    "format", "edited", "located") if arg.get(k) is not None]
            if not (arg.get("all") or nazwy or kryteria):
                raise BladNarzedzia("Give `all`, `photos` or at least one criterion.")
            poprawione = o.filmstrip.edited_paths()
            nieznane = 0
            wybrane = []
            for s in o.paths:
                if nazwy and os.path.basename(s) not in nazwy:
                    continue
                m = o.metadata.get(s)
                potrzebne_exif = any(k in kryteria for k in
                                     ("date_from", "date_to", "iso_min", "iso_max", "camera"))
                if potrzebne_exif and m is None:
                    nieznane += 1
                    continue
                if od and not (m.shot_at and m.shot_at >= od):
                    continue
                if do and not (m.shot_at and m.shot_at <= do):
                    continue
                if arg.get("iso_min") is not None and not (m.iso and m.iso >= arg["iso_min"]):
                    continue
                if arg.get("iso_max") is not None and not (m.iso and m.iso <= arg["iso_max"]):
                    continue
                if arg.get("camera") and arg["camera"].lower() not in (m.camera or "").lower():
                    continue
                if arg.get("format") and ("jpeg" if is_jpeg(s) else "raw") != arg["format"]:
                    continue
                if arg.get("edited") is not None and (s in poprawione) != arg["edited"]:
                    continue
                if arg.get("located") is not None and o._has_location(s) != arg["located"]:
                    continue
                wybrane.append(s)
            o.filmstrip.clearSelection()
            for s in wybrane:
                pozycja = o.filmstrip._item_for(s)
                if pozycja is not None:
                    pozycja.setSelected(True)
            wynik = {"selected_count": len(wybrane),
                     "selected": [os.path.basename(s) for s in wybrane]}
            if nieznane:
                wynik["note"] = (f"{nieznane} photos skipped because their EXIF is still "
                                 "being read - try again in a moment.")
            return wynik
        return [dane(self.w_gui(zaznacz))]

    # ----------------------------------------------------------- 3. edycja

    def _wynik_zmian(self, zmienione: list[str], ile: int) -> list[dict]:
        if not zmienione:
            return [tekst(f"Nothing changed ({ile} photo(s) already had these values).")]
        return [dane({"changed": zmienione, "unchanged": ile - len(zmienione)})]

    def _surowe(self, sciezki: list[str]) -> dict[str, Any]:
        """Wczytane zdjecia (poza watkiem GUI): biezace z okna, reszta z dysku.
        Potrzebne automatowi, balansowi z aparatu i kadrowaniu z proporcja."""
        biezace = self.w_gui(lambda: (self.okno.current_path, self.okno.full_raw))
        wynik = {}
        for s in sciezki:
            if s == biezace[0] and biezace[1] is not None:
                wynik[s] = biezace[1]
            else:
                try:
                    wynik[s] = load_photo(s)
                except Exception as exc:
                    raise BladNarzedzia(f"Cannot read {os.path.basename(s)}: {exc}")
        return wynik

    def n_set_adjustments(self, arg: dict) -> list[dict]:
        wartosci = dict(arg.get("values") or {})
        zmiany = dict(arg.get("deltas") or {})
        obce = [k for k in (*wartosci, *zmiany) if k not in narzedzia.ZAKRESY]
        if obce:
            raise BladNarzedzia(f"Unknown adjustment(s): {', '.join(obce)}.")
        if not wartosci and not zmiany:
            raise BladNarzedzia("Give `values` and/or `deltas`.")
        sciezki = self.w_gui(lambda: self._cele(arg))
        # Temperatura "jak na ujeciu" nie ma liczby w nastawach - zmiana
        # wzgledna potrzebuje wartosci z aparatu, a ta jest dopiero w pliku.
        z_aparatu: dict[str, float] = {}
        if "temperature" in zmiany:
            bez_liczby = self.w_gui(
                lambda: [s for s in sciezki if self._nastawy(s).temperature is None])
            for s, raw in self._surowe(bez_liczby).items():
                z_aparatu[s] = raw.as_shot_temp

        def zmiana(p: EditParams, s: str) -> EditParams:
            for pole, wartosc in wartosci.items():
                _ustaw(p, pole, wartosc)
            for pole, delta in zmiany.items():
                baza = getattr(p, pole)
                if baza is None:
                    baza = z_aparatu[s]
                _ustaw(p, pole, baza + float(delta))
            return p

        return self._wynik_zmian(self.w_gui(lambda: self._zmien(sciezki, zmiana)), len(sciezki))

    def n_auto_adjust(self, arg: dict) -> list[dict]:
        sciezki = self.w_gui(lambda: self._cele(arg))
        nastawy = self.w_gui(lambda: {s: self._nastawy(s) for s in sciezki})
        wartosci = {}
        for s, raw in self._surowe(sciezki).items():
            wartosci[s] = auto_tone(raw, nastawy[s])

        def zmiana(p: EditParams, s: str) -> EditParams:
            for pole, wartosc in wartosci[s].items():
                if pole in narzedzia.ZAKRESY:
                    _ustaw(p, pole, wartosc)
            return p

        zmienione = self.w_gui(lambda: self._zmien(sciezki, zmiana))
        wynik = self._wynik_zmian(zmienione, len(sciezki))
        if len(sciezki) == 1:
            wynik.append(dane({"auto_values": wartosci[sciezki[0]]}))
        return wynik

    def n_reset_adjustments(self, arg: dict) -> list[dict]:
        grupy = arg.get("groups")
        sciezki = self.w_gui(lambda: self._cele(arg))

        def zmiana(p: EditParams, s: str) -> EditParams:
            domyslne = default_params_for(s)
            if not grupy:
                # Jak "Wyzeruj": wszystko, lacznie z geometria - poza tym,
                # co nie jest korekta obrazu (lokalizacja, metadane).
                domyslne.latitude, domyslne.longitude = p.latitude, p.longitude
                domyslne.metadata = dict(p.metadata)
                return domyslne
            for grupa in grupy:
                for pole in presety.GRUPY[grupa]:
                    setattr(p, pole, getattr(domyslne, pole))
            return p

        return self._wynik_zmian(self.w_gui(lambda: self._zmien(sciezki, zmiana)), len(sciezki))

    def n_list_presets(self, arg: dict) -> list[dict]:
        return [dane([{"name": p.etykieta(), "built_in": p.wbudowany, "values": p.wartosci}
                      for p in presety.wszystkie()])]

    def _preset(self, nazwa: str) -> presety.Preset:
        szukana = nazwa.strip().lower()
        for p in presety.wszystkie():
            if szukana in (p.nazwa.lower(), p.etykieta().lower()):
                return p
        dostepne = ", ".join(p.etykieta() for p in presety.wszystkie())
        raise BladNarzedzia(f"No preset named '{nazwa}'. Available: {dostepne}.")

    def n_apply_preset(self, arg: dict) -> list[dict]:
        preset = self._preset(str(arg.get("name", "")))
        sciezki = self.w_gui(lambda: self._cele(arg))

        def zmiana(p: EditParams, s: str) -> EditParams:
            for pole, wartosc in preset.wartosci.items():
                if pole == "mono":
                    p.mono = bool(wartosc)
                elif pole == "temperature" and wartosc is None:
                    p.temperature = None
                elif pole in narzedzia.ZAKRESY:
                    _ustaw(p, pole, wartosc)
            if "mono" in preset.wartosci:  # _ustaw wlacza monochrom przy barwach
                p.mono = bool(preset.wartosci["mono"])
            return p

        return self._wynik_zmian(self.w_gui(lambda: self._zmien(sciezki, zmiana)), len(sciezki))

    def n_save_preset(self, arg: dict) -> list[dict]:
        nazwa = str(arg.get("name", "")).strip()
        grupy = arg.get("groups") or list(presety.GRUPY_DOMYSLNE)
        if not nazwa:
            raise BladNarzedzia("Give a preset name.")

        def zapisz() -> str:
            o = self.okno
            if o.full_raw is None:
                raise BladNarzedzia("Open a photo first - the preset takes its values.")
            if presety.istnieje(nazwa):
                raise BladNarzedzia(f"A preset named '{nazwa}' already exists.")
            wartosci = presety.wartosci_z_grup(o.export_params(), grupy)
            if presety.zapisz_wlasny(nazwa, wartosci) is None:
                raise BladNarzedzia("Could not save the preset file.")
            o.presety_panel.odswiez(nazwa)
            return nazwa
        return [tekst(f"Preset '{self.w_gui(zapisz)}' saved.")]

    def n_set_monochrome(self, arg: dict) -> list[dict]:
        wlacz = bool(arg.get("enabled"))
        filtr = arg.get("filter")
        if filtr and filtr not in narzedzia.FILTRY:
            raise BladNarzedzia(f"Unknown filter '{filtr}'.")
        sciezki = self.w_gui(lambda: self._cele(arg))

        def zmiana(p: EditParams, s: str) -> EditParams:
            if filtr:
                barwy = (dict.fromkeys(MONO_FIELDS, 0.0) if filtr == "brak"
                         else presety.wartosci_filtra(filtr))
                for pole, wartosc in barwy.items():
                    setattr(p, pole, wartosc)
            p.mono = wlacz
            return p

        return self._wynik_zmian(self.w_gui(lambda: self._zmien(sciezki, zmiana)), len(sciezki))

    def n_rotate(self, arg: dict) -> list[dict]:
        krok = {"left": -90, "right": 90, "180": 180}.get(arg.get("direction"))
        if krok is None:
            raise BladNarzedzia("direction must be left, right or 180.")
        sciezki = self.w_gui(lambda: self._cele(arg))

        def zmiana(p: EditParams, s: str) -> EditParams:
            p.orientation = (p.orientation + krok) % 360
            p.crop = PELNY_KADR  # jak w oknie: po obrocie o 90 stopni stary kadr traci sens
            return p

        return self._wynik_zmian(self.w_gui(lambda: self._zmien(sciezki, zmiana)), len(sciezki))

    def n_set_crop(self, arg: dict) -> list[dict]:
        proporcja, prostokat = arg.get("aspect"), arg.get("rect")
        if (proporcja is None) == (prostokat is None):
            raise BladNarzedzia("Give exactly one of `aspect` or `rect`.")
        sciezki = self.w_gui(lambda: self._cele(arg))
        kadry: dict[str, tuple] = {}
        if prostokat is not None:
            l, g, p_, d = (min(1.0, max(0.0, float(v))) for v in prostokat)
            if p_ - l < 0.02 or d - g < 0.02:
                raise BladNarzedzia("rect must be [left, top, right, bottom] with left < right "
                                    "and top < bottom.")
            kadry = dict.fromkeys(sciezki, (l, g, p_, d))
        elif str(proporcja).lower() in ("none", "original", "full"):
            kadry = dict.fromkeys(sciezki, PELNY_KADR)
        else:
            ulamek = _proporcja(str(proporcja))
            nastawy = self.w_gui(lambda: {s: self._nastawy(s) for s in sciezki})
            for s, raw in self._surowe(sciezki).items():
                pelne = _kopia(nastawy[s])
                pelne.crop = PELNY_KADR
                szer, wys = geometry_size(raw, pelne)
                kadry[s] = kadr_o_proporcji(szer, wys, ulamek)

        def zmiana(p: EditParams, s: str) -> EditParams:
            p.crop = tuple(round(v, 5) for v in kadry[s])
            return p

        return self._wynik_zmian(self.w_gui(lambda: self._zmien(sciezki, zmiana)), len(sciezki))

    def n_copy_adjustments(self, arg: dict) -> list[dict]:
        grupy = arg.get("groups") or list(GRUPY_KOPIOWANIA)

        def kopiuj() -> list[str]:
            zrodlo = self._nastawy(self._sciezka(arg["source"]))
            cele = [s for s in self._cele(arg)
                    if os.path.basename(s).lower() != os.path.basename(arg["source"]).lower()]
            if not cele:
                raise BladNarzedzia("No target photos other than the source.")

            def zmiana(p: EditParams, s: str) -> EditParams:
                for grupa in grupy:
                    for pole in presety.GRUPY[grupa]:
                        setattr(p, pole, getattr(zrodlo, pole))
                return p
            return self._zmien(cele, zmiana), len(cele)

        zmienione, ile = self.w_gui(kopiuj)
        return self._wynik_zmian(zmienione, ile)

    def _historia(self, ponow: bool) -> list[dict]:
        def krok() -> str:
            o = self.okno
            if o.current_path is None or o.full_raw is None:
                raise BladNarzedzia("No photo is open.")
            mozna = (o.historia.mozna_ponowic if ponow else o.historia.mozna_cofnac)(o.current_path)
            if not mozna:
                return "Nothing to " + ("redo." if ponow else "undo.")
            (o._ponow_edycje if ponow else o._cofnij_edycje)()
            o.edits[o.current_path] = o.export_params()
            o._store_edits(o.current_path)
            return ("Redone." if ponow else "Undone.")
        return [tekst(self.w_gui(krok))]

    def n_undo(self, arg: dict) -> list[dict]:
        return self._historia(ponow=False)

    def n_redo(self, arg: dict) -> list[dict]:
        return self._historia(ponow=True)

    # ------------------------------------------------ 4. metadane i mapa

    def _zapisz_biezace(self, sciezki: list[str]) -> None:
        """Suwaki biezacego zdjecia do `edits`, zanim metadane albo lokalizacja
        przepisza jego nastawy - inaczej sidecar dostalby stan sprzed ostatnich
        ruchow suwakow."""
        o = self.okno
        if o.current_path in sciezki:
            o.remember_current_edits()

    def n_set_metadata(self, arg: dict) -> list[dict]:
        from ..core.exif_edit import current_values, merge_keywords, normalise_datetime, validate

        pola = dict(arg.get("fields") or {})
        obce = [k for k in pola if k not in narzedzia.POLA_METADANYCH]
        if obce or not pola:
            raise BladNarzedzia("fields must contain some of: "
                                + ", ".join(narzedzia.POLA_METADANYCH) + ".")
        tryb = arg.get("keywords_mode", "replace")
        wartosci: dict[str, str] = {}
        for nazwa, tekst_pola in pola.items():
            klucz = narzedzia.POLA_METADANYCH[nazwa]
            tekst_pola = str(tekst_pola).strip()
            if klucz == "DateTimeOriginal" and tekst_pola:
                tekst_pola = normalise_datetime(tekst_pola) or tekst_pola
            problem = validate(klucz, tekst_pola) if tekst_pola else None
            if problem:
                raise BladNarzedzia(f"{nazwa}: {problem}")
            wartosci[klucz] = tekst_pola
        sciezki = self.w_gui(lambda: self._cele(arg))
        # Slowa dopisywane albo usuwane licza sie od tego, co zdjecie juz ma -
        # z naszego sidecara albo, gdy tam nic nie ma, z samego pliku.
        z_pliku: dict[str, str] = {}
        if "XPKeywords" in wartosci and tryb != "replace":
            nadpisane = self.w_gui(lambda: {s: self._nastawy(s).metadata for s in sciezki})
            for s in sciezki:
                if "XPKeywords" not in nadpisane[s]:
                    try:
                        z_pliku[s] = current_values(s).get("XPKeywords", "")
                    except Exception:
                        z_pliku[s] = ""

        def zmien() -> list[str]:
            o = self.okno
            self._zapisz_biezace(sciezki)
            for s in sciezki:
                p = o._params_for(s) or default_params_for(s)
                meta = dict(p.metadata)
                for klucz, tekst_pola in wartosci.items():
                    if klucz == "XPKeywords" and tryb != "replace":
                        stare = meta.get(klucz, z_pliku.get(s, ""))
                        if tryb == "add":
                            tekst_pola = merge_keywords(stare, tekst_pola)
                        else:
                            usun = {w.strip().lower() for w in tekst_pola.split(";") if w.strip()}
                            tekst_pola = ";".join(w.strip() for w in stare.split(";")
                                                  if w.strip() and w.strip().lower() not in usun)
                    if tekst_pola:
                        meta[klucz] = tekst_pola
                    else:
                        meta.pop(klucz, None)
                p.metadata = meta
                o.edits[s] = p
                o._store_edits(s)
            if o.current_path in sciezki:
                o._show_metadata(o.current_path)
            return [os.path.basename(s) for s in sciezki]
        return [dane({"changed": self.w_gui(zmien)})]

    def n_find_place(self, arg: dict) -> list[dict]:
        miejsca = szukaj_miejsca(str(arg.get("query", "")), 5)
        if not miejsca:
            raise BladNarzedzia("Nothing found for that name.")
        return [dane(miejsca)]

    def _lokalizacje(self, sciezki: list[str], nowa: tuple[float, float] | None) -> None:
        o = self.okno
        self._zapisz_biezace(sciezki)
        # Jak na mapie: caly ruch to jeden krok historii Mapy.
        o.historia_mapy.zapamietaj({s: (o._nadana_lokalizacja(s), nowa) for s in sciezki})
        o._ustaw_lokalizacje({s: nowa for s in sciezki})

    def n_set_location(self, arg: dict) -> list[dict]:
        miejsce = None
        if arg.get("place"):
            znalezione = szukaj_miejsca(str(arg["place"]), 1)
            if not znalezione:
                raise BladNarzedzia(f"Place not found: {arg['place']}")
            miejsce = znalezione[0]
            wsp = (miejsce["latitude"], miejsce["longitude"])
        elif arg.get("latitude") is not None and arg.get("longitude") is not None:
            wsp = (float(arg["latitude"]), float(arg["longitude"]))
            if not (-90 <= wsp[0] <= 90 and -180 <= wsp[1] <= 180):
                raise BladNarzedzia("Coordinates out of range.")
        else:
            raise BladNarzedzia("Give `latitude` and `longitude`, or `place`.")
        sciezki = self.w_gui(lambda: self._cele(arg))
        self.w_gui(lambda: self._lokalizacje(sciezki, wsp))
        wynik = {"changed": [os.path.basename(s) for s in sciezki],
                 "latitude": round(wsp[0], 6), "longitude": round(wsp[1], 6)}
        if miejsce:
            wynik["place"] = miejsce["name"]
        return [dane(wynik)]

    def n_remove_location(self, arg: dict) -> list[dict]:
        sciezki = self.w_gui(lambda: self._cele(arg))
        self.w_gui(lambda: self._lokalizacje(sciezki, None))
        return [dane({"changed": [os.path.basename(s) for s in sciezki]})]

    # ---------------------------------------------------------- 5. eksport

    FORMATY = {"jpeg": ".jpg", "png": ".png", "tiff": ".tif"}

    def n_export_photos(self, arg: dict) -> list[dict]:
        from ..core.export import (
            ON_EXISTING_OVERWRITE, ON_EXISTING_SKIP, ON_EXISTING_UNIQUE, plan_export,
        )

        polityka = {"unique": ON_EXISTING_UNIQUE, "skip": ON_EXISTING_SKIP,
                    "overwrite": ON_EXISTING_OVERWRITE}.get(arg.get("on_existing", "unique"))
        if polityka is None:
            raise BladNarzedzia("on_existing must be unique, skip or overwrite.")

        def start() -> tuple:
            o = self.okno
            if o.export_task is not None:
                raise BladNarzedzia("An export is already running (see get_export_status).")
            sciezki = self._cele(arg)
            o.remember_current_edits()
            # Opcje z ostatniego eksportu uzytkownika; zmiany z polecenia sa
            # jednorazowe i nie trafiaja do jego ustawien.
            opcje = o._export_options()
            if arg.get("folder"):
                opcje.folder = str(arg["folder"])
            if "subfolder" in arg:
                opcje.subfolder = str(arg["subfolder"] or "").strip()
                opcje.use_subfolder = bool(opcje.subfolder)
            if arg.get("format"):
                if arg["format"] not in self.FORMATY:
                    raise BladNarzedzia("format must be jpeg, png or tiff.")
                opcje.file_format = self.FORMATY[arg["format"]]
            for pole, klucz in (("quality", "quality"), ("max_side", "max_side"),
                                ("start_number", "start_number")):
                if arg.get(klucz) is not None:
                    setattr(opcje, pole, int(arg[klucz]))
            for pole, klucz in (("naming", "naming"), ("custom_name", "custom_name"),
                                ("keywords", "keywords"), ("subject", "subject"),
                                ("comment", "comment")):
                if arg.get(klucz) is not None:
                    setattr(opcje, pole, str(arg[klucz]))
            for pole, klucz in (("add_watermark", "watermark"), ("add_author", "add_author"),
                                ("add_copyright", "add_copyright")):
                if arg.get(klucz) is not None:
                    setattr(opcje, pole, bool(arg[klucz]))
            if not opcje.folder:
                raise BladNarzedzia("No export folder is set yet - pass `folder`.")
            if not os.path.isabs(opcje.folder):
                raise BladNarzedzia("`folder` must be an absolute path.")
            blad = o.uruchom_eksport(plan_export(sciezki, opcje), opcje, polityka)
            if blad == "katalog":
                raise BladNarzedzia(f"Cannot create folder {opcje.target_folder()}.")
            return len(sciezki), opcje.target_folder(), blad

        ile, katalog, blad = self.w_gui(start)
        if blad == "pusto":
            return [dane({"folder": katalog, **(self.okno._ostatni_eksport or {})})]
        if arg.get("wait") is False:
            return [tekst(f"Export of {ile} photo(s) to {katalog} started. "
                          "Use get_export_status to follow it.")]
        self._czekaj(lambda: self.okno.export_task is None, 3600, "the export")
        return [dane({"folder": katalog, **(self.okno._ostatni_eksport or {})})]

    def n_get_export_status(self, arg: dict) -> list[dict]:
        def stan() -> dict:
            o = self.okno
            if o.export_task is not None:
                return {"running": True, "done": o.progress_bar.value(),
                        "total": o.progress_bar.maximum()}
            return {"running": False, "last_export": o._ostatni_eksport}
        return [dane(self.w_gui(stan))]

    def n_cancel_export(self, arg: dict) -> list[dict]:
        def przerwij() -> str:
            o = self.okno
            if o.export_task is None:
                return "No export is running."
            o._cancel_export()
            return "Export is being cancelled."
        return [tekst(self.w_gui(przerwij))]


# ------------------------------------------------------------- pomocnicze

def _jpeg(rgb: np.ndarray, bok: int) -> str:
    from PIL import Image

    zdjecie = Image.fromarray(np.ascontiguousarray(rgb))
    zdjecie.thumbnail((bok, bok), Image.LANCZOS)
    bufor = io.BytesIO()
    zdjecie.save(bufor, "JPEG", quality=85)
    return base64.b64encode(bufor.getvalue()).decode("ascii")


def _obok_siebie(lewy: np.ndarray, prawy: np.ndarray) -> np.ndarray:
    """Dwa obrazy w jednym, na tej samej wysokosci, z szara przerwa."""
    from PIL import Image

    wys = min(lewy.shape[0], prawy.shape[0])

    def do_wysokosci(a: np.ndarray) -> np.ndarray:
        if a.shape[0] == wys:
            return a
        szer = max(1, round(a.shape[1] * wys / a.shape[0]))
        return np.asarray(Image.fromarray(a).resize((szer, wys), Image.LANCZOS))

    przerwa = np.full((wys, 8, 3), 128, dtype=np.uint8)
    return np.hstack([do_wysokosci(lewy), przerwa, do_wysokosci(prawy)])


def szukaj_miejsca(zapytanie: str, ile: int) -> list[dict]:
    """Nazwa miejsca -> wspolrzedne (Nominatim, OpenStreetMap).

    Ta sama usluga, z ktorej korzysta wyszukiwarka na mapie. Zasady Nominatim
    wymagaja przedstawienia sie programu (User-Agent) i najwyzej jednego
    zapytania na sekunde - model moze wolac to narzedzie seriami, stad
    odstep pilnowany tutaj.
    """
    import json
    import urllib.parse
    import urllib.request

    from ..przeklad import jezyk

    zapytanie = zapytanie.strip()
    if not zapytanie:
        raise BladNarzedzia("Give a place name.")
    with _NOMINATIM:
        odstep = 1.1 - (time.monotonic() - _NOMINATIM_OSTATNIO[0])
        if odstep > 0:
            time.sleep(odstep)
        url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit="
               f"{ile}&q={urllib.parse.quote(zapytanie)}")
        zadanie = urllib.request.Request(url, headers={
            "User-Agent": "Punctum photo editor (github.com/Riberrr/Punctum)",
            "Accept-Language": jezyk() or "en",
        })
        try:
            with urllib.request.urlopen(zadanie, timeout=15) as odp:
                wyniki = json.loads(odp.read())
        except Exception as exc:
            raise BladNarzedzia(f"Place search failed (internet?): {exc}")
        finally:
            _NOMINATIM_OSTATNIO[0] = time.monotonic()
    return [{"name": w.get("display_name"), "latitude": float(w["lat"]),
             "longitude": float(w["lon"]), "type": w.get("type")} for w in wyniki]


_NOMINATIM = threading.Lock()
_NOMINATIM_OSTATNIO = [0.0]


def statystyki(rgb: np.ndarray) -> dict:
    """Liczby opisujace obraz tak, jak go widac (8 bitow po krzywej sRGB)."""
    obraz_f = rgb.astype(np.float32)
    jasnosc = obraz_f @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    maks, mini = obraz_f.max(axis=2), obraz_f.min(axis=2)
    nasycenie = np.where(maks > 0, (maks - mini) / np.maximum(maks, 1), 0)
    percentyle = np.percentile(jasnosc, [1, 5, 25, 50, 75, 95, 99])
    histogram_16, _ = np.histogram(jasnosc, bins=16, range=(0, 256))
    return {
        "size": [int(rgb.shape[1]), int(rgb.shape[0])],
        "brightness_0_255": {
            "mean": round(float(jasnosc.mean()), 1),
            "percentiles": dict(zip(("p1", "p5", "p25", "p50", "p75", "p95", "p99"),
                                    (round(float(v), 1) for v in percentyle))),
        },
        "clipped_shadows_percent": round(float((maks <= 2).mean() * 100), 2),
        "clipped_highlights_percent": round(float((mini >= 253).mean() * 100), 2),
        "any_channel_clipped_percent": round(float((maks >= 254).mean() * 100), 2),
        "channel_means_rgb": [round(float(v), 1) for v in obraz_f.reshape(-1, 3).mean(axis=0)],
        "mean_saturation_0_1": round(float(nasycenie.mean()), 3),
        "histogram_16_bins_percent": [round(float(v) * 100 / jasnosc.size, 1)
                                      for v in histogram_16],
    }
