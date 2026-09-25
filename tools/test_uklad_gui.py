"""Uklad okna Edycji: panele, splittery, suwak powiekszenia, menu.

Pilnuje tego, co ustalila karta punktu 3+14: przy zmaksymalizowanym oknie
najwazniejsze elementy obu paneli sa widoczne bez przewijania, rozwiniecie
metadanych nie rusza szerokosci niczego, a rozmiary paneli i paska miniatur
zmienia sie mysza i sa pamietane.

Uzycie:  python tools/test_uklad_gui.py <plik.rw2> <plik.jpg> [wiecej...]
Zrzut okna po ulozeniu trafia do katalogu tymczasowego (punctum-uklad.png).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from PySide6.QtCore import QRect, Qt  # noqa: E402

from wspolne import czekaj, lancuch, wypisz, zdjecia  # noqa: E402

from punctum.app import MainWindow  # noqa: E402
from punctum.app.filmstrip import TILE_OVERHEAD  # noqa: E402
from punctum.app.settings_dialog import PAGE_ABOUT, SettingsDialog  # noqa: E402
from punctum.core.settings import LAYOUT_LIMITS, Settings, settings_path  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

workspace = tempfile.mkdtemp(prefix="punctum-uklad-")
for source in zdjecia():
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))

window = MainWindow()
window.settings.save = lambda *a, **k: True  # zadnych sladow w ustawieniach
window.settings.store_edits = False
# Wartosci inne niz domyslne - inaczej nie widac, czy zostaly odtworzone.
window.settings.left_panel_width = 300
window.settings.right_panel_width = 360
window.settings.filmstrip_height = 180
window.showMaximized()

state: dict = {}


def fully_visible(widget, panel) -> bool:
    """Widzet w calosci w widocznym prostokacie panelu (bez przewijania)."""
    if not widget.isVisible():
        return False
    top_left = widget.mapTo(panel, widget.rect().topLeft())
    return panel.rect().contains(QRect(top_left, widget.size()))


def stage_start() -> None:
    czekaj(app, lambda: window.panel_splitter.sizes()[0] == 300, "odtworzenie ukladu")
    left, _centre, right = window.panel_splitter.sizes()
    check("szerokosc lewego panelu odtworzona", left == 300, f"{left} px")
    check("szerokosc prawego panelu odtworzona", right == 360, f"{right} px")
    check("wysokosc paska miniatur odtworzona", window.filmstrip.height() == 180,
          f"{window.filmstrip.height()} px")
    check("kafelki rosna razem z paskiem",
          window.filmstrip.iconSize().height() == 180 - TILE_OVERHEAD,
          f"{window.filmstrip.iconSize().height()} px")

    titles = [a.text() for a in window.menuBar().actions()]
    check("menu: Plik, Edycja, Widok, Pomoc",
          titles == ["&Plik", "&Edycja", "&Widok", "Pomo&c"], str(titles))
    corner = window.tabs.cornerWidget()
    check("Eksportuj stoi w rogu belki zakladek",
          corner is not None and corner.isAncestorOf(window.export_button))
    check("ikona kadrowania wczytana", not window.edit_panel.crop_button.icon().isNull())

    window.format_combo.setCurrentIndex(window.format_combo.findData("all"))
    window.load_folder(workspace)
    czekaj(app, lambda: window.full_raw is not None, "wczytanie pierwszego zdjecia")


def stage_widocznosc() -> None:
    left, right = window.left_panel, window.right_panel
    zoom = window.zoom_panel
    for name, widget in (
        ("nawigator", window.navigator),
        ("suwak powiekszenia", zoom.slider),
        ("przycisk Dopasuj", zoom.fit_button),
        ("przycisk 100 %", zoom.actual_button),
        ("przycisk Przed / po", window.before_button),
        ("dane zdjecia", window.info_panel),
    ):
        check(f"lewy panel: {name} widoczny", fully_visible(widget, left))
    panel = window.edit_panel
    for name, widget in (
        ("histogram", window.histogram_widget),
        ("przycisk kadrowania", panel.crop_button),
        ("suwak kata", panel.sliders["rotation"]),
        ("Wyzeruj kadr", panel.crop_reset_button),
        ("Automatycznie", panel.auto_button),
        ("Wyzeruj", panel.reset_button),
    ):
        check(f"prawy panel: {name} widoczny", fully_visible(widget, right))
    check("suwaki przewijaja sie osobno",
          not panel.scroll_area.widget().isAncestorOf(panel.auto_button))

    path = os.path.join(tempfile.gettempdir(), "punctum-uklad.png")
    window.grab().save(path)


def stage_powiekszenie() -> None:
    view, zoom = window.view, window.zoom_panel
    check("po wczytaniu suwak stoi na 'dopasuj'", zoom.slider.value() == 0,
          str(zoom.slider.value()))
    zoom.slider.setValue(500)
    app.processEvents()
    check("suwak powieksza obraz", view.zoom > view.fit_zoom() * 1.5,
          f"{view.zoom:.3f} przy dopasowaniu {view.fit_zoom():.3f}")
    view.zoom_actual()
    app.processEvents()
    check("przycisk 100 % przesuwa suwak", zoom.slider.value() == zoom.value_for(1.0),
          f"{zoom.slider.value()} / {zoom.value_for(1.0)}")
    check("etykieta pokazuje 100 %", zoom.zoom_label.text() == "100 %",
          zoom.zoom_label.text())
    zoom.slider.setValue(zoom.slider.maximum())
    app.processEvents()
    check("koniec suwaka to maksimum podgladu",
          abs(view.zoom - view.MAX_ZOOM) < 0.01, f"{view.zoom:.2f}")
    zoom.fit_button.click()
    app.processEvents()
    check("Dopasuj wraca suwakiem na poczatek", zoom.slider.value() == 0,
          str(zoom.slider.value()))


def stage_metadane() -> None:
    before = (window.left_panel.width(), window.right_panel.width(), window.view.width())
    nav_top = window.navigator.geometry().top()
    window.info_panel.details_button.click()
    app.processEvents()
    after = (window.left_panel.width(), window.right_panel.width(), window.view.width())
    check("rozwiniecie metadanych nie zmienia szerokosci", before == after,
          f"{before} -> {after}")
    check("nawigator zostaje na miejscu",
          window.navigator.geometry().top() == nav_top
          and fully_visible(window.navigator, window.left_panel))
    check("suwak powiekszenia dalej widoczny",
          fully_visible(window.zoom_panel.slider, window.left_panel))
    exif = window.exif_panel
    check("przyciski metadanych widoczne bez przewijania",
          all(fully_visible(b, window.left_panel)
              for b in (exif.all_button, exif.clear_button, exif.write_button)))
    window.info_panel.details_button.click()
    app.processEvents()


def stage_przeciaganie() -> None:
    splitter = window.panel_splitter
    splitter.moveSplitter(320, 1)
    app.processEvents()
    check("przeciagniecie zmienia lewy panel", splitter.sizes()[0] == 320,
          str(splitter.sizes()))
    check("i trafia do ustawien", window.settings.left_panel_width == 320,
          str(window.settings.left_panel_width))
    splitter.moveSplitter(900, 1)
    app.processEvents()
    high = LAYOUT_LIMITS["left_panel_width"][1]
    check("lewy panel nie przekracza granicy", splitter.sizes()[0] == high,
          str(splitter.sizes()[0]))
    splitter.moveSplitter(splitter.width() - 400 - splitter.handleWidth(), 2)
    app.processEvents()
    check("przeciagniecie zmienia prawy panel", splitter.sizes()[2] == 400,
          str(splitter.sizes()))

    strip = window.strip_splitter
    header = window._strip_header.height()
    strip.moveSplitter(strip.height() - header - 240 - strip.handleWidth(), 1)
    app.processEvents()
    check("przeciagniecie zmienia wysokosc paska", window.filmstrip.height() == 240,
          f"{window.filmstrip.height()} px")
    check("wysokosc paska trafia do ustawien", window.settings.filmstrip_height == 240,
          str(window.settings.filmstrip_height))

    # zapis i odczyt - to, co przezywa zamkniecie programu
    target = os.path.join(workspace, "ustawienia.json")
    Settings.save(window.settings, target)
    loaded = Settings.load(target)
    check("rozmiary przezywaja zapis",
          (loaded.left_panel_width, loaded.right_panel_width, loaded.filmstrip_height)
          == (high, 400, 240),
          f"{loaded.left_panel_width} {loaded.right_panel_width} {loaded.filmstrip_height}")
    clamped = Settings(left_panel_width=10, right_panel_width=5000,
                       filmstrip_height=1).normalised()
    check("uszkodzone rozmiary sa przycinane",
          (clamped.left_panel_width, clamped.right_panel_width, clamped.filmstrip_height)
          == (220, 480, 90))

    dialog = SettingsDialog(window.settings, window.system, window)
    dialog.show_page(PAGE_ABOUT)
    check("Pomoc otwiera ustawienia na stronie O programie",
          dialog.current_page() == PAGE_ABOUT
          and dialog.categories.currentItem().data(Qt.UserRole) == PAGE_ABOUT)
    dialog.deleteLater()


def finish() -> None:
    try:
        failures = wypisz(results)
    finally:
        window.hide()
        if BACKUP is not None:
            with open(SETTINGS_FILE, "wb") as handle:
                handle.write(BACKUP)
        shutil.rmtree(workspace, ignore_errors=True)
    app.exit(failures)


lancuch(app, [stage_start, stage_widocznosc, stage_powiekszenie, stage_metadane,
              stage_przeciaganie], finish)
sys.exit(app.exec())
