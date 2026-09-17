"""Czy praca przezywa zamkniecie programu.

Test robi to, co uzytkownik: poprawia zdjecie, przechodzi dalej, zamyka okno,
otwiera program od nowa i sprawdza, czy suwaki wrocily. Sam zapis do pliku
sprawdza tools/test_sidecar.py - tutaj chodzi o cala droge przez interfejs.

Uzycie:  python tools/test_trwalosc_gui.py <plik.rw2> <plik.jpg> [wiecej...]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication(sys.argv)
# Test zamyka okno w srodku, zeby sprawdzic, co przezyje. Bez tego Qt uznaje
# zamkniecie ostatniego okna za koniec programu i test konczy sie w polowie.
app.setQuitOnLastWindowClosed(False)

from punctum.app import MainWindow  # noqa: E402
from punctum.core.settings import settings_path  # noqa: E402
from punctum.core.sidecar import has_edits, read_sidecar  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# Test rusza prawdziwy plik ustawien uzytkownika (ostatni katalog, historia),
# wiec zapamietujemy jego tresc i oddajemy ja na koncu.
SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

workspace = tempfile.mkdtemp(prefix="punctum-trwalosc-")
for source in sys.argv[1:]:
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))
photos = sorted(
    os.path.join(workspace, n) for n in os.listdir(workspace)
)
print(f"katalog testowy: {len(photos)} zdjec")

window = MainWindow()
window.resize(1400, 900)
window.show()
window.load_folder(workspace)
second: list[MainWindow] = []


def stage_edit() -> None:
    """Poprawia pierwsze zdjecie i przechodzi na drugie."""
    panel = window.edit_panel
    panel.sliders["exposure"].set_value(1.50)
    panel.sliders["shadows"].set_value(35)
    panel.sliders["vibrance"].set_value(20)
    app.processEvents()
    window.edited = window.current_path
    window.filmstrip.setCurrentRow(1)
    app.processEvents()


def stage_disk() -> None:
    first = window.edited
    check("plik z korektami powstal obok zdjecia", has_edits(first),
          os.path.basename(first))
    saved = read_sidecar(first)
    check("na dysku sa wlasciwe wartosci",
          saved is not None and abs(saved.exposure - 1.50) < 1e-6
          and abs(saved.shadows - 35) < 1e-6,
          "brak" if saved is None else f"EV{saved.exposure:+.2f}, cienie {saved.shadows:+.0f}")
    check("pasek miniatur oznacza poprawione zdjecie",
          window.filmstrip.item(0).text().startswith("•"),
          window.filmstrip.item(0).text())
    check("licznik w pasku stanu podaje postep",
          "poprawionych" in window.status.currentMessage()
          or window.filmstrip.edited_count() == 1,
          window.status.currentMessage())

    # zamkniecie programu, dokladnie jak u uzytkownika
    window.close()
    app.processEvents()


def stage_reopen() -> None:
    fresh = MainWindow()
    fresh.resize(1400, 900)
    fresh.show()
    fresh.load_folder(workspace)
    second.append(fresh)
    app.processEvents()


def stage_verify_list() -> None:
    fresh = second[0]
    check("po ponownym otwarciu znacznik jest na miejscu",
          fresh.filmstrip.item(0).text().startswith("•"),
          fresh.filmstrip.item(0).text())
    check("program wie, ile zdjec ma juz prace",
          fresh.filmstrip.edited_count() == 1,
          f"{fresh.filmstrip.edited_count()} z {len(fresh.paths)}")

    # Sedno calego pomyslu z dzieleniem pracy na dni: zdjecia poprawione
    # wczoraj nie sa dzis otwarte, a eksport i tak musi wziac ich nastawy.
    # Sprawdzamy to ZANIM zdjecie zostanie otwarte.
    yesterday = fresh._params_for(fresh.paths[0])
    check("eksport siega po prace z poprzedniej sesji, bez otwierania zdjecia",
          yesterday is not None and abs(yesterday.exposure - 1.50) < 1e-6,
          "brak" if yesterday is None else f"EV{yesterday.exposure:+.2f}")

    fresh.filmstrip.setCurrentRow(0)
    app.processEvents()


def stage_verify_sliders() -> None:
    fresh = second[0]
    panel = fresh.edit_panel
    exposure = panel.sliders["exposure"].value()
    shadows = panel.sliders["shadows"].value()
    vibrance = panel.sliders["vibrance"].value()
    check("suwaki wrocily takie, jak zostaly",
          abs(exposure - 1.50) < 1e-6 and abs(shadows - 35) < 1e-6
          and abs(vibrance - 20) < 1e-6,
          f"EV{exposure:+.2f}, cienie {shadows:+.0f}, jaskrawość {vibrance:+.0f}")
    check("pasek stanu mowi, ze wczytal korekty",
          "wczytano zapisane korekty" in fresh.status.currentMessage(),
          fresh.status.currentMessage())
    check("historia katalogow zapamietala folder",
          workspace in fresh.settings.recent_folders,
          str(fresh.settings.recent_folders[:2]))
    fresh.grab().save(os.path.join("out", "trwalosc_okno.png"))
    report()


def report() -> None:
    print(f"\n{'test':<52}{'wynik':>8}   szczegoly", flush=True)
    print("-" * 110, flush=True)
    failures = 0
    for name, ok, detail in results:
        failures += 0 if ok else 1
        print(f"{name:<52}{'OK' if ok else 'BLAD':>8}   {detail}", flush=True)
    print(f"\n{len(results) - failures} / {len(results)} testow przeszlo", flush=True)

    for opened in second:
        opened.close()
    shutil.rmtree(workspace, ignore_errors=True)
    if BACKUP is not None:  # oddajemy uzytkownikowi jego ustawienia
        with open(SETTINGS_FILE, "wb") as handle:
            handle.write(BACKUP)
    elif os.path.exists(SETTINGS_FILE):
        os.remove(SETTINGS_FILE)
    app.quit()


def guarded(function):
    def wrapper() -> None:
        import traceback
        try:
            function()
        except Exception:
            print(f"\nWYJATEK w {function.__name__}:", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            report()
    return wrapper


os.makedirs("out", exist_ok=True)
QTimer.singleShot(5000, guarded(stage_edit))
QTimer.singleShot(9000, guarded(stage_disk))
QTimer.singleShot(11000, guarded(stage_reopen))
QTimer.singleShot(17000, guarded(stage_verify_list))
QTimer.singleShot(21000, guarded(stage_verify_sliders))

sys.exit(app.exec())
