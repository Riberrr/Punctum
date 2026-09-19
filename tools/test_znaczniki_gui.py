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

# Konsola Windows chodzi w cp1250, a znacznik lokalizacji jest rombem spoza
# tej strony kodowej - bez tego raport wysypuje sie na wlasnym wydruku.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from punctum.app import MainWindow  # noqa: E402
from punctum.app.markers import EDIT_MARK, GEO_MARK, caption, strip  # noqa: E402
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


def caption_of(strip_widget, path: str) -> str:
    for row in range(strip_widget.count()):
        item = strip_widget.item(row)
        if item.data(0x0100) == path:
            return item.text()
    return ""


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
    """Sam modul znacznikow i stan wyjsciowy list."""
    check("znaczniki sa rozne", EDIT_MARK != GEO_MARK, f"{EDIT_MARK} / {GEO_MARK}")
    check("podpis bez znacznikow to sama nazwa",
          caption("DSC.jpg") == "DSC.jpg", caption("DSC.jpg"))
    check("podpis z obydwoma znacznikami",
          caption("DSC.jpg", True, True) == f"{EDIT_MARK}{GEO_MARK} DSC.jpg",
          caption("DSC.jpg", True, True))
    check("wyrownanie trzyma szerokosc prefiksu",
          len(caption("a.jpg", False, False, pad=True))
          == len(caption("a.jpg", True, True, pad=True)))
    check("ze znacznikow da sie wrocic do nazwy",
          strip(caption("DSC.jpg", True, True, pad=True)) == "DSC.jpg")

    wait_for(lambda: window.filmstrip.count() == len(sys.argv) - 1, "lista zdjęć")
    wait_for(lambda: window.full_raw is not None, "wczytanie pierwszego zdjęcia")

    state["photos"] = list(window.paths)
    state["jpeg"] = next((p for p in window.paths if is_writable_format(p)), None)
    state["raw"] = next((p for p in window.paths if not is_writable_format(p)), None)
    # Zdjecia moga miec GPS prosto z aparatu - punktem odniesienia jest to,
    # co bylo na starcie, a nie zalozenie, ze lista jest pusta.
    state["geo0"] = {
        p for p in window.paths if GEO_MARK in caption_of(window.filmstrip, p)
    }
    check("na starcie nic nie jest oznaczone jako poprawione",
          window.filmstrip.edited_count() == 0,
          f"{window.filmstrip.edited_count()} oznaczonych")
    check("sekcja metadanych jest zwinieta",
          not window.exif_section.content.isVisible())


def stage_lokalizacja() -> None:
    """Nadanie wspolrzednych zapala znacznik na pasku miniatur."""
    target = state["photos"][0]
    other = next((p for p in state["photos"][1:] if p not in state["geo0"]), None)
    window._on_location_assigned([target], LAT, LON)
    app.processEvents()

    text = caption_of(window.filmstrip, target)
    check("pasek miniatur oznacza zdjecie z lokalizacja", GEO_MARK in text, text)
    check("zapisana praca ma swoj wlasny znacznik", EDIT_MARK in text, text)
    check("pasek liczy zdjecia z lokalizacja",
          window.filmstrip.located_count() == len(state["geo0"] | {target}),
          f"{window.filmstrip.located_count()}")
    if other is not None:
        check("zdjecie bez wspolrzednych zostaje bez znacznika",
              GEO_MARK not in caption_of(window.filmstrip, other),
              caption_of(window.filmstrip, other))

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
          EDIT_MARK in caption_of(window.filmstrip, jpeg),
          caption_of(window.filmstrip, jpeg))
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
    text = ""
    for row in range(view.list.count()):
        if view.list.item(row).data(0x0100) == located:
            text = view.list.item(row).text()
    check("lista w mapie oznacza zdjecie z lokalizacja", GEO_MARK in text, text)
    check("lista w mapie oznacza tez zapisana prace", EDIT_MARK in text, text)

    jpeg = state["jpeg"]
    jpeg_text = ""
    for row in range(view.list.count()):
        if view.list.item(row).data(0x0100) == jpeg:
            jpeg_text = view.list.item(row).text()
    check("zdjecie z metadanymi ma znacznik pracy w mapie",
          EDIT_MARK in jpeg_text, jpeg_text)

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
    report()


def report() -> None:
    # Sprzatanie w finally - wywrocony wydruk nie ma prawa zawiesic testu.
    try:
        print(f"\n{'test':<54}{'wynik':>8}   szczegoly", flush=True)
        print("-" * 110, flush=True)
        failures = 0
        for name, ok, detail in results:
            failures += 0 if ok else 1
            print(f"{name:<54}{'OK' if ok else 'BLAD':>8}   {detail}", flush=True)
        print(f"\n{len(results) - failures} / {len(results)} testow przeszlo",
              flush=True)
    finally:
        window.close()
        window.pool.waitForDone(5000)  # inaczej watek wraca do skasowanego okna
        shutil.rmtree(workspace, ignore_errors=True)
        if BACKUP is not None:
            with open(SETTINGS_FILE, "wb") as handle:
                handle.write(BACKUP)
        app.quit()


def guarded(function):
    def wrapper() -> None:
        import traceback
        try:
            function()
        except Exception:
            print(f"\nWYJATEK w {function.__name__}:", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            report()
    return wrapper


os.makedirs("out", exist_ok=True)
QTimer.singleShot(5000, guarded(stage_czyste))
QTimer.singleShot(9000, guarded(stage_lokalizacja))
QTimer.singleShot(11000, guarded(stage_metadane))
QTimer.singleShot(17000, guarded(stage_mapa))
QTimer.singleShot(21000, guarded(stage_zapis))

sys.exit(app.exec())
