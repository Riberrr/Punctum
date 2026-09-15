"""Prawa kolumna: histogram, dane zdjecia i suwaki korekt."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core import EditParams
from ..core.metadata import PhotoMetadata
from .sliders import TEMPERATURE_STOPS, TINT_STOPS, ParamSlider


class HistogramWidget(QFrame):
    """Histogram trzech kanalow, rysowany jak w Lightroomie - warstwami."""

    CHANNEL_COLORS = (QColor(230, 70, 70), QColor(70, 210, 90), QColor(80, 130, 245))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(104)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._data: np.ndarray | None = None

    def set_histogram(self, hist: np.ndarray | None) -> None:
        self._data = hist
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor(26, 26, 28))

        if self._data is None:
            painter.setPen(QColor(120, 120, 125))
            painter.drawText(rect, Qt.AlignCenter, "brak zdjęcia")
            return

        peak = float(self._data.max()) or 1.0
        # skala pierwiastkowa - inaczej jedna dominujaca wartosc splaszcza
        # caly wykres do kreski przy dolnej krawedzi
        scaled = np.sqrt(self._data / peak)

        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        width, height, bins = rect.width(), rect.height(), scaled.shape[1]

        for channel in range(3):
            path = QPainterPath()
            path.moveTo(rect.left(), rect.bottom())
            for i in range(bins):
                path.lineTo(
                    rect.left() + width * i / (bins - 1),
                    rect.bottom() - scaled[channel, i] * height,
                )
            path.lineTo(rect.right(), rect.bottom())
            path.closeSubpath()
            color = QColor(self.CHANNEL_COLORS[channel])
            color.setAlpha(150)
            painter.fillPath(path, color)


class InfoPanel(QFrame):
    """Najwazniejsze parametry zdjecia - to, co fotograf sprawdza odruchowo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("infoPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self.camera_label = QLabel("—")
        self.camera_label.setObjectName("cameraLabel")
        self.settings_label = QLabel("—")
        self.settings_label.setObjectName("settingsLabel")
        self.date_label = QLabel("—")
        self.gps_label = QLabel("—")
        for widget in (self.date_label, self.gps_label):
            widget.setObjectName("metaLabel")

        for widget in (self.camera_label, self.settings_label, self.date_label, self.gps_label):
            widget.setWordWrap(True)
            layout.addWidget(widget)

    def set_metadata(self, meta: PhotoMetadata | None) -> None:
        widgets = (self.camera_label, self.settings_label, self.date_label, self.gps_label)
        if meta is None:
            for widget in widgets:
                widget.setText("—")
            return
        self.camera_label.setText(meta.camera or "nieznany aparat")
        self.settings_label.setText(meta.summary())
        self.date_label.setText(
            meta.shot_at.strftime("%d.%m.%Y  %H:%M:%S") if meta.shot_at else "brak daty"
        )
        self.gps_label.setText(
            f"{meta.latitude:.5f}, {meta.longitude:.5f}" if meta.has_gps else "brak lokalizacji"
        )


class EditPanel(QWidget):
    """Komplet suwakow. Emituje sygnal po kazdej zmianie."""

    params_changed = Signal()
    reset_requested = Signal()
    auto_requested = Signal()
    crop_mode_toggled = Signal(bool)
    orientation_step = Signal(int)  # obrot o wielokrotnosc 90 stopni
    crop_reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sliders: dict[str, ParamSlider] = {}
        self._as_shot_temp = 5500.0
        self._loading = False

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        self.auto_button = QPushButton("Automatycznie")
        self.auto_button.setToolTip("Dobierz parametry tonalne na podstawie histogramu")
        self.auto_button.clicked.connect(self.auto_requested.emit)
        layout.addWidget(self.auto_button)

        layout.addWidget(self._section("Balans bieli"))
        self._add(layout, "temperature", "Temperatura", 2000, 15000, 5500, 0, " K",
                  gradient=TEMPERATURE_STOPS)
        self._add(layout, "tint", "Tinta", -100, 100, 0, gradient=TINT_STOPS)

        layout.addWidget(self._section("Odcień"))
        self._add(layout, "exposure", "Ekspozycja", -5, 5, 0, 2)
        self._add(layout, "contrast", "Kontrast", -100, 100, 0)
        self._add(layout, "highlights", "Podświetlenia", -100, 100, 0)
        self._add(layout, "shadows", "Cienie", -100, 100, 0)
        self._add(layout, "whites", "Biele", -100, 100, 0)
        self._add(layout, "blacks", "Czernie", -100, 100, 0)

        layout.addWidget(self._section("Obecność"))
        self._add(layout, "vibrance", "Jaskrawość", -100, 100, 0)
        self._add(layout, "saturation", "Nasycenie", -100, 100, 0)

        layout.addWidget(self._section("Kadrowanie i obrót"))
        self.crop_button = QPushButton("Kadruj")
        self.crop_button.setCheckable(True)
        self.crop_button.setToolTip(
            "Ciągnij za krawędzie, aby zmienić kadr (Shift zachowuje proporcje).\n"
            "Ciągnij poza kadrem, aby obrócić zdjęcie."
        )
        self.crop_button.toggled.connect(self.crop_mode_toggled.emit)
        layout.addWidget(self.crop_button)

        rotate_row = QHBoxLayout()
        rotate_row.setSpacing(4)
        for label, step, tip in (
            ("↺ 90°", -90, "Obróć w lewo"),
            ("180°", 180, "Obróć o 180°"),
            ("↻ 90°", 90, "Obróć w prawo"),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, s=step: self.orientation_step.emit(s))
            rotate_row.addWidget(button)
        layout.addLayout(rotate_row)

        self._add(layout, "rotation", "Kąt", -45, 45, 0, 1, "°")

        self.crop_reset_button = QPushButton("Wyzeruj kadr")
        self.crop_reset_button.clicked.connect(self.crop_reset_requested.emit)
        layout.addWidget(self.crop_reset_button)

        layout.addWidget(self._section("Redukcja szumu"))
        self._add(layout, "noise_luminance", "Luminancja", 0, 100, 0)
        self._add(layout, "noise_color", "Kolor", 0, 100, 25)

        self.reset_button = QPushButton("Wyzeruj wszystko")
        self.reset_button.clicked.connect(self.reset_requested.emit)
        layout.addSpacing(8)
        layout.addWidget(self.reset_button)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # --- budowanie ------------------------------------------------------

    def _section(self, title: str) -> QLabel:
        label = QLabel(title.upper())
        label.setObjectName("sectionLabel")
        return label

    def _add(self, layout, key, label, lo, hi, default=0.0, decimals=0, suffix="",
             gradient=None) -> None:
        slider = ParamSlider(key, label, lo, hi, default, decimals, suffix, gradient)
        slider.value_changed.connect(self._on_change)
        self.sliders[key] = slider
        layout.addWidget(slider)

    def _on_change(self, key: str, value: float) -> None:
        if not self._loading:
            self.params_changed.emit()

    # --- stan -----------------------------------------------------------

    def set_as_shot_temp(self, temp: float, tint: float) -> None:
        """Ustawia punkt wyjscia suwaka temperatury na nastawe z aparatu."""
        self._as_shot_temp = temp
        self._loading = True
        self.sliders["temperature"].default = temp
        self.sliders["temperature"].set_value(temp)
        self.sliders["tint"].set_value(0.0)
        self._loading = False

    def apply_values(self, values: dict[str, float]) -> None:
        """Wpisuje komplet wartosci naraz i przelicza podglad tylko raz."""
        self._loading = True
        for key, value in values.items():
            if key in self.sliders:
                self.sliders[key].set_value(value)
        self._loading = False
        self.params_changed.emit()

    def params(self, orientation: int = 0, crop=(0.0, 0.0, 1.0, 1.0)) -> EditParams:
        get = lambda key: self.sliders[key].value()  # noqa: E731
        temperature = get("temperature")
        return EditParams(
            temperature=None if abs(temperature - self._as_shot_temp) < 1.0 else temperature,
            tint=get("tint"),
            exposure=get("exposure"),
            contrast=get("contrast"),
            highlights=get("highlights"),
            shadows=get("shadows"),
            whites=get("whites"),
            blacks=get("blacks"),
            vibrance=get("vibrance"),
            saturation=get("saturation"),
            orientation=orientation,
            rotation=get("rotation"),
            crop=crop,
            noise_luminance=get("noise_luminance"),
            noise_color=get("noise_color"),
        )

    def set_rotation_silently(self, degrees: float) -> None:
        self._loading = True
        self.sliders["rotation"].set_value(degrees)
        self._loading = False

    def reset_all(self) -> None:
        self._loading = True
        for slider in self.sliders.values():
            slider.reset()
        self._loading = False
        self.params_changed.emit()
