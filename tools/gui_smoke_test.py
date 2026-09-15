"""Test GUI bez udzialu czlowieka.

Buduje okno, wczytuje folder, czeka az miniatury i podglad sie policza,
ustawia suwaki i zapisuje zrzut okna do pliku PNG. Dzieki temu mozna
sprawdzic dzialanie interfejsu, nie zabierajac uzytkownikowi ekranu.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.app import MainWindow  # noqa: E402

folder = sys.argv[1]
out_png = sys.argv[2] if len(sys.argv) > 2 else "gui_test.png"

app = QApplication(sys.argv)
window = MainWindow()
window.resize(1600, 1000)
window.show()

print(f"folder: {folder}")
window.load_folder(folder)
print(f"znalezione pliki RAW: {len(window.paths)}")
for path in window.paths[:5]:
    print(f"  - {os.path.basename(path)}")

steps: list[tuple[int, str]] = []


def stage_one() -> None:
    print(f"\nminiatury wczytane  : {sum(1 for _ in range(window.filmstrip.count()))}")
    print(f"wybrane zdjecie     : {window.current_path}")
    print(f"RAW zdekodowany     : {window.full_raw is not None}")
    if window.full_raw is not None:
        print(f"balans bieli z pliku: {window.full_raw.as_shot_temp:.0f} K")
        print(f"proxy               : {window.proxy.shape[1]}x{window.proxy.shape[0]}")
    print(f"podglad policzony   : {window.current_image is not None}")

    # ruszamy suwakami tak, jak zrobilby to uzytkownik
    window.edit_panel.sliders["exposure"].set_value(0.57)
    window.edit_panel.sliders["contrast"].set_value(7)
    window.edit_panel.sliders["highlights"].set_value(-76)
    window.edit_panel.sliders["shadows"].set_value(28)
    window.edit_panel.sliders["whites"].set_value(14)
    window.edit_panel.sliders["blacks"].set_value(-19)
    window.edit_panel.sliders["vibrance"].set_value(15)
    print("\nsuwaki ustawione, czekam na przeliczenie...")


def stage_two() -> None:
    params = window.edit_panel.params()
    print(f"parametry z panelu  : EV{params.exposure:+.2f} "
          f"swiatla {params.highlights:+.0f} cienie {params.shadows:+.0f}")
    print(f"podglad odswiezony  : {window.current_image is not None}")
    window.grab().save(out_png)
    print(f"\nzrzut okna zapisany : {out_png}")
    app.quit()


QTimer.singleShot(6000, stage_one)
QTimer.singleShot(9000, stage_two)

sys.exit(app.exec())
