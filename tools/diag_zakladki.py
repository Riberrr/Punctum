"""Dlaczego przy wejsciu na zakladke Mapa okno miga.

Podejrzenie: QWebEngineView dostaje wlasne OKNO NATYWNE, a Qt, dokladajac
natywne dziecko do okna, ktore go wczesniej nie mialo, potrafi przebudowac
cale okno najwyzszego poziomu. Z zewnatrz wyglada to dokladnie tak, jak
opisuje uzytkownik: okno na ulamek sekundy znika i pojawia sie od nowa.

Da sie to sprawdzic wprost: uchwyt okna (winId) jest wtedy INNY niz przed
przelaczeniem. Test mierzy tez czas kazdego przejscia miedzy zakladkami.

Uzycie:  python tools/diag_zakladki.py <plik.rw2> [wiecej...]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from punctum.app import MainWindow  # noqa: E402
from punctum.core.settings import settings_path  # noqa: E402

SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

WCZESNIE = "--wczesnie" in sys.argv  # zbuduj mape PRZED pokazaniem okna
photos = [a for a in sys.argv[1:] if not a.startswith("--")]

workspace = tempfile.mkdtemp(prefix="punctum-zakladki-")
for source in photos:
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))

GL = "--gl" in sys.argv  # zamiast mapy: maleńki widżet OpenGL przed pokazaniem

build_start = time.perf_counter()
window = MainWindow()
window.settings.save = lambda *a, **k: True
window.resize(1400, 900)
if WCZESNIE:
    window._ensure_map()
if GL:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    probe = QOpenGLWidget(window.map_tab)
    probe.resize(1, 1)
    probe.show()
    app.processEvents()
build_ms = (time.perf_counter() - build_start) * 1000.0
window.show()
print(f"budowa okna{' z mapa' if WCZESNIE else ''}: {build_ms:.0f} ms")
window.format_combo.setCurrentIndex(window.format_combo.findData("all"))
window.load_folder(workspace)


def settle(seconds: float = 0.6) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)


def report() -> None:
    settle(2.0)
    print(f"\nokno po starcie:            winId={int(window.winId())}")
    print(f"mapa zbudowana:             {window.map_view is not None}")

    handles = [int(window.winId())]
    for step in range(4):
        target = 1 if step % 2 == 0 else 0
        start = time.perf_counter()
        window.tabs.setCurrentIndex(target)
        settle(1.2)
        elapsed = (time.perf_counter() - start) * 1000.0
        handle = int(window.winId())
        native = "tak" if window.map_view is not None else "nie"
        changed = "ZMIENIL SIE" if handle != handles[-1] else "bez zmian"
        handles.append(handle)
        name = "Mapa" if target == 1 else "Edycja"
        print(f"przejscie na {name:<7} {elapsed:7.0f} ms   winId={handle}  ({changed})")
        if window.map_view is not None and target == 1:
            view = window.map_view.web
            print(f"    widok sieciowy: winId={int(view.winId())}, "
                  f"natywny rodzic={native}, "
                  f"tlo strony={view.page().backgroundColor().name()}")

    print(f"\nuchwytow razem: {len(set(handles))} roznych "
          f"({'okno bylo przebudowywane' if len(set(handles)) > 1 else 'okno stabilne'})")

    window.close()
    window.pool.waitForDone(4000)
    shutil.rmtree(workspace, ignore_errors=True)
    if BACKUP is not None:
        with open(SETTINGS_FILE, "wb") as handle:
            handle.write(BACKUP)
    app.quit()


QTimer.singleShot(4000, report)
sys.exit(app.exec())
