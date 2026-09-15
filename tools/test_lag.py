"""Pomiar opoznienia od ruchu suwaka do odswiezonego podgladu.

Mierzymy cala droge, tak jak przechodzi ja zdarzenie z myszy: zmiana wartosci
suwaka, obieg petli zdarzen, przeliczenie obrazu, podmiana pixmapy. Sam czas
renderowania nie wystarczy - opoznienie moze siedziec rownie dobrze
w kolejkowaniu zadan albo w konwersji obrazu.

Granica odczuwalnosci to okolo 16 ms, czyli jedna klatka przy 60 Hz.
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.app import MainWindow  # noqa: E402

folder = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "out/lag"
os.makedirs(out_dir, exist_ok=True)

app = QApplication(sys.argv)
window = MainWindow()
window.resize(1600, 1000)
window.show()
window.load_folder(folder)

updates: list[float] = []
original_set_image = window.view.set_image


def timed_set_image(rgb8, image_size, *args, **kwargs):
    updates.append(time.perf_counter())
    return original_set_image(rgb8, image_size, *args, **kwargs)


window.view.set_image = timed_set_image


def measure(action) -> float:
    """Czas od wywolania akcji do faktycznego odswiezenia podgladu.

    Petla kreci sie bez usypiania watku. `time.sleep(0.001)` wydaje sie
    niewinne, ale zegar systemowy Windows ma rozdzielczosc okolo 15 ms, wiec
    jedno takie usypianie potrafi dopisac do wyniku wiecej niz cala mierzona
    operacja. Pierwsza wersja tego testu pokazywala przez to 11 ms tam, gdzie
    naprawde bylo 6.
    """
    updates.clear()
    start = time.perf_counter()
    action()
    deadline = start + 2.0
    while not updates and time.perf_counter() < deadline:
        app.processEvents()
    return (updates[-1] - start) * 1000 if updates else float("nan")


def summarise(name: str, samples: list[float]) -> None:
    values = np.array([v for v in samples if not np.isnan(v)])
    if not values.size:
        print(f"{name:<34}{'brak pomiarów':>12}")
        return
    median, worst = float(np.median(values)), float(values.max())
    verdict = "PŁYNNIE" if median < 16 else ("ZNOŚNIE" if median < 40 else "ZA WOLNO")
    print(f"{name:<34}{median:>8.1f}{worst:>9.1f}   {verdict}")


def send_mouse(kind, pos: QPointF, modifiers=Qt.NoModifier) -> None:
    view = window.view
    types = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove,
             "release": QEvent.MouseButtonRelease}
    event = QMouseEvent(
        types[kind], pos, view.viewport().mapToGlobal(pos.toPoint()),
        Qt.LeftButton if kind != "move" else Qt.NoButton,
        Qt.LeftButton, modifiers,
    )
    {"press": view.mousePressEvent, "move": view.mouseMoveEvent,
     "release": view.mouseReleaseEvent}[kind](event)


def run_tests() -> None:
    print(f"silnik podglądu : {'GPU' if window.gpu_source_ready else 'procesor (numpy)'}")
    if window.gpu.available:
        print(f"karta           : {window.gpu.hardware}")
    width, height = window.view.image_size
    print(f"obraz           : {width}x{height}\n")
    print(f"{'operacja':<34}{'mediana':>8}{'najgorzej':>9}   ocena")
    print("-" * 64)

    exposure = window.edit_panel.sliders["exposure"]
    samples = [measure(lambda i=i: exposure.set_value(-1.0 + i * 0.08)) for i in range(25)]
    summarise("suwak ekspozycji", samples)

    shadows = window.edit_panel.sliders["shadows"]
    samples = [measure(lambda i=i: shadows.set_value(i * 4)) for i in range(25)]
    summarise("suwak cieni (maski EV)", samples)

    temperature = window.edit_panel.sliders["temperature"]
    samples = [measure(lambda i=i: temperature.set_value(4000 + i * 200)) for i in range(25)]
    summarise("suwak temperatury barwowej", samples)

    vibrance = window.edit_panel.sliders["vibrance"]
    samples = [measure(lambda i=i: vibrance.set_value(-50 + i * 4)) for i in range(25)]
    summarise("suwak jaskrawości", samples)

    rotation = window.edit_panel.sliders["rotation"]
    samples = [measure(lambda i=i: rotation.set_value(-8 + i * 0.7)) for i in range(25)]
    summarise("suwak kąta obrotu", samples)
    rotation.set_value(0)

    # kadrowanie ciagnieciem uchwytu
    window.edit_panel.crop_button.setChecked(True)
    app.processEvents()
    view = window.view

    def scene_to_view(x, y):
        return QPointF(view.mapFromScene(QPointF(x, y)))

    # Przeciaganie ramki nie przelicza obrazu, tylko odrysowuje nakladke,
    # wiec mierzymy czas pelnego odrysowania okna - to jest to, co decyduje
    # o plynnosci ciagniecia uchwytu.
    samples = []
    send_mouse("press", scene_to_view(width, height))
    for i in range(20):
        factor = 1.0 - i * 0.02
        start = time.perf_counter()
        send_mouse("move", scene_to_view(width * factor, height * factor))
        view.viewport().repaint()
        samples.append((time.perf_counter() - start) * 1000)
    send_mouse("release", scene_to_view(width * 0.6, height * 0.6))
    summarise("ciągnięcie narożnika kadru", samples)

    # obrot ciagnieciem poza kadrem
    view.set_crop_fractions((0.2, 0.2, 0.8, 0.8))
    samples = []
    send_mouse("press", scene_to_view(width * 1.1, height * 0.5))
    for i in range(20):
        samples.append(measure(
            lambda i=i: send_mouse("move", scene_to_view(width * 1.1, height * (0.5 + i * 0.01)))
        ))
    send_mouse("release", scene_to_view(width * 1.1, height * 0.7))
    summarise("obrót ciągnięciem poza kadrem", samples)

    window.edit_panel.crop_button.setChecked(False)
    app.processEvents()

    # przesuwanie powiekszonego kadru
    view.zoom_to(2.0)
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()
    detail_times = []
    for i in range(15):
        start = time.perf_counter()
        window._render_detail(
            __import__("PySide6.QtCore", fromlist=["QRect"]).QRect(
                800 + i * 40, 600, 1200, 800
            ),
            2.0,
        )
        detail_times.append((time.perf_counter() - start) * 1000)
    summarise("doliczanie ostrego fragmentu", detail_times)

    window.grab().save(os.path.join(out_dir, "po_optymalizacji.png"))
    print(f"\nzrzut w {out_dir}")
    app.quit()


QTimer.singleShot(6000, run_tests)
sys.exit(app.exec())
