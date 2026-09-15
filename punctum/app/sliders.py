"""Suwaki: zwykle, te z kolorowym rowkiem oraz obsluga kolka myszy."""

from __future__ import annotations

import time

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


class WheelGuard:
    """Rozstrzyga, czy kolko myszy nalezy do suwaka, czy do listy suwakow.

    Problem bierze sie stad, ze Qt kieruje zdarzenie kolka do widzetu pod
    kursorem. Przy przewijaniu dlugiej listy suwaki same podjezdzaja pod
    nieruchomy kursor i po drodze lapia zdarzenie - uzytkownik chcial
    przewinac panel, a zmienil ekspozycje.

    Stosujemy dwa niezalezne warunki:

    1. Blokada po przewinieciu. Kazde przewiniecie listy ustawia znacznik
       czasu; przez nastepne `lockout_ms` suwaki sa gluche na kolko. Dzieki
       temu ciagle przewijanie nigdy nie zahacza o zaden z nich.
    2. Wymog zatrzymania. Suwak przyjmuje kolko dopiero, gdy kursor jest nad
       nim od co najmniej `dwell_ms`. To lapie sytuacje, w ktorej suwak
       dopiero co podjechal pod kursor - `enterEvent` zeruje wtedy licznik.

    Celowe uzycie (najedz i kreci) dziala bez zmian, bo kursor stoi nad
    suwakiem dluzej niz prog, a lista nie byla ostatnio przewijana.
    """

    def __init__(self, lockout_ms: int = 400, dwell_ms: int = 220):
        self.lockout_ms = lockout_ms
        self.dwell_ms = dwell_ms
        self._last_scroll = 0.0

    def note_panel_scroll(self) -> None:
        self._last_scroll = time.monotonic()

    def allows(self, hovering_since: float) -> bool:
        if self.lockout_ms <= 0:
            return True  # zabezpieczenie wylaczone w ustawieniach
        now = time.monotonic()
        if (now - self._last_scroll) * 1000.0 < self.lockout_ms:
            return False
        if not hovering_since or (now - hovering_since) * 1000.0 < self.dwell_ms:
            return False
        return True


class WheelSlider(QSlider):
    """Suwak, ktory oddaje kolko liscie, gdy nie jest jego adresatem."""

    def __init__(self, guard: WheelGuard | None = None, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._guard = guard
        self._hovering_since = 0.0
        # StrongFocus zamiast domyslnego WheelFocus: samo krecenie kolkiem
        # nie ma przejmowac ogniska klawiatury
        self.setFocusPolicy(Qt.StrongFocus)

    def set_guard(self, guard: WheelGuard) -> None:
        self._guard = guard

    def enterEvent(self, event) -> None:
        self._hovering_since = time.monotonic()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovering_since = 0.0
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:
        if self._guard is None or self._guard.allows(self._hovering_since):
            super().wheelEvent(event)
        else:
            # ignore() przekazuje zdarzenie wyzej - do obszaru przewijania
            event.ignore()


class GradientSlider(WheelSlider):
    """Suwak, ktorego rowek jest wypelniony gradientem barwnym."""

    def __init__(self, stops, guard: WheelGuard | None = None, parent=None):
        super().__init__(guard, parent)
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
        guard: WheelGuard | None = None,
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

        self.slider = (
            GradientSlider(gradient, guard) if gradient else WheelSlider(guard)
        )
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
