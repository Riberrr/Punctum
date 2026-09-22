"""Test podgladu usuwania szumu i przycisku "Przed / po" przy powiekszeniu.

Dwa bledy, ktore ten test pilnuje:
1. Ostry fragment przy powiekszeniu liczyla karta graficzna, a shader nie
   odszumia - po chwili na odszumiony podglad wjezdzal fragment z szumem
   i efekt suwaka "znikal".
2. Przy przytrzymanym "Przed / po" ostry fragment liczyl sie z korektami,
   wiec zdjecie bez korekt po chwili podmienialo sie z powrotem na "po".

Uzycie: python tools/test_szum_podglad_gui.py <plik RAW> [inne pliki...]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

import cv2
import numpy as np
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wspolne import czekaj, lancuch, wypisz, zdjecia  # noqa: E402

app = QApplication(sys.argv)

from punctum.app import MainWindow  # noqa: E402
from punctum.core import EditParams, is_jpeg  # noqa: E402
from punctum.core.denoise import noise_sigma  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


raw_path = next(p for p in zdjecia() if not is_jpeg(p))
workspace = tempfile.mkdtemp(prefix="punctum-szum-")
shutil.copy2(raw_path, os.path.join(workspace, os.path.basename(raw_path)))

window = MainWindow()
window.resize(1500, 950)
window.settings.save = lambda *args, **kwargs: True  # nie ruszamy ustawien uzytkownika
window.show()

# Zapisujemy kazdy ostry fragment, ktory trafia do widoku.
details: list[tuple[np.ndarray, object, float]] = []
_set_detail = window.view.set_detail


def spy_detail(rgb8, rect, scale):
    details.append((rgb8.copy(), rect, scale))
    _set_detail(rgb8, rect, scale)


window.view.set_detail = spy_detail
window.load_folder(workspace)


def sigma(rgb8: np.ndarray) -> float:
    y = cv2.cvtColor(rgb8, cv2.COLOR_RGB2YCrCb)[..., 0]
    s = noise_sigma(y, np.array([0, 256]))
    return float(s[0])


def gpu_reference(params: EditParams, rect, scale) -> np.ndarray | None:
    if not window.gpu_source_ready:
        return None
    return window.gpu.render(
        window.full_raw, params,
        max(1, round(rect.width() * scale)), max(1, round(rect.height() * scale)),
        region=(rect.x(), rect.y(), rect.width(), rect.height()), scale=scale,
    )


def pauza(ms: int) -> None:
    """Chwila ciszy z mieleniem zdarzen - czy nic nie wjedzie po czasie."""
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def stage_load() -> None:
    czekaj(app, lambda: window.full_raw is not None and window.current_image is not None,
           "wczytanie RAW-a", 30000)
    window.view.zoom_to(1.0)


def stage_noise_on() -> None:
    czekaj(app, lambda: len(details) > 0, "pierwszy ostry fragment")
    details.clear()
    window.edit_panel.sliders["noise_luminance"].set_value(50)
    window.edit_panel.sliders["noise_color"].set_value(25)
    window._on_params_changed()  # set_value moze nie wysylac sygnalu


def stage_noise_check() -> None:
    czekaj(app, lambda: len(details) > 0, "ostry fragment po ruchu suwaka", 30000)
    # po chwili nic nowego nie ma wjechac na odszumiony fragment
    pauza(1500)
    rgb8, rect, scale = details[-1]
    reference = gpu_reference(window.display_params(), rect, scale)
    if reference is None:
        check("porownanie z karta graficzna", True, "brak GPU - pominiete")
        return
    s_det, s_ref = sigma(rgb8), sigma(reference)
    check("ostry fragment przy powiekszeniu jest odszumiony", s_det < 0.7 * s_ref,
          f"sigma {s_det:.2f} wobec {s_ref:.2f} bez odszumiania")
    check("fragment liczony z pelnej rozdzielczosci, nie z podgladu",
          scale >= 0.99, f"skala {scale:.2f}")


def stage_before() -> None:
    details.clear()
    window._show_before()


def stage_before_check() -> None:
    czekaj(app, lambda: len(details) > 0, "ostry fragment przy 'przed'", 30000)
    pauza(1500)
    rgb8, rect, scale = details[-1]
    reference = gpu_reference(EditParams(), rect, scale)
    if reference is not None:
        diff = float(np.mean(np.abs(rgb8.astype(np.int16) - reference.astype(np.int16))))
        check("przy 'przed' ostry fragment jest bez korekt", diff < 2.0,
              f"srednia roznica {diff:.2f}")
    base = window.view.base_pixmap()
    check("przy 'przed' podglad nie zostal podmieniony na 'po'",
          base.width() == window.before_image.shape[1], f"{base.width()} px")
    details.clear()
    window._show_after()


def stage_after_check() -> None:
    czekaj(app, lambda: len(details) > 0, "ostry fragment po puszczeniu", 30000)
    rgb8, rect, scale = details[-1]
    reference = gpu_reference(window.display_params(), rect, scale)
    if reference is not None:
        s_det, s_ref = sigma(rgb8), sigma(reference)
        check("po puszczeniu 'przed' fragment znow odszumiony", s_det < 0.7 * s_ref,
              f"sigma {s_det:.2f} wobec {s_ref:.2f}")


def fine_energy(rgb8: np.ndarray) -> float:
    y = cv2.cvtColor(rgb8, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    return float(np.mean(np.abs(y - cv2.GaussianBlur(y, (0, 0), 1.0))))


def stage_sharpen_only() -> None:
    """Sam szum wylaczony, wyostrzanie domyslne: fragment tez z procesora."""
    details.clear()
    window.edit_panel.sliders["noise_luminance"].set_value(0)
    window.edit_panel.sliders["noise_color"].set_value(0)
    window._on_params_changed()


def stage_sharpen_check() -> None:
    czekaj(app, lambda: len(details) > 0, "fragment z samym wyostrzaniem", 30000)
    pauza(1500)
    rgb8, rect, scale = details[-1]
    reference = gpu_reference(window.display_params(), rect, scale)
    if reference is not None:
        e_det, e_ref = fine_energy(rgb8), fine_energy(reference)
        check("przy 1:1 fragment jest wyostrzony (nie z karty)", e_det > 1.15 * e_ref,
              f"energia drobnego pasma {e_det:.2f} wobec {e_ref:.2f}")


KOD = 0


def report() -> None:
    global KOD
    try:
        # wyjatek w etapie przerywa lancuch - pusta lista to tez porazka
        KOD = wypisz(results) if len(results) >= 4 else max(1, wypisz(results))
    finally:
        window.close()
        app.quit()
        shutil.rmtree(workspace, ignore_errors=True)


lancuch(app, [stage_load, stage_noise_on, stage_noise_check, stage_before,
              stage_before_check, stage_after_check, stage_sharpen_only,
              stage_sharpen_check], report)

app.exec()
sys.exit(KOD)
