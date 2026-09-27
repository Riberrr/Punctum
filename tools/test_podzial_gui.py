"""Podzielony podglad przed/po w dzialajacym oknie (punkt 19).

Wlacza podzial z menu i przyciskiem, sprawdza, ze po lewej stronie linii
jest zdjecie bez korekt, a po prawej z korektami, przeciaga linie mysza,
przycina kadr (obie polowki musza miec te sama geometrie), przytrzymuje
"Przed / po", wchodzi w kadrowanie i powieksza do 100 %.

Uzycie:  python tools/test_podzial_gui.py <plik.rw2> [wiecej...] [--pelny]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from wspolne import czekaj, lancuch, wypisz, zdjecia  # noqa: E402

from punctum.app import MainWindow  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


workspace = tempfile.mkdtemp(prefix="punctum-podzial-")
for source in zdjecia()[:1]:
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))

window = MainWindow()
window.settings.save = lambda *a, **k: True  # zadnych sladow w ustawieniach
window.settings.store_edits = False
window.resize(1500, 950)
window.show()
window.format_combo.setCurrentIndex(window.format_combo.findData("all"))
window.load_folder(workspace)

view = window.view
panel = window.edit_panel


def pomaluj() -> None:
    for _ in range(5):
        app.processEvents()


def jasnosc(x_ulamek: float) -> float:
    """Srednia jasnosc pionowego paska zdjecia w polozeniu x (ulamek szerokosci),
    z pominieciem gornej czesci, gdzie stoja podpisy."""
    pomaluj()
    obraz = view.viewport().grab().toImage()
    width, height = view.image_size
    lewy_gorny = view.mapFromScene(0.0, 0.0)
    prawy_dolny = view.mapFromScene(float(width), float(height))
    x = round(lewy_gorny.x() + (prawy_dolny.x() - lewy_gorny.x()) * x_ulamek)
    y0 = round(lewy_gorny.y() + (prawy_dolny.y() - lewy_gorny.y()) * 0.3)
    y1 = round(lewy_gorny.y() + (prawy_dolny.y() - lewy_gorny.y()) * 0.9)
    suma, n = 0.0, 0
    for y in range(max(0, y0), min(obraz.height(), y1), 3):
        for dx in range(-6, 7, 3):
            kolor = obraz.pixelColor(min(obraz.width() - 1, max(0, x + dx)), y)
            suma += kolor.red() + kolor.green() + kolor.blue()
            n += 1
    return suma / max(1, n) / 3.0


def ta_sama_geometria() -> bool:
    return view._before_base.pixmap().size() == view._base.pixmap().size()


def stage_start() -> None:
    czekaj(app, lambda: window.full_raw is not None and window.current_image is not None,
           "pierwsze zdjecie")
    check("na starcie podzial wylaczony",
          not window.split_button.isChecked() and not view.split_visible)
    check("przycisk podzialu ma ikone i dymek",
          not window.split_button.icon().isNull() and bool(window.split_button.toolTip()))
    check("akcja w menu ma skrot Y", window.split_action.shortcut().toString() == "Y",
          window.split_action.shortcut().toString())


def stage_wlacz() -> None:
    window.split_action.trigger()
    check("akcja z menu wciska przycisk", window.split_button.isChecked())
    czekaj(app, lambda: view.split_visible, "podzial widoczny")
    check("po wlaczeniu linia jest widoczna", view.split_visible)
    check("obraz przed w rozmiarze podgladu", ta_sama_geometria(),
          f"{view._before_base.pixmap().size()} / {view._base.pixmap().size()}")
    check("linia startuje na srodku", abs(view.split_position - 0.5) < 1e-6,
          f"{view.split_position}")


def stage_strony() -> None:
    panel.sliders["exposure"].set_value(2.0)
    window._render_preview()
    czekaj(app, lambda: window.display_params().exposure == 2.0, "ekspozycja")
    pomaluj()
    view.set_split_position(1.0)
    przed = jasnosc(0.2), jasnosc(0.8)
    view.set_split_position(0.0)
    po = jasnosc(0.2), jasnosc(0.8)
    view.set_split_position(0.5)
    polowa = jasnosc(0.2), jasnosc(0.8)
    check("po korekcie +2 EV zdjecie jest jasniejsze", po[0] > przed[0] + 10,
          f"przed {przed[0]:.0f}, po {po[0]:.0f}")
    check("lewa polowa pokazuje przed", abs(polowa[0] - przed[0]) < 3,
          f"{polowa[0]:.1f} wobec {przed[0]:.1f}")
    check("prawa polowa pokazuje po", abs(polowa[1] - po[1]) < 3,
          f"{polowa[1]:.1f} wobec {po[1]:.1f}")


def stage_przeciaganie() -> None:
    width, height = view.image_size
    start = view.mapFromScene(width * 0.5, height * 0.5)
    cel = view.mapFromScene(width * 0.25, height * 0.5)
    viewport = view.viewport()
    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(start.x(), start.y()))
    QTest.mouseMove(viewport, QPoint((start.x() + cel.x()) // 2, cel.y()))
    QTest.mouseMove(viewport, QPoint(cel.x(), cel.y()))
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(cel.x(), cel.y()))
    pomaluj()
    check("przeciagniecie przesuwa linie", abs(view.split_position - 0.25) < 0.02,
          f"{view.split_position:.3f}")
    srodek = view.mapToScene(viewport.rect().center())
    check("przeciaganie linii nie przesuwa zdjecia",
          abs(srodek.x() - width / 2) < width * 0.02, f"{srodek.x():.0f}")


def stage_kadr() -> None:
    pelny = view.image_size
    window.crop = (0.2, 0.1, 0.8, 0.9)
    view.set_crop_fractions(window.crop)
    window._render_preview()
    czekaj(app, lambda: window.current_image is not None and ta_sama_geometria()
           and view.image_size[0] < pelny[0] * 0.7, "kadr")
    check("po kadrowaniu przed ma geometrie kadru", ta_sama_geometria(),
          f"{view._before_base.pixmap().size()} / {view._base.pixmap().size()}")


def stage_przytrzymanie() -> None:
    window.before_button.pressed.emit()
    pomaluj()
    check("przytrzymanie przed/po chowa podzial", not view.split_visible)
    window.before_button.released.emit()
    czekaj(app, lambda: view.split_visible, "podzial po puszczeniu")
    check("po puszczeniu podzial wraca", view.split_visible and ta_sama_geometria())


def stage_kadrowanie() -> None:
    panel.crop_button.setChecked(True)
    pomaluj()
    check("w kadrowaniu podzialu nie ma", not view.split_visible)
    panel.crop_button.setChecked(False)
    czekaj(app, lambda: view.split_visible, "podzial po kadrowaniu")
    check("po kadrowaniu podzial wraca", view.split_visible and ta_sama_geometria())


def stage_detal() -> None:
    view.zoom_actual()
    czekaj(app, lambda: view._before_detail.isVisible(), "ostry fragment przed")
    check("przy 100 % ostry fragment ma tez strona przed", view._before_detail.isVisible())
    view.fit_to_window()


def stage_wylacz() -> None:
    window.split_button.click()
    pomaluj()
    check("przycisk wylacza podzial i odznacza menu",
          not view.split_visible and not window.split_action.isChecked())


KOD = 0


def report() -> None:
    global KOD
    try:
        KOD = wypisz(results, szerokosc=56)
    finally:
        window.close()
        window.pool.waitForDone(5000)
        shutil.rmtree(workspace, ignore_errors=True)
        app.quit()


lancuch(app, [stage_start, stage_wlacz, stage_strony, stage_przeciaganie, stage_kadr,
              stage_przytrzymanie, stage_kadrowanie, stage_detal, stage_wylacz], report)
app.exec()
sys.exit(KOD)
