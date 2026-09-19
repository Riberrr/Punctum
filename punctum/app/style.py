"""Ciemny motyw okna - fotografie oglada sie na neutralnym tle.

Arkusz jest szablonem: `@ASSETS@` zamieniamy w czasie dzialania na sciezke
do katalogu z grafikami. Qt wymaga w `url()` sciezki bezwzglednej albo
wzgledem katalogu roboczego, a ten zalezy od sposobu uruchomienia programu.
Zawsze uzywac funkcji `stylesheet()`, nie stalej `STYLESHEET_TEMPLATE`.
"""

from __future__ import annotations

import os

ASSETS_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def stylesheet() -> str:
    """Gotowy arkusz stylow z podstawiona sciezka do grafik."""
    # Qt oczekuje w url() ukosnikow w przod, takze na Windowsie
    return STYLESHEET_TEMPLATE.replace("@ASSETS@", ASSETS_DIRECTORY.replace("\\", "/"))


STYLESHEET_TEMPLATE = """
QWidget {
    background: #1e1e20;
    color: #c8c8cc;
    font-family: "Segoe UI", sans-serif;
    font-size: 12px;
}
QMainWindow::separator { background: #131315; width: 1px; height: 1px; }

#sectionLabel {
    color: #7a7a82;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 12px 0 2px 0;
}
#valueLabel { color: #8a8a90; }
#infoPanel { background: #232326; border: 1px solid #2e2e32; border-radius: 4px; }
#cameraLabel { color: #e8e8ea; font-weight: 600; }
#settingsLabel { color: #b8b8be; }
#metaLabel { color: #86868c; }
#sidePanel { background: #1b1b1d; border-left: 1px solid #2e2e32; }

/* Chowany fragment sekcji z danymi zdjecia: strzalka zamiast przycisku,
   zeby nie wygladala jak kolejna akcja do klikniecia. */
#sectionChevron {
    background: transparent; border: none;
    color: #7a7a82; padding: 0 4px; font-size: 11px;
}
#sectionChevron:hover { color: #e0e0e4; }
#sectionChevron:checked { color: #c8c8cc; }

QSlider::groove:horizontal {
    height: 3px; background: #3a3a40; border-radius: 1px;
}
QSlider::sub-page:horizontal { background: #4a4a52; border-radius: 1px; }
QSlider::handle:horizontal {
    background: #d0d0d6; width: 11px; height: 11px;
    margin: -4px 0; border-radius: 5px;
}
QSlider::handle:horizontal:hover { background: #ffffff; }

QPushButton {
    background: #2e2e33; border: 1px solid #3c3c42;
    border-radius: 3px; padding: 5px 12px;
}
QPushButton:hover { background: #3a3a41; }
QPushButton:pressed { background: #26262b; }
QPushButton:disabled { color: #5a5a60; background: #252528; }

QListWidget {
    background: #171719; border: none; outline: none;
}
QListWidget::item { color: #8a8a90; padding: 2px; border-radius: 3px; }
QListWidget::item:selected { background: #34343c; color: #ffffff; }

QScrollBar:horizontal { background: #171719; height: 9px; }
QScrollBar::handle:horizontal { background: #45454d; border-radius: 4px; min-width: 30px; }
QScrollBar:vertical { background: #1e1e20; width: 9px; }
QScrollBar::handle:vertical { background: #45454d; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }

/* Przyciski wyboru.  Bez jawnego stanu :checked motyw ciemny rysuje
   zaznaczony przycisk jako pusty prostokat - wyglada to jak brakujaca
   kontrolka, a nie jak wybrana opcja. */
QRadioButton, QCheckBox { spacing: 7px; padding: 2px 0; }
QRadioButton::indicator, QCheckBox::indicator {
    width: 13px; height: 13px;
    border: 1px solid #5d5d66;
    background: #2a2a2e;
}
QRadioButton::indicator { border-radius: 7px; }
QCheckBox::indicator { border-radius: 3px; }
QRadioButton::indicator:hover, QCheckBox::indicator:hover { border-color: #8a8a94; }
QRadioButton::indicator:checked {
    border-color: #b8b8c0;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 #eaeaee, stop:0.42 #eaeaee, stop:0.48 #2a2a2e, stop:1 #2a2a2e);
}
QCheckBox::indicator:checked { background: #d4d4da; border-color: #b8b8c0; }
QRadioButton:disabled, QCheckBox:disabled { color: #5a5a60; }

QGroupBox {
    border: 1px solid #333338;
    border-radius: 4px;
    margin-top: 9px;
    padding: 10px 10px 8px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 9px;
    padding: 0 5px;
    color: #9a9aa4;
}

QTabWidget::pane { border: 1px solid #333338; border-radius: 4px; top: -1px; }
QTabBar::tab {
    background: #232326; color: #9a9aa4;
    padding: 6px 14px; margin-right: 2px;
    border: 1px solid #333338;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
}
QTabBar::tab:selected { background: #1e1e20; color: #e8e8ea; border-bottom-color: #1e1e20; }
QTabBar::tab:hover:!selected { background: #2b2b30; }

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: #26262a; border: 1px solid #3c3c42;
    border-radius: 3px; padding: 4px 6px;
    selection-background-color: #45454f;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border-color: #6a6a76;
}
QComboBox::drop-down { border: none; width: 18px; }

/* Geometria strzałek w polach liczbowych.  Gdy arkusz stylów dotknie samego
   QSpinBox (tło, ramka, wypełnienie), Qt przestaje wyliczać położenie
   podelementów natywnie i przycisk strzałki kurczy się do paru pikseli przy
   prawej krawędzi — widać go w całości, ale klika się tylko jego skrawek.
   Dlatego trzeba podać wymiary jawnie. */
QSpinBox, QDoubleSpinBox { padding-right: 20px; }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    width: 18px;
    background: #2f2f35;
    border-left: 1px solid #3c3c42;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-position: top right;
    border-top-right-radius: 3px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-position: bottom right;
    border-bottom-right-radius: 3px;
    border-top: 1px solid #3c3c42;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #3c3c44; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background: #26262b; }
/* Strzalki podajemy jako obrazki.  Arkusze stylow Qt nie potrafia narysowac
   trojkata obramowaniem (wychodzi szary prostokat), a gdy przycisk jest
   ostylowany, Qt przestaje rysowac takze wlasny wskaznik - pole zostaje puste.
   Pliki powstaja z tools/make_assets.py; Qt sam siega po wariant @2x
   na ekranach o duzej gestosci pikseli. */
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("@ASSETS@/arrow-up.png");
    width: 9px; height: 5px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("@ASSETS@/arrow-down.png");
    width: 9px; height: 5px;
}
QSpinBox::up-arrow:disabled, QSpinBox::up-arrow:off,
QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:off {
    image: url("@ASSETS@/arrow-up-disabled.png");
}
QSpinBox::down-arrow:disabled, QSpinBox::down-arrow:off,
QDoubleSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:off {
    image: url("@ASSETS@/arrow-down-disabled.png");
}
QComboBox::down-arrow {
    image: url("@ASSETS@/arrow-down.png");
    width: 9px; height: 5px;
}
QComboBox QAbstractItemView {
    background: #26262a; border: 1px solid #3c3c42;
    selection-background-color: #3a3a44;
}

QStatusBar { background: #171719; color: #7a7a82; }
QStatusBar::item { border: none; }
QMenuBar { background: #171719; }
QMenuBar::item:selected { background: #34343c; }
QMenu { background: #232326; border: 1px solid #3a3a40; }
QMenu::item:selected { background: #34343c; }
QToolTip { background: #2e2e33; color: #e0e0e4; border: 1px solid #45454d; }
"""
