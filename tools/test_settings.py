"""Test ustawien: wykrywanie sprzetu, okno, zapis i faktyczne przelaczanie toru.

Najwazniejsze jest ostatnie: wybor w oknie ustawien ma naprawde zmieniac to,
co liczy obraz. Samo zapamietanie wartosci w pliku niczego nie zalatwia.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication(sys.argv)

from punctum.app import MainWindow  # noqa: E402
from punctum.app.settings_dialog import SettingsDialog  # noqa: E402
from punctum.core.settings import ENGINE_AUTO, ENGINE_CPU, ENGINE_GPU, Settings  # noqa: E402

folder = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "out/settings"
os.makedirs(out_dir, exist_ok=True)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# --------------------------------------------------------- zapis i odczyt

print("=== ZAPIS USTAWIEŃ ===")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "podkatalog", "settings.json")
    original = Settings(render_engine=ENGINE_CPU, preview_size=2048, export_quality=88,
                        noise_delay_ms=400, pixel_peek_zoom=3.5)
    check("zapis tworzy katalog", original.save(path), path)
    loaded = Settings.load(path)
    check("odczyt zwraca te same wartości",
          loaded.render_engine == ENGINE_CPU and loaded.preview_size == 2048
          and loaded.export_quality == 88 and loaded.noise_delay_ms == 400,
          f"silnik={loaded.render_engine} podgląd={loaded.preview_size}")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{to nie jest poprawny json")
    check("uszkodzony plik nie wywala programu", Settings.load(path).render_engine == ENGINE_AUTO)

    with open(path, "w", encoding="utf-8") as handle:
        handle.write('{"render_engine": "kosmos", "preview_size": 99999, "nieznany_klucz": 1}')
    recovered = Settings.load(path)
    check("wartości spoza zakresu są przycinane",
          recovered.render_engine == ENGINE_AUTO and recovered.preview_size in (1200, 3200),
          f"silnik={recovered.render_engine} podgląd={recovered.preview_size}")

# --------------------------------------------------------------- aplikacja

window = MainWindow()
window.resize(1600, 1000)
window.show()
window.load_folder(folder)

print("\n=== WYKRYTY SPRZĘT ===")
print(f"  procesor : {window.system.cpu.summary}")
print(f"  karta    : {window.system.gpu.summary}")
print(f"  sterownik: {window.system.gpu.driver}")
print(f"  GLSL     : {window.system.gpu.glsl}")
print(f"  system   : {window.system.system}")


def render_checksum() -> float:
    """Srednia jasnosc podgladu - sluzy do porownania obu torow."""
    return float(window.current_image.mean()) if window.current_image is not None else -1.0


def stage_engines() -> None:
    check("procesor rozpoznany", window.system.cpu.name != "nieznany", window.system.cpu.name)
    check("liczba rdzeni odczytana", window.system.cpu.cores_logical > 0,
          f"{window.system.cpu.cores_physical}/{window.system.cpu.cores_logical}")
    check("pamięć odczytana", window.system.cpu.memory_gb > 0.5,
          f"{window.system.cpu.memory_gb:.0f} GB")
    check("karta rozpoznana", window.system.gpu.available, window.system.gpu.name)

    window.edit_panel.sliders["exposure"].set_value(0.8)
    window.edit_panel.sliders["shadows"].set_value(35)
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()

    # --- tor GPU -----------------------------------------------------
    window.settings.render_engine = ENGINE_GPU
    window._apply_settings()
    window._render_preview()
    app.processEvents()
    gpu_ready = window.gpu_source_ready
    start = time.perf_counter()
    window._render_preview()
    app.processEvents()
    gpu_ms = (time.perf_counter() - start) * 1000
    gpu_value = render_checksum()
    check("wymuszony GPU używa karty", gpu_ready, window._engine_name())

    # --- tor procesora -----------------------------------------------
    window.settings.render_engine = ENGINE_CPU
    window._apply_settings()
    check("wymuszony procesor zwalnia teksturę", not window.gpu_source_ready,
          window._engine_name())

    # Tor procesora liczy na watku roboczym, wiec trzeba poczekac na PRAWDZIWY
    # nowy wynik. Bez wyzerowania podgladu petla konczylaby sie natychmiast,
    # porownujac obraz z GPU sam ze soba - i test przechodzilby bez powodu.
    window.current_image = None
    window._render_preview()
    deadline = time.perf_counter() + 10.0
    while window.current_image is None and time.perf_counter() < deadline:
        app.processEvents()
    cpu_value = render_checksum()

    check("tor procesora faktycznie policzył obraz", window.current_image is not None)
    check("oba tory dają ten sam obraz", abs(gpu_value - cpu_value) < 1.0,
          f"GPU {gpu_value:.2f} vs procesor {cpu_value:.2f}")
    print(f"\n  średnia jasność podglądu: GPU {gpu_value:.3f}, procesor {cpu_value:.3f}")
    print("  (pomiar czasu obu torów jest w tools/test_gpu.py — tam oba są synchroniczne)")

    # --- powrót na automat -------------------------------------------
    window.settings.render_engine = ENGINE_AUTO
    window._apply_settings()
    window._render_preview()
    app.processEvents()
    check("powrót na automat wraca na kartę", window.gpu_source_ready, window._engine_name())

    # --- zmiana rozmiaru podglądu ------------------------------------
    window.settings.preview_size = 2560
    window._apply_settings()
    window._render_preview()
    app.processEvents()
    check("większy podgląd daje większy obraz",
          window.view.base_pixmap().width() > 2000,
          f"{window.view.base_pixmap().width()} px")

    # --- ukrycie nawigatora ------------------------------------------
    window.settings.show_navigator = False
    window._apply_settings()
    app.processEvents()
    check("nawigator daje się ukryć", not window.navigator.isVisible())
    window.settings.show_navigator = True
    window._apply_settings()


def stage_dialog() -> None:
    dialog = SettingsDialog(window.settings, window.system, window)
    dialog.resize(600, 620)
    dialog.show()
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()
    for index, name in enumerate(("wydajnosc", "podglad", "eksport", "o_programie")):
        dialog.tabs.setCurrentIndex(index)
        app.processEvents()
        time.sleep(0.25)
        app.processEvents()
        dialog.grab().save(os.path.join(out_dir, f"ustawienia_{index}_{name}.png"))
    check("okno ma cztery zakładki", dialog.tabs.count() == 4)
    check("wybór karty dostępny", dialog.engine_buttons["gpu"].isEnabled())
    dialog.close()


def stage_report() -> None:
    print(f"\n{'test':<42}{'wynik':>8}   szczegóły")
    print("-" * 86)
    failures = 0
    for name, ok, detail in results:
        failures += 0 if ok else 1
        print(f"{name:<42}{'OK' if ok else 'BŁĄD':>8}   {detail}")
    print(f"\n{len(results) - failures} / {len(results)} testów przeszło")
    window.grab().save(os.path.join(out_dir, "okno_glowne.png"))
    print(f"zrzuty w {out_dir}")
    app.quit()


QTimer.singleShot(5500, stage_engines)
QTimer.singleShot(9500, stage_dialog)
QTimer.singleShot(12500, stage_report)

sys.exit(app.exec())
