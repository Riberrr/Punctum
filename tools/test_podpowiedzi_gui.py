"""Podpowiedzi w prawdziwych oknach: pokrycie, dymek JPEG, wylacznik.

Przechodzi po oknie glownym (Edycja i Mapa, z panelem metadanych),
po Ustawieniach i po oknie eksportu i sprawdza, ze kazdy przycisk, suwak,
pole, lista i pole wyboru ma podpowiedz - wlasna albo odziedziczona po
wierszu suwaka. Wyjatki sa jawne: Zapisz / Anuluj / Eksportuj w dolnych
przyciskach okien i wewnetrzne widzety Qt.

Uzycie:  python tools/test_podpowiedzi_gui.py <plik.rw2> <plik.jpg> [wiecej...]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from PySide6.QtCore import QEvent, QPoint  # noqa: E402
from PySide6.QtGui import QHelpEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QDialogButtonBox,
    QLineEdit,
    QPlainTextEdit,
    QScrollBar,
    QTabBar,
    QTextEdit,
    QToolTip,
    QWidget,
)

from wspolne import czekaj, lancuch, wypisz, zdjecia  # noqa: E402

from punctum.app import MainWindow  # noqa: E402
from punctum.app.export_dialog import ExportDialog  # noqa: E402
from punctum.app.podpowiedzi import WLASCIWOSC  # noqa: E402
from punctum.app.settings_dialog import SettingsDialog  # noqa: E402
from punctum.core.export import ExportOptions  # noqa: E402
from punctum.core.settings import settings_path  # noqa: E402

KLASY = (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QLineEdit, QComboBox,
         QTextEdit, QPlainTextEdit)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

workspace = tempfile.mkdtemp(prefix="punctum-podpowiedzi-")
for source in zdjecia():
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))

window = MainWindow()
window.settings.save = lambda *a, **k: True  # zadnych sladow w ustawieniach
window.settings.store_edits = False
window.showMaximized()


def opis(w) -> str:
    for attr in ("text", "placeholderText", "objectName"):
        f = getattr(w, attr, None)
        if callable(f) and f():
            return f"{type(w).__name__} '{f()[:30]}'"
    return f"{type(w).__name__} w {type(w.parentWidget()).__name__}"


def ma_podpowiedz(w, root) -> bool:
    """Wlasna podpowiedz albo przodka - Qt przekazuje zdarzenie ToolTip
    w gore, wiec suwak w wierszu ParamSlider pokazuje dymek wiersza."""
    while w is not None and w is not root:
        if w.toolTip():
            return True
        w = w.parentWidget()
    return False


def bez_podpowiedzi(root) -> list[str]:
    braki = []
    for w in root.findChildren(QWidget):
        if not isinstance(w, KLASY) or isinstance(w, QScrollBar):
            continue
        if w.objectName().startswith("qt_"):
            continue  # wewnetrzne widzety Qt (np. rozwiniecie paska menu)
        if isinstance(w.parentWidget(), (QAbstractSpinBox, QComboBox, QTabBar)):
            continue  # czesci pol zlozonych - dymek ma cale pole
        if isinstance(w.parentWidget(), QDialogButtonBox) and not w.property(WLASCIWOSC):
            role = w.parentWidget().buttonRole(w)
            if role in (QDialogButtonBox.AcceptRole, QDialogButtonBox.RejectRole):
                continue  # Zapisz / Anuluj / Eksportuj - wyjatek z karty punktu
        if not ma_podpowiedz(w, root):
            braki.append(opis(w))
    return braki


def stage_start() -> None:
    window.load_folder(workspace)
    czekaj(app, lambda: window.full_raw is not None, "wczytanie pierwszego zdjecia")


def stage_okno() -> None:
    braki = bez_podpowiedzi(window)
    check("okno glowne: wszystko z podpowiedzia", not braki, "; ".join(braki[:8]))
    ep = window.edit_panel
    klucze = [s.property(WLASCIWOSC) for s in ep.sliders.values()]
    check("kazdy suwak ma swoj klucz", all(k and k.startswith("suwak.") for k in klucze),
          str(klucze))
    check("panel metadanych w Mapie tez opisany",
          not bez_podpowiedzi(window.map_tab))
    etykieta = window.exif_panel.findChildren(QWidget)
    check("etykiety pol EXIF dostaja ten sam dymek",
          any(getattr(w, "text", lambda: "")() == "Obiektyw" and "LensModel" in w.toolTip()
              for w in etykieta))


def stage_jpeg() -> None:
    ep = window.edit_panel
    ep.set_as_shot_temp(6500, 0, relative=True)
    tip_jpeg = ep.sliders["temperature"].toolTip()
    ep.set_as_shot_temp(5200, 0, relative=False)
    tip_raw = ep.sliders["temperature"].toolTip()
    check("temperatura JPEG: dopisek o kelwinach umownych", "umowne" in tip_jpeg)
    check("temperatura RAW: bez dopisku, z tytulem", "umowne" not in tip_raw and "Temperatura" in tip_raw)


def stage_metadane() -> None:
    button = window.info_panel.details_button
    button.setChecked(True)
    zwin = button.toolTip()
    button.setChecked(False)
    check("strzalka metadanych zmienia dymek", "Zwiń" in zwin and "Zwiń" not in button.toolTip())


def dymek_po_zdarzeniu(widget) -> bool:
    # hideText chowa dymek z opoznieniem - bez czekania poprzedni dymek
    # wygladalby jak nowy
    QToolTip.hideText()
    czekaj(app, lambda: not QToolTip.isVisible(), "schowanie dymka", 3000)
    pos = QPoint(4, 4)
    app.sendEvent(widget, QHelpEvent(QEvent.ToolTip, pos, widget.mapToGlobal(pos)))
    # bez `czekaj`: przy wylaczonych podpowiedziach brak dymku jest
    # oczekiwany, a `czekaj` drukowalby wtedy falszywy alarm
    koniec = time.perf_counter() + 1.5
    while time.perf_counter() < koniec:
        app.processEvents()
        if QToolTip.isVisible():
            return True
        time.sleep(0.02)
    return False


def stage_wylacznik() -> None:
    target = window.edit_panel.auto_button
    check("dymek pokazuje sie po najechaniu", dymek_po_zdarzeniu(target))
    window.settings.show_tooltips = False
    window._apply_settings()
    check("wylaczone podpowiedzi: dymek sie nie pokazuje", not dymek_po_zdarzeniu(target))
    window.settings.show_tooltips = True
    window._apply_settings()
    check("wlaczone z powrotem od razu", dymek_po_zdarzeniu(target))
    QToolTip.hideText()


def stage_ustawienia() -> None:
    dialog = SettingsDialog(window.settings, window.system, window)
    dialog.show()
    app.processEvents()
    braki = bez_podpowiedzi(dialog)
    check("Ustawienia: wszystko z podpowiedzia", not braki, "; ".join(braki[:8]))
    check("pole Pokazuj podpowiedzi zaznaczone", dialog.tooltips_box.isChecked())
    dialog.tooltips_box.setChecked(False)
    check("pole Pokazuj podpowiedzi trafia do ustawien",
          dialog._collect_from_widgets().show_tooltips is False)
    dialog.close()
    dialog.deleteLater()


def stage_eksport() -> None:
    sources = list(window.paths)[:2]
    dialog = ExportDialog(ExportOptions(folder=workspace), sources, window)
    dialog.show()
    app.processEvents()
    braki = bez_podpowiedzi(dialog)
    check("okno eksportu: wszystko z podpowiedzia", not braki, "; ".join(braki[:8]))
    dialog.close()
    dialog.deleteLater()


def finish() -> None:
    try:
        failures = wypisz(results)
    finally:
        window.hide()
        if BACKUP is not None:
            with open(SETTINGS_FILE, "wb") as handle:
                handle.write(BACKUP)
        shutil.rmtree(workspace, ignore_errors=True)
    app.exit(failures)


lancuch(app, [stage_start, stage_okno, stage_jpeg, stage_metadane, stage_wylacznik,
              stage_ustawienia, stage_eksport], finish)
sys.exit(app.exec())
