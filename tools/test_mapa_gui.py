"""Przejscie przez interfejs: zakladka Mapa, przypisanie punktu, trwalosc.

Test udaje uzytkownika: przechodzi na zakladke mapy, zaznacza zdjecia, nadaje
im wspolrzedne (wolajac most tak, jak zrobilby to klikniety Leaflet), wraca do
edycji, rusza suwakiem i zamyka program. Potem otwiera go od nowa i sprawdza,
czy lokalizacja przezyla.

Uzycie:  python tools/test_mapa_gui.py <plik.rw2> <plik.jpg> [wiecej...]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Raport pokazuje nazwy plikow i polskie napisy - konsola Windows chodzi
# w cp1250 i potrafi wywrocic sie na wlasnym wydruku.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)  # test sam zamyka okno w srodku

from wspolne import lancuch, wypisz  # noqa: E402

from punctum.app import MainWindow  # noqa: E402
from punctum.app.markers import GEO_ROLE  # noqa: E402
from punctum.core.settings import settings_path  # noqa: E402
from punctum.core.sidecar import read_sidecar  # noqa: E402

LAT, LON = 50.0686361, 22.2290139

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def wait_for(condition, label: str, timeout_ms: int = 25000) -> bool:
    """Czeka na warunek zamiast zgadywac czas - patrz test_trwalosc_gui."""
    import time as _time
    deadline = _time.perf_counter() + timeout_ms / 1000.0
    while _time.perf_counter() < deadline:
        app.processEvents()
        if condition():
            return True
        _time.sleep(0.02)
    print(f"[czekanie] nie doczekano: {label}", flush=True)
    return False


SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

workspace = tempfile.mkdtemp(prefix="punctum-mapa-")
for source in sys.argv[1:]:
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))
print(f"katalog testowy: {len(os.listdir(workspace))} zdjec")

window = MainWindow()
window.resize(1500, 950)
window.show()
# Filtr formatow pamieta wybor miedzy uruchomieniami, a test ma pokazac
# wszystkie skopiowane zdjecia niezaleznie od tego, co uzytkownik ustawil.
window.format_combo.setCurrentIndex(window.format_combo.findData("all"))
window.load_folder(workspace)
second: list[MainWindow] = []


def stage_open_map() -> None:
    wait_for(lambda: window.full_raw is not None, "wczytanie pierwszego zdjęcia")
    check("okno ma dwie zakladki", window.tabs.count() == 2,
          " / ".join(window.tabs.tabText(i) for i in range(window.tabs.count())))
    # Mapa stoi gotowa od startu. Nie jest to optymalizacja, tylko lekarstwo
    # na migotanie: QWebEngineView dokladany do widocznego okna kaze Qt
    # przebudowac cale okno (uchwyt sie zmienia, program na moment znika
    # z ekranu). Dlatego pilnujemy obu rzeczy naraz.
    check("mapa jest gotowa przed wejsciem na zakladke", window.map_view is not None)
    before = int(window.winId())
    window.tabs.setCurrentIndex(1)
    app.processEvents()
    check("zakladka pokazala mape", window.map_view is not None)
    check("przejscie na mape nie przebudowuje okna",
          int(window.winId()) == before,
          f"{before} → {int(window.winId())}")
    check("strona mapy ma ciemne tlo, nie biale",
          window.map_view.web.page().backgroundColor().name() != "#ffffff",
          window.map_view.web.page().backgroundColor().name())
    check("mapa dostala wszystkie zdjecia z katalogu",
          window.map_view.list.count() == len(window.paths) == len(sys.argv) - 1,
          f"{window.map_view.list.count()} pozycji, w katalogu {len(window.paths)}")

    view = window.map_view
    wait_for(lambda: all(not view.list.item(i).icon().isNull()
                         for i in range(view.list.count())),
             "miniatury w liście mapy", 15000)
    with_icon = sum(1 for i in range(view.list.count())
                    if not view.list.item(i).icon().isNull())
    check("lista mapy pokazuje miniatury",
          with_icon == view.list.count(),
          f"{with_icon} z {view.list.count()} pozycji ma miniature")


def stage_assign() -> None:
    view = window.map_view
    wait_for(lambda: view.answered, "odpowiedź strony mapy")
    check("strona mapy sie zgłosiła", view.answered,
          "mapa wczytana" if view.has_map else "brak sieci — mapa nieaktywna")

    # Zaznaczamy dwa pierwsze zdjecia i wolamy most tak, jak zrobilby to
    # klikniety Leaflet. Samo klikniecie w kafelek jest poza zasiegiem testu.
    paths = [view.list.item(i).data(0x0100) for i in range(min(2, view.list.count()))]
    view.set_selection(paths)
    check("zaznaczenie przeszlo do listy mapy", view.selected_paths() == paths,
          f"{len(view.selected_paths())} zaznaczonych")

    view.bridge.map_clicked.emit(LAT, LON)
    app.processEvents()

    stored = [read_sidecar(p) for p in paths]
    check("obydwa zdjecia dostaly wspolrzedne",
          all(s is not None and s.has_location for s in stored),
          ", ".join("brak" if s is None else f"{s.latitude:.5f}" for s in stored))
    check("wspolrzedne sa te, ktore wskazano",
          all(s is not None and abs(s.latitude - LAT) < 1e-6
              and abs(s.longitude - LON) < 1e-6 for s in stored))
    check("lista mapy oznacza zdjecia z lokalizacja",
          bool(view.list.item(0).data(GEO_ROLE)), view.list.item(0).text())
    window.first_two = paths


def stage_slider() -> None:
    """Powrot do edycji i ruch suwakiem - lokalizacja ma to przezyc."""
    window.tabs.setCurrentIndex(0)
    app.processEvents()
    window.filmstrip.setCurrentRow(0)
    app.processEvents()


def stage_slider_check() -> None:
    wait_for(lambda: window.full_raw is not None, "powrót do edycji zdjęcia")
    window.edit_panel.sliders["exposure"].set_value(1.10)
    app.processEvents()
    window.remember_current_edits()
    saved = read_sidecar(window.first_two[0])
    check("ruch suwakiem nie skasowal lokalizacji",
          saved is not None and saved.has_location
          and abs(saved.latitude - LAT) < 1e-6,
          "brak" if saved is None or not saved.has_location
          else f"{saved.latitude:.5f}, {saved.longitude:.5f}")
    check("korekta zapisala sie razem z lokalizacja",
          saved is not None and abs(saved.exposure - 1.10) < 1e-6,
          f"EV{saved.exposure:+.2f}" if saved else "brak")
    window.close()
    app.processEvents()


def stage_reopen() -> None:
    fresh = MainWindow()
    fresh.resize(1500, 950)
    fresh.show()
    fresh.load_folder(workspace)
    second.append(fresh)
    app.processEvents()


def stage_verify() -> None:
    fresh = second[0]
    wait_for(lambda: fresh.filmstrip.count() == len(sys.argv) - 1,
             "lista zdjęć w nowym oknie")
    fresh.tabs.setCurrentIndex(1)
    app.processEvents()
    view = fresh.map_view
    wait_for(lambda: view.answered, "odpowiedź strony mapy w nowym oknie")
    check("po ponownym otwarciu mapa zna lokalizacje",
          len(view.locations) == 2, f"{len(view.locations)} zdjec z pinezka")
    first = window.first_two[0]
    check("wspolrzedne przezyly zamkniecie programu",
          first in view.locations and abs(view.locations[first][0] - LAT) < 1e-6,
          f"{view.locations.get(first)}")
    check("lista pokazuje znacznik lokalizacji",
          sum(1 for row in range(view.list.count())
              if view.list.item(row).data(GEO_ROLE)) == 2)

    # usuniecie lokalizacji
    view.set_selection([first])
    view._on_clear()
    app.processEvents()
    cleared = read_sidecar(first)
    check("usuniecie lokalizacji dziala",
          cleared is not None and not cleared.has_location,
          "zostala" if cleared and cleared.has_location else "zdjeta")
    check("korekty zostaly nietkniete przy usuwaniu lokalizacji",
          cleared is not None and abs(cleared.exposure - 1.10) < 1e-6,
          f"EV{cleared.exposure:+.2f}" if cleared else "brak")

    fresh.grab().save(os.path.join("out", "mapa_okno.png"))

    # Zrzut ekranu widoku sieciowego wychodzi bialy, wiec o stan mapy pytamy
    # sama strone: ile kafelkow naprawde sie wczytalo i ile jest pinezek.
    # Odpowiedz przychodzi wywolaniem zwrotnym, wiec etap na nia czeka -
    # inaczej lancuch etapow zdazylby zamknac program przed odpowiedzia.
    if view.has_map:
        view.web.page().runJavaScript("window.mapState()", _on_state)
        wait_for(lambda: odpowiedziala, "odpowiedź strony o stanie mapy", 8000)


odpowiedziala = False


def _on_state(raw) -> None:
    global odpowiedziala
    odpowiedziala = True
    import json as _json
    try:
        state = _json.loads(raw)
    except Exception:  # noqa: BLE001
        check("mapa odpowiedziala o swoim stanie", False, repr(raw)[:80])
        return
    print(f"stan mapy: {state}")
    check("kafelki mapy naprawde sie wczytaly", state.get("tiles", 0) > 0,
          f"{state.get('tiles')} kafelkow")
    check("pinezka zostala po usunieciu jednej z dwoch",
          state.get("markers") == 1, f"{state.get('markers')} pinezek")


KOD = 0


def report() -> None:
    global KOD
    # Sprzatanie idzie w finally: gdy sam wydruk sie wywroci (a potrafi, patrz
    # strona kodowa konsoli), test ma sie skonczyc, a nie wisiec do rana.
    try:
        KOD = wypisz(results)
    finally:
        # Watki wczytujace zdjecia musza skonczyc, zanim zniknie okno -
        # inaczej sygnal wraca do skasowanego obiektu i Qt krzyczy na stderr.
        for opened in [window, *second]:
            opened.pool.waitForDone(4000)
            opened.close()
        shutil.rmtree(workspace, ignore_errors=True)
        if BACKUP is not None:
            with open(SETTINGS_FILE, "wb") as handle:
                handle.write(BACKUP)
        app.quit()


os.makedirs("out", exist_ok=True)
lancuch(app, [stage_open_map, stage_assign, stage_slider,
              stage_slider_check, stage_reopen, stage_verify], report)

app.exec()
sys.exit(KOD)
