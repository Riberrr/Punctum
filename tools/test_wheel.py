"""Test zabezpieczenia suwakow przed przypadkowa zmiana kolkiem myszy.

Odtwarza zgloszony scenariusz: uzytkownik przewija liste suwakow, a kursor
przejezdza nad ktoryms z nich. Wartosc nie moze sie wtedy zmienic. Jednoczesnie
celowe uzycie - najedz i krec kolkiem - musi dzialac bez zmian.
"""

from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QEnterEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication(sys.argv)

from punctum.app import MainWindow  # noqa: E402

folder = sys.argv[1]
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def wheel(widget, notches: int = 1) -> None:
    """Wysyla zdarzenie kolka prosto do widzetu, jak zrobilby to system."""
    point = QPointF(widget.width() / 2, widget.height() / 2)
    event = QWheelEvent(
        point, widget.mapToGlobal(point.toPoint()).toPointF(),
        QPoint(0, 0), QPoint(0, 120 * notches),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
    )
    widget.wheelEvent(event)


def hover_enter(widget) -> None:
    """Symuluje wjechanie suwaka pod kursor (albo kursora na suwak)."""
    point = QPointF(widget.width() / 2, widget.height() / 2)
    widget.enterEvent(QEnterEvent(point, point, widget.mapToGlobal(point.toPoint()).toPointF()))


window = MainWindow()
window.resize(1500, 950)
window.show()
window.load_folder(folder)


def run() -> None:
    panel = window.edit_panel
    guard = panel.wheel_guard
    exposure = panel.sliders["exposure"].slider
    contrast = panel.sliders["contrast"].slider

    print(f"blokada po przewinięciu : {guard.lockout_ms} ms")
    print(f"wymagane zatrzymanie    : {guard.dwell_ms} ms\n")

    # --- 1. przewijanie listy nie zmienia suwaka ----------------------
    hover_enter(exposure)
    time.sleep((guard.dwell_ms + 80) / 1000.0)  # kursor stoi już dość długo
    before = exposure.value()
    guard.note_panel_scroll()  # użytkownik kręci kółkiem nad listą
    for _ in range(6):
        wheel(exposure)
        guard.note_panel_scroll()  # lista przewija się dalej
    check("przewijanie listy nie rusza suwaka", exposure.value() == before,
          f"{before} -> {exposure.value()}")

    # --- 2. suwak, który dopiero podjechał pod kursor ------------------
    guard._last_scroll = 0.0  # brak niedawnego przewijania
    hover_enter(contrast)  # suwak właśnie pojawił się pod kursorem
    before = contrast.value()
    wheel(contrast)
    check("świeżo najechany suwak nie reaguje", contrast.value() == before,
          f"{before} -> {contrast.value()}")

    # --- 3. celowe użycie nadal działa --------------------------------
    time.sleep((guard.dwell_ms + 80) / 1000.0)
    before = contrast.value()
    wheel(contrast, notches=1)
    check("najedź i kręć — działa", contrast.value() != before,
          f"{before} -> {contrast.value()}")

    before = contrast.value()
    wheel(contrast, notches=-1)
    check("kręcenie w drugą stronę — działa", contrast.value() < before,
          f"{before} -> {contrast.value()}")

    # --- 4. blokada wygasa po czasie ----------------------------------
    guard.note_panel_scroll()
    before = exposure.value()
    wheel(exposure)
    blocked = exposure.value() == before
    time.sleep((guard.lockout_ms + 120) / 1000.0)
    wheel(exposure)
    released = exposure.value() != before
    check("blokada działa i wygasa", blocked and released,
          f"zaraz po przewinięciu: {'głuchy' if blocked else 'ZMIENIŁ'}, "
          f"po {guard.lockout_ms} ms: {'reaguje' if released else 'NADAL GŁUCHY'}")

    # --- 5. da się wyłączyć w ustawieniach -----------------------------
    panel.set_wheel_protection(0)
    guard.note_panel_scroll()
    before = exposure.value()
    wheel(exposure)
    check("zero w ustawieniach wyłącza zabezpieczenie", exposure.value() != before,
          f"{before} -> {exposure.value()}")
    panel.set_wheel_protection(window.settings.wheel_lockout_ms,
                               window.settings.wheel_dwell_ms)

    # --- 6. samo przewiniecie panelu uruchamia blokade ----------------
    # To jest ogniwo, na ktorym cale zabezpieczenie stoi: pasek przewijania
    # panelu musi zglaszac arbitrowi kazde przewiniecie. Bez tego polaczenia
    # reszta logiki dziala, ale nigdy sie nie wlacza.
    scrollbar = panel.scroll_area.verticalScrollBar()
    guard._last_scroll = 0.0
    scrollbar.setValue(min(120, scrollbar.maximum()))
    app.processEvents()
    check("przewinięcie panelu zgłasza się arbitrowi", guard._last_scroll > 0.0,
          f"zakres paska: 0..{scrollbar.maximum()}")

    hover_enter(exposure)
    time.sleep((guard.dwell_ms + 80) / 1000.0)
    before = exposure.value()
    scrollbar.setValue(min(240, scrollbar.maximum()))
    app.processEvents()
    wheel(exposure)
    check("suwak głuchnie po realnym przewinięciu panelu", exposure.value() == before,
          f"{before} -> {exposure.value()}")

    # --- 7. ignorowane zdarzenie trafia do listy ----------------------
    if scrollbar.maximum() > 0:
        scrollbar.setValue(0)
        app.processEvents()
        guard.note_panel_scroll()
        point = QPointF(exposure.width() / 2, exposure.height() / 2)
        event = QWheelEvent(
            point, exposure.mapToGlobal(point.toPoint()).toPointF(),
            QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
            Qt.NoScrollPhase, False,
        )
        exposure.wheelEvent(event)
        check("zablokowane zdarzenie jest oddawane liście", not event.isAccepted(),
              "event.ignore() pozwala Qt przekazać je wyżej")
    else:
        check("lista ma pasek przewijania", False, "panel się nie przewija — sprawdź układ")

    print(f"{'test':<46}{'wynik':>8}   szczegóły")
    print("-" * 92)
    failures = 0
    for name, ok, detail in results:
        failures += 0 if ok else 1
        print(f"{name:<46}{'OK' if ok else 'BŁĄD':>8}   {detail}")
    print(f"\n{len(results) - failures} / {len(results)} testów przeszło")
    app.quit()


QTimer.singleShot(5500, run)
sys.exit(app.exec())
