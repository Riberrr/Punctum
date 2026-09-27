"""Cofnij / ponow i nowe przyciski Mapy w dzialajacym oknie (punkt 25).

Udaje uzytkownika: rusza suwakami i obraca zdjecie, cofa i ponawia przyciskami
i skrotem, przechodzi na inne zdjecie i wraca; w Mapie nadaje lokalizacje
dwom zdjeciom naraz, cofa to jednym ruchem, przywraca wspolrzedne z aparatu,
filtruje liste i zaznacza jej czesci.

Uzycie:  python tools/test_historia_gui.py <plik.rw2> <plik.jpg> [wiecej...] [--pelny]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from wspolne import czekaj, lancuch, wypisz, zdjecia  # noqa: E402

from punctum.app import MainWindow  # noqa: E402
from punctum.core.settings import settings_path  # noqa: E402
from punctum.core.sidecar import read_sidecar  # noqa: E402

LAT, LON = 49.2992, 19.9496
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

workspace = tempfile.mkdtemp(prefix="punctum-historia-")
for source in zdjecia():
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))

window = MainWindow()
window.settings.save = lambda *a, **k: True  # zadnych sladow w ustawieniach
window.settings.store_edits = True
window.resize(1500, 950)
window.show()
window.format_combo.setCurrentIndex(window.format_combo.findData("all"))
window.load_folder(workspace)

panel = window.edit_panel
state: dict = {}


def value(key: str) -> float:
    return panel.sliders[key].value()


def buttons() -> tuple[bool, bool]:
    return panel.undo_button.isEnabled(), panel.redo_button.isEnabled()


def stage_start() -> None:
    czekaj(app, lambda: window.filmstrip.count() == len(zdjecia()), "lista zdjec")
    czekaj(app, lambda: window.full_raw is not None, "pierwsze zdjecie")
    state["p0"] = window.current_path
    check("swieze zdjecie: cofnij i ponow wylaczone", buttons() == (False, False),
          str(buttons()))


def stage_edycja() -> None:
    panel.sliders["exposure"].set_value(1.0)
    window._zatwierdz_krok(sila=True)
    panel.sliders["contrast"].set_value(30.0)
    window._zatwierdz_krok(sila=True)
    check("po zmianie mozna cofnac", buttons() == (True, False), str(buttons()))

    panel.undo_button.click()
    check("cofnij zdejmuje ostatnia zmiane",
          value("contrast") == 0.0 and value("exposure") == 1.0,
          f"kontrast {value('contrast')}, ekspozycja {value('exposure')}")
    panel.undo_button.click()
    check("drugie cofniecie wraca do stanu wyjsciowego", value("exposure") == 0.0)
    check("na poczatku: tylko ponow", buttons() == (False, True), str(buttons()))
    panel.redo_button.click()
    check("ponow przywraca zmiane", value("exposure") == 1.0 and value("contrast") == 0.0)

    # Zmiana zatwierdzana zegarem, po chwili spokoju - tak jak przy suwaku.
    panel.sliders["saturation"].set_value(20.0)
    check("zmiana czeka na chwile spokoju", window.history_timer.isActive())
    czekaj(app, lambda: not window.history_timer.isActive(), "zegar historii", 3000)
    check("po chwili ponawianie jest odciete", buttons() == (True, False), str(buttons()))
    window.undo_action.trigger()  # Ctrl+Z z menu
    check("skrot cofa nasycenie", value("saturation") == 0.0 and value("exposure") == 1.0)

    # Ctrl+Z tuz po ruchu, zanim zegar zdazy - cofa te zmiane, nie wczesniejsza.
    panel.sliders["exposure"].set_value(2.0)
    window.undo_action.trigger()
    check("cofniecie od razu po zmianie cofa wlasnie ja", value("exposure") == 1.0,
          str(value("exposure")))

    window._rotate_orientation(90)
    window._zatwierdz_krok(sila=True)
    check("obrot o 90 stopni", window.orientation == 90)
    window.undo_action.trigger()
    check("cofniecie obrotu", window.orientation == 0, str(window.orientation))
    window.redo_action.trigger()
    check("ponowienie obrotu (Ctrl+Y)", window.orientation == 90)
    window.undo_action.trigger()


def stage_drugie() -> None:
    other = next(p for p in window.paths if p != state["p0"])
    state["p1"] = other
    window.filmstrip.setCurrentRow(window.paths.index(other))
    czekaj(app, lambda: window.current_path == other and window.full_raw is not None,
           "drugie zdjecie")
    check("inne zdjecie ma wlasna, pusta historie", buttons() == (False, False),
          str(buttons()))
    panel.sliders["contrast"].set_value(-20.0)
    window._zatwierdz_krok(sila=True)

    window.filmstrip.setCurrentRow(window.paths.index(state["p0"]))
    czekaj(app, lambda: window.current_path == state["p0"] and window.full_raw is not None,
           "powrot do pierwszego")
    check("po powrocie historia zdjecia jest na miejscu", buttons()[0], str(buttons()))
    check("i nastawy tez", value("exposure") == 1.0, str(value("exposure")))
    window.undo_action.trigger()
    check("cofanie po powrocie dziala", value("exposure") == 0.0, str(value("exposure")))


def own(path: str):
    params = window._params_for(path)
    return (params.latitude, params.longitude) if params and params.has_location else None


def stage_mapa() -> None:
    window.tabs.setCurrentWidget(window.map_tab)
    app.processEvents()
    mv = window.map_view
    a, b = state["p0"], state["p1"]
    check("mapa: na starcie bez historii",
          not mv.undo_button.isEnabled() and not mv.redo_button.isEnabled())

    window._on_location_assigned([a, b], LAT, LON)
    check("przypisanie dwom zdjeciom", own(a) == (LAT, LON) and own(b) == (LAT, LON))
    check("mapa: mozna cofnac", mv.undo_button.isEnabled())
    window.undo_action.trigger()  # w zakladce mapy skrot cofa lokalizacje
    check("jedno cofniecie zdejmuje lokalizacje z obu", own(a) is None and own(b) is None,
          f"{own(a)} {own(b)}")
    saved = read_sidecar(a)
    check("cofniecie trafia do sidecara", saved is not None and not saved.has_location)
    check("suwaki w Edycji nietkniete skrotem z mapy", value("exposure") == 0.0)
    mv.redo_button.click()
    check("ponow przywraca oba", own(a) == (LAT, LON) and own(b) == (LAT, LON))

    # Przywracanie z aparatu: udajemy, ze zdjecie mialo GPS w pliku.
    mv.camera[a] = (50.0, 20.0)
    mv.set_selection([b])
    check("przywracanie wylaczone dla zdjecia bez GPS z aparatu",
          not mv.restore_button.isEnabled())
    mv.set_selection([a])
    check("przywracanie wlaczone dla zmienionego", mv.restore_button.isEnabled())
    mv.restore_button.click()
    check("przywrocenie zdejmuje nasza lokalizacje", own(a) is None and own(b) == (LAT, LON))
    mv.undo_button.click()
    check("i da sie je cofnac", own(a) == (LAT, LON))

    # Zaznaczanie i filtr.
    located = {p for p in window.paths if p in mv.locations}
    mv.select_located_button.click()
    check("zaznacz z lokalizacja", set(mv.selected_paths()) == located,
          f"{len(mv.selected_paths())} z {len(located)}")
    mv.select_missing_button.click()
    check("zaznacz bez lokalizacji", set(mv.selected_paths()) == set(window.paths) - located)
    mv.select_all_button.click()
    check("zaznacz wszystkie", len(mv.selected_paths()) == len(window.paths))

    mv.set_filter("bez_lokalizacji")
    check("filtr chowa zdjecia z lokalizacja",
          set(mv.visible_paths()) == set(window.paths) - located)
    check("ukryte traca zaznaczenie", not (set(mv.selected_paths()) & located))
    check("lejek wcisniety przy wlaczonym filtrze", mv.filter_button.isChecked())
    mv.select_all_button.click()
    check("zaznacz wszystkie bierze tylko widoczne",
          set(mv.selected_paths()) == set(mv.visible_paths()))
    mv.set_filter("nadana")
    check("filtr: nadane na mapie", set(mv.visible_paths()) == {a, b}, str(len(mv.visible_paths())))
    mv.set_filter("wszystkie")
    check("bez filtra wszystko widac i lejek puszczony",
          len(mv.visible_paths()) == len(window.paths) and not mv.filter_button.isChecked())
    window.tabs.setCurrentIndex(0)


def stage_uklad() -> None:
    crop, reset = panel.crop_button, panel.crop_reset_button
    check("kadrowanie i zerowanie kadru w jednym wierszu z obrotami",
          crop.parentWidget() is reset.parentWidget()
          and abs(crop.geometry().center().y() - reset.geometry().center().y()) <= 1,
          f"{crop.geometry().y()} / {reset.geometry().y()}")
    check("zerowanie kadru to ikona", not reset.icon().isNull() and reset.text() == "")
    check("cofnij i ponow w pasku akcji",
          panel.undo_button.parentWidget() is panel.pasek_akcji
          and panel.redo_button.parentWidget() is panel.pasek_akcji)
    rows = [panel.undo_button.geometry().center().y(), panel.auto_button.geometry().center().y()]
    check("w tym samym wierszu co Automatycznie", abs(rows[0] - rows[1]) <= 1, str(rows))


KOD = 0


def report() -> None:
    global KOD
    try:
        KOD = wypisz(results, szerokosc=56)
    finally:
        window.close()
        window.pool.waitForDone(5000)
        shutil.rmtree(workspace, ignore_errors=True)
        if BACKUP is not None:
            with open(SETTINGS_FILE, "wb") as handle:
                handle.write(BACKUP)
        app.quit()


lancuch(app, [stage_start, stage_edycja, stage_drugie, stage_mapa, stage_uklad], report)
app.exec()
sys.exit(KOD)
