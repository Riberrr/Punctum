"""Test interfejsu przy mieszanym katalogu: filtr formatow i opis balansu bieli.

Skleja tymczasowy katalog z kilku RAW-ow i kilku JPEG-ow, po czym sprawdza,
czy pasek miniatur, przelacznik formatow i panel korekt zachowuja sie tak,
jak powinny. Uzycie:

    python tools/test_jpeg_gui.py <plik.rw2> <plik.jpg> [wiecej plikow...]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wspolne import czekaj, lancuch, wypisz  # noqa: E402

app = QApplication(sys.argv)

from punctum.app import MainWindow  # noqa: E402
from punctum.core import FORMAT_ALL, FORMAT_JPEG, FORMAT_RAW, is_jpeg  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


workspace = tempfile.mkdtemp(prefix="punctum-jpeg-")
for source in sys.argv[1:]:
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))

raw_files = [n for n in os.listdir(workspace) if not is_jpeg(n)]
jpeg_files = [n for n in os.listdir(workspace) if is_jpeg(n)]
print(f"katalog testowy: {len(raw_files)} RAW, {len(jpeg_files)} JPEG")

window = MainWindow()
window.resize(1500, 950)
# Test przestawia filtr formatow, a okno zapisuje ustawienia przy kazdej takiej
# zmianie. Bez tej zaslepki zostawialby uzytkownikowi wlasny filtr w prawdziwym
# pliku ustawien - i po tescie program pokazywalby mu tylko RAW-y.
window.settings.save = lambda *args, **kwargs: True
window.show()
window.format_combo.setCurrentIndex(window.format_combo.findData(FORMAT_ALL))
window.load_folder(workspace)


def select_format(key: str) -> None:
    window.format_combo.setCurrentIndex(window.format_combo.findData(key))
    app.processEvents()


def stage_list() -> None:
    czekaj(app, lambda: window.filmstrip.count() == len(raw_files) + len(jpeg_files),
           "lista zdjęć w pasku miniatur")
    check("katalog pokazuje oba formaty naraz",
          window.filmstrip.count() == len(raw_files) + len(jpeg_files),
          f"{window.filmstrip.count()} pozycji")
    check("licznik nad paskiem podaje oba formaty",
          "RAW" in window.format_count.text() and "JPEG" in window.format_count.text(),
          window.format_count.text())

    select_format(FORMAT_JPEG)
    check("filtr JPEG zostawia same JPEG-i",
          window.filmstrip.count() == len(jpeg_files) == len(window.paths)
          and all(is_jpeg(p) for p in window.paths),
          f"{window.filmstrip.count()} pozycji")

    select_format(FORMAT_RAW)
    check("filtr RAW zostawia same RAW-y",
          window.filmstrip.count() == len(raw_files) == len(window.paths)
          and not any(is_jpeg(p) for p in window.paths),
          f"{window.filmstrip.count()} pozycji")

    check("wybor formatu zapisuje sie w ustawieniach",
          window.settings.format_filter == FORMAT_RAW, window.settings.format_filter)
    select_format(FORMAT_ALL)


def stage_jpeg() -> None:
    """Otwiera JPEG-a i sprawdza, co panel o nim mowi."""
    target = next(p for p in window.paths if is_jpeg(p))
    window.filmstrip.setCurrentRow(window.paths.index(target))
    czekaj(app, lambda: window.current_path == target and window.full_raw is not None,
           "wczytanie JPEG-a")


def stage_jpeg_check() -> None:
    label = window.edit_panel.sliders["temperature"].name_label.text()
    check("suwak temperatury oznaczony jako wzgledny przy JPEG", "wzgl" in label, label)
    check("pasek stanu mowi, ze to JPEG", "JPEG" in window.status.currentMessage(),
          window.status.currentMessage())
    check("zdjecie sie wczytalo",
          window.full_raw is not None and window.full_raw.source_format == "jpeg",
          "brak" if window.full_raw is None else window.full_raw.source_format)
    window._run_auto()


def stage_auto_check() -> None:
    czekaj(app,
           lambda: abs(window.edit_panel.sliders["exposure"].value()) > 1e-6
           or abs(window.edit_panel.sliders["contrast"].value()) > 1e-6,
           "wynik automatu na suwakach", 15000)
    exposure = window.edit_panel.sliders["exposure"].value()
    contrast = window.edit_panel.sliders["contrast"].value()
    check("automat dziala na JPEG-u", abs(exposure) > 1e-6 or abs(contrast) > 1e-6,
          f"EV{exposure:+.2f}, kontrast {contrast:+.0f}")
    window.grab().save(os.path.join("out", "jpeg_okno.png"))

    target = next((p for p in window.paths if not is_jpeg(p)), None)
    if target is not None:
        window.filmstrip.setCurrentRow(window.paths.index(target))
        czekaj(app,
               lambda: window.full_raw is not None
               and window.full_raw.source_format != "jpeg",
               "wczytanie RAW-a")


def stage_raw_check() -> None:
    label = window.edit_panel.sliders["temperature"].name_label.text()
    check("przy RAW wraca zwykla etykieta temperatury", label == "Temperatura", label)
    check("przy RAW pasek stanu podaje kelwiny",
          " K" in window.status.currentMessage(), window.status.currentMessage())


KOD = 0


def report() -> None:
    global KOD
    try:
        KOD = wypisz(results)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        window.close()
        app.quit()


os.makedirs("out", exist_ok=True)
lancuch(app, [stage_list, stage_jpeg, stage_jpeg_check,
              stage_auto_check, stage_raw_check], report)

app.exec()
sys.exit(KOD)
