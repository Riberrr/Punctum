"""Test eksportu: planowanie nazw, kolizje, praca w tle i pamiec korekt."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication(sys.argv)

from punctum.app import MainWindow  # noqa: E402
from punctum.app.export_dialog import ExportDialog  # noqa: E402
from punctum.core import EditParams  # noqa: E402
from punctum.core.export import (  # noqa: E402
    NAMING_CUSTOM,
    ON_EXISTING_OVERWRITE,
    ON_EXISTING_SKIP,
    ON_EXISTING_UNIQUE,
    ExportOptions,
    plan_export,
    resolve_conflicts,
)

folder = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "out/export"
os.makedirs(out_dir, exist_ok=True)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# ------------------------------------------------- planowanie bez interfejsu

print("=== PLANOWANIE NAZW ===")
with tempfile.TemporaryDirectory() as tmp:
    sources = [f"C:/foto/P117{i:04d}.RW2" for i in range(4)]

    options = ExportOptions(folder=tmp)
    plan = plan_export(sources, options)
    check("oryginalne nazwy zachowane",
          os.path.basename(plan.pairs[0][1]) == "P1170000.jpg",
          os.path.basename(plan.pairs[0][1]))

    options = ExportOptions(folder=tmp, use_subfolder=True, subfolder="Wysyłka")
    plan = plan_export(sources, options)
    check("podfolder trafia do ścieżki",
          os.path.basename(os.path.dirname(plan.pairs[0][1])) == "Wysyłka",
          plan.pairs[0][1])

    options = ExportOptions(folder=tmp, naming=NAMING_CUSTOM, custom_name="Wakacje",
                            start_number=7, number_digits=3)
    plan = plan_export(sources, options)
    names = [os.path.basename(t) for _, t in plan.pairs]
    check("numerator liczy od zadanej wartości", names[0] == "Wakacje-007.jpg", names[0])
    check("numerator rośnie co zdjęcie", names[3] == "Wakacje-010.jpg", names[3])

    options.number_digits = 5
    plan = plan_export(sources, options)
    check("liczba cyfr respektowana",
          os.path.basename(plan.pairs[0][1]) == "Wakacje-00007.jpg",
          os.path.basename(plan.pairs[0][1]))

    # kolizje z plikami juz istniejacymi
    options = ExportOptions(folder=tmp)
    first_target = plan_export(sources, options).pairs[0][1]
    with open(first_target, "w", encoding="utf-8") as handle:
        handle.write("zajęte")
    plan = plan_export(sources, options)
    check("kolizja wykryta przed startem", plan.has_conflicts and len(plan.conflicts) == 1,
          f"{len(plan.conflicts)} kolizji")

    pairs, skipped = resolve_conflicts(plan, ON_EXISTING_SKIP)
    check("pomijanie usuwa kolidujące", len(pairs) == 3 and skipped == 1,
          f"{len(pairs)} do zapisu, {skipped} pominięte")

    pairs, _ = resolve_conflicts(plan, ON_EXISTING_OVERWRITE)
    check("zastępowanie zachowuje wszystkie", len(pairs) == 4, f"{len(pairs)}")

    pairs, _ = resolve_conflicts(plan, ON_EXISTING_UNIQUE)
    check("nowe nazwy omijają istniejący plik",
          os.path.basename(pairs[0][1]) == "P1170000-2.jpg",
          os.path.basename(pairs[0][1]))

    # kolizja wewnatrz samej kolejki: dwa rozne pliki, ta sama nazwa docelowa
    same = ["C:/a/DSC001.RW2", "C:/b/DSC001.RW2"]
    plan = plan_export(same, ExportOptions(folder=tmp))
    targets = [t for _, t in plan.pairs]
    check("dwa źródła o tej samej nazwie nie nadpisują się",
          targets[0] != targets[1], os.path.basename(targets[1]))

# ------------------------------------------------------------- z interfejsem

window = MainWindow()
window.resize(1500, 950)
window.show()
window.load_folder(folder)

export_dir = os.path.join(os.path.abspath(out_dir), "wynik")
shutil.rmtree(export_dir, ignore_errors=True)
os.makedirs(export_dir, exist_ok=True)


def stage_edits() -> None:
    print("\n=== PAMIĘĆ KOREKT ===")
    panel = window.edit_panel
    panel.sliders["exposure"].set_value(1.25)
    panel.sliders["shadows"].set_value(40)
    app.processEvents()
    first = window.current_path

    window.filmstrip.setCurrentRow(1)
    app.processEvents()
    time.sleep(2.5)
    app.processEvents()
    check("nastawy zapisane przy zmianie zdjęcia", first in window.edits,
          f"{os.path.basename(first)}: EV{window.edits[first].exposure:+.2f}"
          if first in window.edits else "brak")
    check("nowe zdjęcie startuje bez korekt",
          abs(panel.sliders["exposure"].value()) < 1e-6,
          f"EV{panel.sliders['exposure'].value():+.2f}")

    window.filmstrip.setCurrentRow(0)
    app.processEvents()
    time.sleep(2.5)
    app.processEvents()
    check("powrót przywraca nastawy",
          abs(panel.sliders["exposure"].value() - 1.25) < 1e-6
          and abs(panel.sliders["shadows"].value() - 40) < 1e-6,
          f"EV{panel.sliders['exposure'].value():+.2f}, cienie {panel.sliders['shadows'].value():+.0f}")


def stage_dialog() -> None:
    print("\n=== OKNO EKSPORTU ===")
    sources = [p for p in window.paths if "~" not in p][:3]
    options = ExportOptions(folder=export_dir, naming=NAMING_CUSTOM,
                            custom_name="Test", start_number=1, max_side=1200)
    dialog = ExportDialog(options, sources, window)
    dialog.set_edited_count(1)
    dialog.resize(600, 620)
    dialog.show()
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()
    dialog.grab().save(os.path.join(out_dir, "okno_eksportu.png"))
    check("podgląd nazwy pokazuje pełną ścieżkę",
          "Test-001.jpg" in dialog.preview_label.text(), dialog.preview_label.text())
    check("ostrzeżenie o brakujących korektach widoczne", dialog.edited_hint.isVisible())
    check("przycisk eksportu aktywny przy poprawnym katalogu",
          dialog.export_button.isEnabled())
    dialog.folder_edit.setText("Z:\\nie ma takiego")
    app.processEvents()
    check("zły katalog blokuje eksport", not dialog.export_button.isEnabled(),
          dialog.preview_label.text())
    dialog.close()


def stage_export() -> None:
    print("\n=== EKSPORT W TLE ===")
    sources = [p for p in window.paths if "~" not in p][:3]
    options = ExportOptions(folder=export_dir, naming=NAMING_CUSTOM,
                            custom_name="Test", start_number=1, max_side=1000,
                            noise_quality="balanced")
    plan = plan_export(sources, options)
    pairs, _ = resolve_conflicts(plan, ON_EXISTING_OVERWRITE)
    params = {s: window.edits.get(s, EditParams()) for s, _ in pairs}

    from punctum.app.workers import ExportTask

    seen: list[tuple[int, int]] = []
    done_flag: list = []

    task = ExportTask(pairs, params, options)
    task.signals.export_progress.connect(lambda d, t, n: seen.append((d, t)))
    task.signals.export_finished.connect(lambda s, f, e: done_flag.append((s, f, e)))
    start = time.perf_counter()
    window.pool.start(task)

    deadline = start + 120
    while not done_flag and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.02)
    elapsed = time.perf_counter() - start

    if not done_flag:
        check("eksport zakończył się w rozsądnym czasie", False, "przekroczono 120 s")
    else:
        saved, failed, errors = done_flag[0]
        check("zapisano wszystkie zdjęcia", saved == len(pairs) and failed == 0,
              f"{saved} zapisanych, {failed} błędów")
        check("postęp raportowany po każdym pliku", len(seen) >= len(pairs),
              f"{len(seen)} zgłoszeń postępu")
        files = sorted(f for f in os.listdir(export_dir) if f.lower().endswith(".jpg"))
        check("pliki leżą na dysku pod właściwymi nazwami",
              files == ["Test-001.jpg", "Test-002.jpg", "Test-003.jpg"], str(files))
        if files:
            from PIL import Image
            with Image.open(os.path.join(export_dir, files[0])) as image:
                check("dłuższy bok ograniczony do 1000 px", max(image.size) == 1000,
                      f"{image.size[0]}x{image.size[1]}")
        print(f"  czas eksportu 3 zdjęć: {elapsed:.1f} s "
              f"({elapsed / max(len(pairs), 1):.1f} s na zdjęcie)")
    stage_report()


def stage_report() -> None:
    print(f"\n{'test':<52}{'wynik':>8}   szczegóły", flush=True)
    print("-" * 96, flush=True)
    failures = 0
    for name, ok, detail in results:
        failures += 0 if ok else 1
        print(f"{name:<52}{'OK' if ok else 'BŁĄD':>8}   {detail}", flush=True)
    print(f"\n{len(results) - failures} / {len(results)} testów przeszło", flush=True)
    # Zamkniecie okna przed wyjsciem: inaczej watki puli moga jeszcze trzymac
    # obiekty Qt i proces potrafi zawisnac na sprzataniu.
    window.close()
    app.quit()


def guarded(function):
    """Wyjatek w wywolaniu zwrotnym zegara Qt gubi sie bez sladu w logu."""
    def wrapper() -> None:
        import traceback
        try:
            function()
        except Exception:
            print(f"\nWYJĄTEK w {function.__name__}:", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            stage_report()
    return wrapper


QTimer.singleShot(5500, guarded(stage_edits))
QTimer.singleShot(13000, guarded(stage_dialog))
QTimer.singleShot(15500, guarded(stage_export))  # na koncu sam wywoluje stage_report

sys.exit(app.exec())
