"""Ile trwa zbudowanie glownego okna - z mapa i bez niej."""

import os
import sys
import time

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication(sys.argv)

from punctum.app import MainWindow  # noqa: E402

start = time.perf_counter()
window = MainWindow()
build = (time.perf_counter() - start) * 1000
window.show()
app.processEvents()
shown = (time.perf_counter() - start) * 1000

lazy = getattr(window, "map_view", None) is None
print(f"budowa okna     : {build:6.0f} ms")
print(f"do pokazania    : {shown:6.0f} ms")
print(f"mapa            : {'jeszcze nie powstala (leniwie)' if lazy else 'zbudowana od razu'}")

if lazy:
    start = time.perf_counter()
    window.tabs.setCurrentIndex(1)
    app.processEvents()
    print(f"pierwsze wejscie na zakladke mapy: {(time.perf_counter() - start) * 1000:.0f} ms")

window.close()
