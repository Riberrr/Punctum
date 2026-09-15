"""Test obszaru klikania strzalek w polach liczbowych.

Zglaszony objaw: strzalka w gore reaguje tylko przy samej prawej krawedzi.
Sprawdzamy to tak, jak robi to uzytkownik - klikamy w SRODEK przycisku
i patrzymy, czy wartosc sie zmienila. Sam wyglad niczego nie dowodzi,
bo strzalka rysowala sie poprawnie takze wtedy, gdy nie dzialala.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSpinBox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication(sys.argv)

from punctum.app.settings_dialog import SettingsDialog  # noqa: E402
from punctum.app.style import stylesheet  # noqa: E402
from punctum.core.hardware import detect_system  # noqa: E402
from punctum.core.settings import Settings  # noqa: E402

out_dir = sys.argv[1] if len(sys.argv) > 1 else "out/spinbox"
os.makedirs(out_dir, exist_ok=True)

app.setStyleSheet(stylesheet())
dialog = SettingsDialog(Settings(), detect_system())
dialog.resize(600, 640)
dialog.show()
app.processEvents()

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def button_rect(spinbox, subcontrol):
    option = QStyleOptionSpinBox()
    option.initFrom(spinbox)
    option.subControls = QStyle.SC_SpinBoxUp | QStyle.SC_SpinBoxDown
    option.buttonSymbols = spinbox.buttonSymbols()
    option.frame = True
    return spinbox.style().subControlRect(QStyle.CC_SpinBox, option, subcontrol, spinbox)


def click(widget, point: QPoint) -> None:
    position = QPointF(point)
    globalpos = widget.mapToGlobal(point).toPointF()
    widget.mousePressEvent(
        QMouseEvent(QMouseEvent.Type.MouseButtonPress, position, globalpos,
                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    )
    widget.mouseReleaseEvent(
        QMouseEvent(QMouseEvent.Type.MouseButtonRelease, position, globalpos,
                    Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    )


BOXES = {
    "Wątki miniatur": dialog.threads_box,
    "Jakość JPEG": dialog.quality_box,
    "Opóźnienie detalu": dialog.detail_delay_box,
    "Blokada kółka": dialog.wheel_lockout_box,
    "Podgląd pikseli (ułamkowy)": dialog.pixel_peek_box,
}

print(f"{'pole':<30}{'szer. przycisku':>16}{'wysokość':>10}")
print("-" * 56)
for name, box in BOXES.items():
    box.setValue(max(box.minimum() + 2, box.value()))
    app.processEvents()
    up = button_rect(box, QStyle.SC_SpinBoxUp)
    down = button_rect(box, QStyle.SC_SpinBoxDown)
    print(f"{name:<30}{up.width():>16}{up.height():>10}")

    check(f"{name}: przycisk w górę ma sensowną szerokość", up.width() >= 14,
          f"{up.width()} px")
    check(f"{name}: przyciski nie nachodzą na siebie",
          up.bottom() <= down.top() + 1, f"góra kończy {up.bottom()}, dół zaczyna {down.top()}")

    # klikniecie w SRODEK przycisku, nie przy krawedzi
    before = box.value()
    click(box, up.center())
    app.processEvents()
    check(f"{name}: kliknięcie w środek zwiększa wartość", box.value() > before,
          f"{before} -> {box.value()}")

    before = box.value()
    click(box, down.center())
    app.processEvents()
    check(f"{name}: kliknięcie w środek zmniejsza wartość", box.value() < before,
          f"{before} -> {box.value()}")

    # lewa krawedz przycisku tez musi dzialac - to byl zgloszony problem
    before = box.value()
    click(box, QPoint(up.left() + 2, up.center().y()))
    app.processEvents()
    check(f"{name}: lewa krawędź przycisku działa", box.value() > before,
          f"{before} -> {box.value()}")

dialog.tabs.setCurrentIndex(0)
app.processEvents()
dialog.grab().save(os.path.join(out_dir, "spinbox_wydajnosc.png"))
dialog.tabs.setCurrentIndex(1)
app.processEvents()
dialog.grab().save(os.path.join(out_dir, "spinbox_podglad.png"))

print(f"\n{'test':<52}{'wynik':>8}   szczegóły")
print("-" * 92)
failures = 0
for name, ok, detail in results:
    failures += 0 if ok else 1
    print(f"{name:<52}{'OK' if ok else 'BŁĄD':>8}   {detail}")
print(f"\n{len(results) - failures} / {len(results)} testów przeszło")
print(f"zrzuty w {out_dir}")
