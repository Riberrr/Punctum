"""Test kadrowania sterowany symulowanymi zdarzeniami myszy.

Sprawdza to, co zglosil uzytkownik: czy zlapanie za narozniki i krawedzie
naprawde zmienia kadr, czy Shift zachowuje proporcje i czy ciagniecie poza
kadrem obraca zdjecie. Wczesniej obsluga myszy wywalala sie po cichu na
odejmowaniu QPoint od QPointF i zaden uchwyt nie dzialal.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.app import MainWindow  # noqa: E402

folder = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "out/crop"
os.makedirs(out_dir, exist_ok=True)

app = QApplication(sys.argv)
window = MainWindow()
window.resize(1600, 1000)
window.show()
window.load_folder(folder)

results: list[tuple[str, bool, str]] = []


def send(kind, pos: QPointF, buttons=Qt.LeftButton, modifiers=Qt.NoModifier) -> None:
    view = window.view
    types = {
        "press": QEvent.MouseButtonPress,
        "move": QEvent.MouseMove,
        "release": QEvent.MouseButtonRelease,
    }
    event = QMouseEvent(
        types[kind], pos, view.viewport().mapToGlobal(pos.toPoint()),
        Qt.LeftButton if kind != "move" else Qt.NoButton,
        buttons, modifiers,
    )
    {"press": view.mousePressEvent, "move": view.mouseMoveEvent,
     "release": view.mouseReleaseEvent}[kind](event)


def scene_to_view(x: float, y: float) -> QPointF:
    return QPointF(window.view.mapFromScene(QPointF(x, y)))


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def stage_enter_crop() -> None:
    window.edit_panel.crop_button.setChecked(True)


def stage_handles() -> None:
    view = window.view
    width, height = view.image_size
    check("tryb kadrowania włączony", view._crop_mode, f"rozmiar {width}x{height}")

    # 1. wykrywanie uchwytow
    corner = scene_to_view(0, 0)
    found = view._handle_at(corner)
    check("wykrycie narożnika", found == "tl", f"zwrócono {found!r}")
    edge = scene_to_view(width / 2, 0)
    found = view._handle_at(edge)
    check("wykrycie krawędzi górnej", found == "t", f"zwrócono {found!r}")
    middle = scene_to_view(width / 2, height / 2)
    check("środek kadru to nie uchwyt", view._handle_at(middle) is None, "")

    # 2. ciagniecie naroznika
    before = view.crop_fractions()
    send("press", scene_to_view(0, 0))
    send("move", scene_to_view(width * 0.25, height * 0.20))
    send("release", scene_to_view(width * 0.25, height * 0.20))
    after = view.crop_fractions()
    check(
        "ciągnięcie narożnika zmienia kadr",
        abs(after[0] - 0.25) < 0.02 and abs(after[1] - 0.20) < 0.02,
        f"{tuple(round(v, 3) for v in after)}",
    )

    # 3. ciagniecie krawedzi prawej
    send("press", scene_to_view(width, height * 0.6))
    send("move", scene_to_view(width * 0.80, height * 0.6))
    send("release", scene_to_view(width * 0.80, height * 0.6))
    after = view.crop_fractions()
    check("ciągnięcie krawędzi zmienia kadr", abs(after[2] - 0.80) < 0.02,
          f"prawa krawędź {after[2]:.3f}")

    # 4. Shift zachowuje proporcje
    view.set_crop_fractions((0.2, 0.2, 0.8, 0.8))
    ratio_before = (0.6 * width) / (0.6 * height)
    send("press", scene_to_view(width * 0.8, height * 0.8))
    send("move", scene_to_view(width * 0.6, height * 0.75), modifiers=Qt.ShiftModifier)
    send("release", scene_to_view(width * 0.6, height * 0.75), modifiers=Qt.ShiftModifier)
    left, top, right, bottom = view.crop_fractions()
    ratio_after = ((right - left) * width) / max((bottom - top) * height, 1e-6)
    check("Shift zachowuje proporcje", abs(ratio_after - ratio_before) / ratio_before < 0.03,
          f"{ratio_before:.3f} -> {ratio_after:.3f}")

    # 5. przesuwanie calego kadru
    view.set_crop_fractions((0.2, 0.2, 0.7, 0.7))
    send("press", scene_to_view(width * 0.45, height * 0.45))
    send("move", scene_to_view(width * 0.50, height * 0.45))
    send("release", scene_to_view(width * 0.50, height * 0.45))
    left, _, right, _ = view.crop_fractions()
    check("przesuwanie kadru", abs(left - 0.25) < 0.02, f"lewa krawędź {left:.3f}")

    # 6. obrot ciagnieciem poza kadrem
    view.set_crop_fractions((0.25, 0.25, 0.75, 0.75))
    rotation_before = view._rotation
    send("press", scene_to_view(width * 1.10, height * 0.5))
    send("move", scene_to_view(width * 1.10, height * 0.62))
    send("release", scene_to_view(width * 1.10, height * 0.62))
    check("ciągnięcie poza kadrem obraca", abs(view._rotation - rotation_before) > 0.5,
          f"{rotation_before:.2f}° -> {view._rotation:.2f}°")

    window.grab().save(os.path.join(out_dir, "kadrowanie.png"))


def stage_report() -> None:
    print(f"\n{'test':<38}{'wynik':>8}   szczegóły")
    print("-" * 78)
    failures = 0
    for name, ok, detail in results:
        failures += 0 if ok else 1
        print(f"{name:<38}{'OK' if ok else 'BŁĄD':>8}   {detail}")
    print(f"\n{len(results) - failures} / {len(results)} testów przeszło")
    print(f"zrzut w {out_dir}")
    app.quit()


QTimer.singleShot(5500, stage_enter_crop)
QTimer.singleShot(7500, stage_handles)
QTimer.singleShot(9000, stage_report)

sys.exit(app.exec())
