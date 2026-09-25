"""Sterowanie powiekszeniem w lewym panelu: suwak i przyciski."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from .podpowiedzi import podpowiedz
from ..przeklad import t

STEPS = 1000


class ZoomPanel(QWidget):
    """Suwak powiekszenia od "dopasuj" do maksimum podgladu.

    Skala jest logarytmiczna: miedzy dopasowaniem (np. 12 %) a 1600 %
    jest ponad sto razy, a przy skali liniowej caly zakres ponizej 100 %
    miescilby sie w pierwszych kilku pikselach suwaka.

    Panel nie zna widoku - dostaje biezace powiekszenie i dolna granice
    (`set_zoom`) i odpowiada sygnalami. Dzieki temu kolko myszy, przyciski
    i suwak zostaja zsynchronizowane jednym torem: widok zglasza zmiane,
    a panel tylko ja pokazuje.
    """

    zoom_requested = Signal(float)
    fit_requested = Signal()
    actual_requested = Signal()

    def __init__(self, max_zoom: float, parent=None):
        super().__init__(parent)
        self.max_zoom = max_zoom
        self._fit = 1.0

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, STEPS)
        podpowiedz(self.slider, "podglad.powiekszenie")
        self.slider.valueChanged.connect(self._on_slider)

        self.fit_button = QPushButton(t("Dopasuj"))
        podpowiedz(self.fit_button, "podglad.dopasuj")
        self.fit_button.clicked.connect(self.fit_requested.emit)
        self.actual_button = QPushButton("100 %")
        podpowiedz(self.actual_button, "podglad.sto")
        self.actual_button.clicked.connect(self.actual_requested.emit)
        self.zoom_label = QLabel("—")
        self.zoom_label.setMinimumWidth(44)
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # Stan dociagania ostrego fragmentu ("ostrzenie", "pelna ostrosc").
        # Siedzi pod suwakiem, bo dotyczy wlasnie powiekszenia.
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("metaLabel")

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(4)
        buttons.addWidget(self.fit_button)
        buttons.addWidget(self.actual_button)
        buttons.addStretch(1)
        buttons.addWidget(self.zoom_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.slider)
        layout.addLayout(buttons)
        layout.addWidget(self.detail_label)

    # --- przeliczenia ---------------------------------------------------

    def _span(self) -> float:
        return math.log(max(self.max_zoom / self._fit, 1.0001))

    def value_for(self, zoom: float) -> int:
        if zoom <= self._fit:
            return 0
        position = math.log(zoom / self._fit) / self._span()
        return max(0, min(STEPS, round(position * STEPS)))

    def zoom_for(self, value: int) -> float:
        return self._fit * math.exp(self._span() * value / STEPS)

    # --- stan -----------------------------------------------------------

    def set_zoom(self, zoom: float, fit: float) -> None:
        """Pokazuje powiekszenie ustawione w widoku (kolkiem, przyciskiem)."""
        self._fit = max(1e-6, min(fit, self.max_zoom))
        self.zoom_label.setText(f"{zoom * 100:.0f} %")
        self.slider.blockSignals(True)
        self.slider.setValue(self.value_for(zoom))
        self.slider.blockSignals(False)

    def clear(self) -> None:
        self.zoom_label.setText("—")
        self.detail_label.setText("")

    def _on_slider(self, value: int) -> None:
        # Skrajne lewe polozenie to "dopasuj", a nie liczba: po zmianie
        # rozmiaru okna widok ma dalej trzymac cale zdjecie.
        if value == 0:
            self.fit_requested.emit()
        else:
            self.zoom_requested.emit(self.zoom_for(value))
