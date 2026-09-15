"""Suwaki: zwykle oraz te z kolorowym rowkiem dla balansu bieli."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)

# Kierunek gradientow jest taki jak w Lightroomie: suwak pokazuje, w ktora
# strone pojdzie ZDJECIE, a nie jaki jest kolor swiatla. Dlatego przesuniecie
# w prawo (wyzsza temperatura barwowa swiatla) ociepla obraz.
TEMPERATURE_STOPS = [
    (0.00, QColor(28, 78, 208)),
    (0.25, QColor(112, 160, 232)),
    (0.50, QColor(216, 216, 216)),
    (0.75, QColor(242, 208, 112)),
    (1.00, QColor(255, 176, 0)),
]

TINT_STOPS = [
    (0.00, QColor(62, 190, 80)),
    (0.50, QColor(216, 216, 216)),
    (1.00, QColor(208, 64, 192)),
]


class GradientSlider(QSlider):
    """Suwak, ktorego rowek jest wypelniony gradientem barwnym."""

    def __init__(self, stops, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._stops = stops
        self.setMinimumHeight(18)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.CC_Slider, option, QStyle.SC_SliderGroove, self
        )
        handle = self.style().subControlRect(
            QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self
        )

        centre_y = self.height() / 2.0
        bar = QRectF(groove.left(), centre_y - 3.0, max(1, groove.width()), 6.0)

        gradient = QLinearGradient(bar.left(), 0.0, bar.right(), 0.0)
        for position, color in self._stops:
            gradient.setColorAt(position, color)

        path = QPainterPath()
        path.addRoundedRect(bar, 3.0, 3.0)
        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
        painter.drawPath(path)

        painter.setPen(QPen(QColor(24, 24, 26), 1))
        painter.setBrush(QColor(250, 250, 252))
        painter.drawEllipse(QPointF(handle.center().x(), centre_y), 6.0, 6.0)


class ParamSlider(QWidget):
    """Suwak z etykieta i wartoscia. Dwuklik przywraca wartosc domyslna."""

    value_changed = Signal(str, float)

    def __init__(
        self,
        key: str,
        label: str,
        minimum: float,
        maximum: float,
        default: float = 0.0,
        decimals: int = 0,
        suffix: str = "",
        gradient=None,
        parent=None,
    ):
        super().__init__(parent)
        self.key = key
        self.default = default
        self.decimals = decimals
        self.suffix = suffix
        self._scale = 10**decimals

        self.name_label = QLabel(label)
        self.value_label = QLabel()
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_label.setMinimumWidth(56)
        self.value_label.setObjectName("valueLabel")

        self.slider = GradientSlider(gradient) if gradient else QSlider(Qt.Horizontal)
        self.slider.setMinimum(int(round(minimum * self._scale)))
        self.slider.setMaximum(int(round(maximum * self._scale)))
        self.slider.setValue(int(round(default * self._scale)))
        self.slider.valueChanged.connect(self._on_slider)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(2)
        layout.addWidget(self.name_label, 0, 0)
        layout.addWidget(self.value_label, 0, 1)
        layout.addWidget(self.slider, 1, 0, 1, 2)

        self._refresh_label()

    def _on_slider(self, raw_value: int) -> None:
        self._refresh_label()
        self.value_changed.emit(self.key, self.value())

    def _refresh_label(self) -> None:
        value = self.value()
        text = f"{value:+.{self.decimals}f}" if self.default == 0 else f"{value:.{self.decimals}f}"
        self.value_label.setText(text + self.suffix)
        self.value_label.setStyleSheet(
            "color:#e8e8ea;" if abs(value - self.default) > 1e-9 else "color:#8a8a90;"
        )

    def value(self) -> float:
        return self.slider.value() / self._scale

    def set_value(self, value: float, silent: bool = False) -> None:
        self.slider.blockSignals(silent)
        self.slider.setValue(int(round(value * self._scale)))
        self.slider.blockSignals(False)
        self._refresh_label()

    def reset(self) -> None:
        self.set_value(self.default)

    def mouseDoubleClickEvent(self, event) -> None:
        self.reset()
