"""Znaczniki na listach zdjec i panel metadanych w obu zakladkach.

Test udaje uzytkownika, ktory wraca do katalogu po przerwie: sprawdza, czy
z samej listy widac, co jest juz poprawione i co ma wspolrzedne, a potem czy
wpisane metadane ida ta sama droga, co reszta nastaw - do sidecara, do obu
paneli i na zadanie do samego pliku.

Uzycie:  python tools/test_znaczniki_gui.py <plik.rw2> <plik.jpg> [wiecej...]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Konsola Windows chodzi w cp1250 i potrafi wywrocic sie na wlasnym wydruku
# (strzalki, ogonki) - raport idzie wiec w UTF-8.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QPainter, QPixmap  # noqa: E402

from wspolne import lancuch, wypisz  # noqa: E402

from punctum.app import MainWindow  # noqa: E402
from punctum.app.markers import EDIT_ROLE, GEO_ROLE, paint_pin  # noqa: E402
from punctum.core.exif_edit import current_values, is_writable_format  # noqa: E402
from punctum.core.settings import settings_path  # noqa: E402
from punctum.core.sidecar import read_sidecar  # noqa: E402

LAT, LON = 49.2992, 19.9496
AUTOR = "Łukasz Żółć"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def wait_for(condition, label: str, timeout_ms: int = 25000) -> bool:
    import time as _time
    deadline = _time.perf_counter() + timeout_ms / 1000.0
    while _time.perf_counter() < deadline:
        app.processEvents()
        if condition():
            return True
        _time.sleep(0.02)
    print(f"[czekanie] nie doczekano: {label}", flush=True)
    return False


def item_of(list_widget, path: str):
    for row in range(list_widget.count()):
        item = list_widget.item(row)
        if item.data(0x0100) == path:
            return item
    return None


def marks_of(list_widget, path: str) -> tuple[bool, bool]:
    """(zapisana praca, wspolrzedne) - tak, jak widzi to rysujacy delegat."""
    item = item_of(list_widget, path)
    if item is None:
        return (False, False)
    return (bool(item.data(EDIT_ROLE)), bool(item.data(GEO_ROLE)))


def caption_of(list_widget, path: str) -> str:
    item = item_of(list_widget, path)
    return "" if item is None else item.text()


# Ustawienia uzytkownika sa prawdziwym plikiem - test ich nie rusza.
SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

workspace = tempfile.mkdtemp(prefix="punctum-znaczniki-")
for source in sys.argv[1:]:
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))
print(f"katalog testowy: {len(os.listdir(workspace))} zdjec")

window = MainWindow()
window.settings.save = lambda *a, **k: True  # zadnych sladow w ustawieniach
window.settings.store_edits = True
window.resize(1500, 950)
window.show()
window.format_combo.setCurrentIndex(window.format_combo.findData("all"))
window.load_folder(workspace)

state: dict = {}


def stage_czyste() -> None:
    """Rysowanie znacznikow i stan wyjsciowy list."""
    check("znaczniki maja osobne role", EDIT_ROLE != GEO_ROLE)

    # Pinezka jest rysowana, a nie pisana - wiec sprawdzamy, czy naprawde
    # cokolwiek zostawia na obrazku.
    canvas = QPixmap(16, 20)
    canvas.fill(Qt.black)
    painter = QPainter(canvas)
    paint_pin(painter, QRectF(2, 2, 11, 15))
    painter.end()
    image = canvas.toImage()
    painted = sum(
        1 for y in range(20) for x in range(16)
        if image.pixelColor(x, y).red() > 60
    )
    check("pinezka naprawde sie rysuje", painted > 25, f"{painted} pikseli")

    wait_for(lambda: window.filmstrip.count() == len(sys.argv) - 1, "lista zdjęć")
    wait_for(lambda: window.full_raw is not None, "wczytanie pierwszego zdjęcia")

    state["photos"] = list(window.paths)
    state["jpeg"] = next((p for p in window.paths if is_writable_format(p)), None)
    state["raw"] = next((p for p in window.paths if not is_writable_format(p)), None)
    # Zdjecia moga miec GPS prosto z aparatu - punktem odniesienia jest to,
    # co bylo na starcie, a nie zalozenie, ze lista jest pusta.
    state["geo0"] = {
        p for p in window.paths if marks_of(window.filmstrip, p)[1]
    }
    check("na starcie nic nie jest oznaczone jako poprawione",
          window.filmstrip.edited_count() == 0,
          f"{window.filmstrip.edited_count()} oznaczonych")
    check("podpis w pasku to sama nazwa pliku",
          caption_of(window.filmstrip, state["photos"][0])
          == os.path.basename(state["photos"][0]),
          caption_of(window.filmstrip, state["photos"][0]))
    check("metadane sa schowane, a strzalka widoczna",
          not window.exif_panel.isVisible()
          and not window.info_panel.details_button.isHidden())


def stage_lokalizacja() -> None:
    """Nadanie wspolrzednych zapala znacznik na pasku miniatur."""
    target = state["photos"][0]
    other = next((p for p in state["photos"][1:] if p not in state["geo0"]), None)
    window._on_location_assigned([target], LAT, LON)
    app.processEvents()

    edited, located = marks_of(window.filmstrip, target)
    check("pasek miniatur oznacza zdjecie z lokalizacja", located)
    check("zapisana praca ma swoj wlasny znacznik", edited)
    check("nazwa pliku zostaje nietknieta",
          caption_of(window.filmstrip, target) == os.path.basename(target),
          caption_of(window.filmstrip, target))
    check("pasek liczy zdjecia z lokalizacja",
          window.filmstrip.located_count() == len(state["geo0"] | {target}),
          f"{window.filmstrip.located_count()}")
    if other is not None:
        check("zdjecie bez wspolrzednych zostaje bez znacznika",
              not marks_of(window.filmstrip, other)[1])

    saved = read_sidecar(target)
    check("lokalizacja poszla do sidecara",
          saved is not None and saved.has_location)
    if window.current_path == target:
        check("dane zdjecia pokazuja nadana lokalizacje",
              "nadana" in window.info_panel.gps_label.text(),
              window.info_panel.gps_label.text())
    state["located"] = target


def stage_metadane() -> None:
    """Wpis w panelu EXIF trafia do nastaw i na dysk."""
    jpeg = state["jpeg"]
    if jpeg is None:
        check("w katalogu testowym jest JPEG", False, "podaj jakis plik .jpg")
        return
    window.filmstrip.setCurrentRow(window.paths.index(jpeg))
    wait_for(lambda: window.current_path == jpeg and window.full_raw is not None,
             "wczytanie JPEG-a")

    # Strzalka w sekcji z danymi zdjecia rozwija metadane w dol.
    column = window.info_panel.parentWidget()
    before_width = column.width()
    before_view = window.view.width()
    window.info_panel.details_button.click()
    app.processEvents()
    check("strzalka rozwija metadane", window.exif_panel.isVisible())
    check("rozwiniecie nie poszerza prawej kolumny",
          column.width() == before_width,
          f"{before_width} → {column.width()} px")
    check("podglad zdjecia nie przeskakuje",
          window.view.width() == before_view,
          f"{before_view} → {window.view.width()} px")
    check("i zmienia sie na zwijajaca",
          window.info_panel.details_button.text() == "▴",
          window.info_panel.details_button.text())

    panel = window.exif_panel
    check("panel pokazuje biezace zdjecie", panel.path == jpeg,
          os.path.basename(panel.path or ""))
    check("przycisk zapisu do oryginalu dziala dla JPEG-a",
          panel.write_button.isEnabled())

    panel.editors["Artist"].setText(AUTOR)
    panel._on_edited()
    app.processEvents()

    params = window._params_for(jpeg)
    check("zmiana pola trafila do nastaw zdjecia",
          params is not None and params.metadata.get("Artist") == AUTOR,
          repr(params.metadata if params else None)[:60])

    window.remember_current_edits()
    saved = read_sidecar(jpeg)
    check("metadane sa w sidecarze",
          saved is not None and saved.metadata.get("Artist") == AUTOR,
          repr(saved.metadata if saved else None)[:60])
    check("wpisanie metadanych oznacza zdjecie jako poprawione",
          marks_of(window.filmstrip, jpeg)[0])
    written = current_values(jpeg).get("Artist", "")
    check("plik zrodlowy jeszcze nietkniety", written != AUTOR,
          "czeka na przycisk" if written != AUTOR else "juz zapisany!")


def stage_mapa() -> None:
    """Drugi panel w zakladce mapy pokazuje to samo co pierwszy."""
    window.tabs.setCurrentIndex(1)
    app.processEvents()
    view = window.map_view
    check("zakladka mapy ma panel metadanych", view is not None
          and view.exif_panel is not None)

    panel = view.exif_panel
    check("panel w mapie pokazuje to samo zdjecie",
          panel.path == window.current_path,
          os.path.basename(panel.path or ""))
    check("panel w mapie zna wpisanego autora",
          panel.editors["Artist"].text() == AUTOR,
          panel.editors["Artist"].text())

    located = state.get("located")
    edited_mark, geo_mark = marks_of(view.list, located)
    check("lista w mapie oznacza zdjecie z lokalizacja", geo_mark)
    check("lista w mapie oznacza tez zapisana prace", edited_mark)
    check("nazwy w mapie to same nazwy plikow",
          caption_of(view.list, located) == os.path.basename(located),
          caption_of(view.list, located))

    jpeg = state["jpeg"]
    check("zdjecie z metadanymi ma znacznik pracy w mapie",
          marks_of(view.list, jpeg)[0])
    check("panel metadanych ma margines od krawedzi okna",
          view.panel_host.layout().contentsMargins().right() >= 8,
          f"{view.panel_host.layout().contentsMargins().right()} px")

    # Zmiana w panelu mapy ma dojsc do nastaw tak samo, jak w Edycji.
    panel.editors["Copyright"].setText("© 2026 Punctum")
    panel._on_edited()
    app.processEvents()
    params = window._params_for(window.current_path)
    check("zmiana z panelu w mapie tez trafia do nastaw",
          params is not None and params.metadata.get("Copyright") == "© 2026 Punctum",
          repr(params.metadata if params else None)[:70])


def stage_zapis() -> None:
    """Przycisk "zapisz do oryginalu" wpisuje metadane w plik."""
    window.tabs.setCurrentIndex(0)
    app.processEvents()
    jpeg = state["jpeg"]
    window.filmstrip.setCurrentRow(window.paths.index(jpeg))
    wait_for(lambda: window.current_path == jpeg, "powrót na JPEG-a")
    window.filmstrip.clearSelection()
    for row in range(window.filmstrip.count()):
        item = window.filmstrip.item(row)
        item.setSelected(item.data(0x0100) == jpeg)
    app.processEvents()

    before = os.path.getmtime(jpeg)
    window.exif_panel.write_button.click()
    app.processEvents()

    values = current_values(jpeg)
    check("autor jest juz w pliku", values.get("Artist") == AUTOR,
          values.get("Artist", "brak"))
    check("prawa autorskie tez", values.get("Copyright") == "© 2026 Punctum",
          values.get("Copyright", "brak"))
    check("data pliku zostala nietknieta",
          abs(os.path.getmtime(jpeg) - before) < 1.0,
          f"{os.path.getmtime(jpeg) - before:+.1f} s")

    raw = state["raw"]
    if raw is not None:
        window.filmstrip.setCurrentRow(window.paths.index(raw))
        wait_for(lambda: window.exif_panel.path == raw, "przełączenie panelu na RAW")
        check("dla RAW-a zapis do oryginalu jest wylaczony",
              not window.exif_panel.write_button.isEnabled())
        check("i panel mowi dlaczego",
              "XMP" in window.exif_panel.problem.text(),
              window.exif_panel.problem.text()[:70])

    window.grab().save(os.path.join("out", "znaczniki_okno.png"))


KOD = 0


def report() -> None:
    global KOD
    # Sprzatanie w finally - wywrocony wydruk nie ma prawa zawiesic testu.
    try:
        KOD = wypisz(results, szerokosc=54)
    finally:
        window.close()
        window.pool.waitForDone(5000)  # inaczej watek wraca do skasowanego okna
        shutil.rmtree(workspace, ignore_errors=True)
        if BACKUP is not None:
            with open(SETTINGS_FILE, "wb") as handle:
                handle.write(BACKUP)
        app.quit()


os.makedirs("out", exist_ok=True)
lancuch(app, [stage_czyste, stage_lokalizacja, stage_metadane,
              stage_mapa, stage_zapis], report)

app.exec()
sys.exit(KOD)
