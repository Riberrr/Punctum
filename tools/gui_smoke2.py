"""Test nowych funkcji: automat, kadrowanie, ostry detal, redukcja szumu.

Sprawdza nie tylko czy kod sie wykonuje, ale czy efekt jest mierzalny:
odszumianie musi zmienic piksele, a doliczony detal musi byc ostrzejszy
od rozciagnietego proxy.
"""

from __future__ import annotations

import os
import sys

import numpy as np
from PySide6.QtCore import QRect, QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.app import MainWindow  # noqa: E402
from punctum.core import EditParams, develop, develop_region, load_raw  # noqa: E402

folder = sys.argv[1]
noisy = sys.argv[2]
out_dir = sys.argv[3]
os.makedirs(out_dir, exist_ok=True)


def sharpness(image: np.ndarray) -> float:
    """Wariancja laplasjanu - im wyzsza, tym wiecej realnych szczegolow."""
    import cv2

    grey = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(grey, cv2.CV_64F).var())


print("=" * 62)
print("TEST 1 — redukcja szumu faktycznie zmienia obraz")
raw = load_raw(noisy)
proxy = raw.proxy(1600)
base = EditParams(exposure=1.0)
without = develop(proxy, base, denoise=False)
with_nr = develop(proxy, EditParams(exposure=1.0, noise_luminance=70, noise_color=80))
diff = float(np.abs(without.astype(np.int16) - with_nr.astype(np.int16)).mean())
print(f"  srednia roznica piksela : {diff:.2f} poziomu  -> {'OK' if diff > 1.0 else 'BLAD'}")
print(f"  ziarnistosc bez redukcji: {sharpness(without):8.1f}")
print(f"  ziarnistosc po redukcji : {sharpness(with_nr):8.1f}  (ma byc nizsza)")

print("\nTEST 2 — detal z pelnej rozdzielczosci jest ostrzejszy niz proxy")
import cv2  # noqa: E402

zoom = 2.0
region = QRect(2000, 1400, 640, 480)
detail = develop_region(
    raw, base, (region.x(), region.y(), region.width(), region.height()), scale=zoom
)
full_w, full_h = raw.shape[1], raw.shape[0]
proxy_render = develop(proxy, base, denoise=False)
sx = proxy_render.shape[1] / full_w
patch = proxy_render[
    int(region.y() * sx) : int((region.y() + region.height()) * sx),
    int(region.x() * sx) : int((region.x() + region.width()) * sx),
]
patch_up = cv2.resize(patch, (detail.shape[1], detail.shape[0]), interpolation=cv2.INTER_LINEAR)
s_detail, s_proxy = sharpness(detail), sharpness(patch_up)
print(f"  proxy rozciagniete      : {s_proxy:8.1f}")
print(f"  detal z pelnej rozdz.   : {s_detail:8.1f}")
print(f"  zysk ostrosci           : {s_detail / max(s_proxy, 1e-6):8.1f}x  "
      f"-> {'OK' if s_detail > s_proxy * 2 else 'BLAD'}")
cv2.imwrite(os.path.join(out_dir, "detal_proxy.png"), cv2.cvtColor(patch_up, cv2.COLOR_RGB2BGR))
cv2.imwrite(os.path.join(out_dir, "detal_pelny.png"), cv2.cvtColor(detail, cv2.COLOR_RGB2BGR))

print("\nTEST 3 — geometria: obrot o 90 stopni i kadrowanie")
from punctum.core import geometry_size  # noqa: E402

print(f"  bez zmian               : {geometry_size(raw, EditParams())}")
print(f"  obrot 90                : {geometry_size(raw, EditParams(orientation=90))}")
print(f"  kadr polowa             : {geometry_size(raw, EditParams(crop=(0.25, 0.25, 0.75, 0.75)))}")
rotated = develop(proxy, EditParams(orientation=90, exposure=1.0), denoise=False)
print(f"  obrocony obraz          : {rotated.shape[1]}x{rotated.shape[0]}  "
      f"-> {'OK' if rotated.shape[0] > rotated.shape[1] else 'BLAD'}")

print("\nTEST 4 — okno i automatyczna korekcja")
app = QApplication(sys.argv)
window = MainWindow()
window.resize(1600, 1000)
window.show()
window.load_folder(folder)
print(f"  plikow w folderze       : {len(window.paths)}")


def stage_auto() -> None:
    print(f"  zdekodowane             : {window.full_raw is not None}")
    window._run_auto()


def stage_crop() -> None:
    values = {k: window.edit_panel.sliders[k].value()
              for k in ("exposure", "contrast", "highlights", "shadows", "whites", "blacks")}
    print(f"  automat ustawil         : {values}")
    window.edit_panel.crop_button.setChecked(True)
    window.crop = (0.12, 0.10, 0.88, 0.90)
    window.view.set_crop_fractions(window.crop)
    window.edit_panel.set_rotation_silently(3.5)
    window.view.set_rotation(3.5)
    window._render_preview()


def stage_shot() -> None:
    window.grab().save(os.path.join(out_dir, "okno_kadrowanie.png"))
    print(f"  tryb kadrowania         : {window.crop_mode}")
    window.edit_panel.crop_button.setChecked(False)
    window.edit_panel.sliders["noise_luminance"].set_value(60)
    window.edit_panel.sliders["noise_color"].set_value(70)
    window.view.zoom_to(2.0)


def stage_final() -> None:
    window.grab().save(os.path.join(out_dir, "okno_zoom.png"))
    print(f"  powiekszenie            : {window.view.zoom * 100:.0f} %")
    print(f"  rozmiar po kadrze       : {window.view.image_size}")
    print(f"\nzrzuty zapisane w {out_dir}")
    app.quit()


QTimer.singleShot(5500, stage_auto)
QTimer.singleShot(7500, stage_crop)
QTimer.singleShot(10000, stage_shot)
QTimer.singleShot(13500, stage_final)

sys.exit(app.exec())
