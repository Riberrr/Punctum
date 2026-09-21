"""Nawigator: miniatura zdjecia z ramka pokazujaca powiekszony fragment."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QSizePolicy

from .image_view import numpy_to_pixmap


class Navigator(QFrame):
    """Pokazuje cale zdjecie i obszar aktualnie widoczny w oknie podgladu.

    Przy powiekszeniu 400 % latwo stracic orientacje, ktory to fragment kadru -
    ramka na miniaturze odpowiada na to pytanie bez zmniejszania widoku.
    Klikniecie w miniature przenosi podglad w to miejsce.
    """

    centre_requested = Signal(float, float)  # wspolrzedne 0..1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navigator")
        self.setMinimumHeight(120)
        # Wysokosc idzie za szerokoscia panelu: po poszerzeniu lewej kolumny
        # sama szerokosc zostawialaby miniature malenka w srodku szerokiego
        # pasa, a to przy duzym powiekszeniu jest jedyna mapa kadru.
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._pixmap: QPixmap | None = None
        self._view_rect: QRectF | None = None  # znormalizowany 0..1

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(120, round(width * 2 / 3))

    def sizeHint(self) -> QSize:
        return QSize(260, self.heightForWidth(260))

    def set_image(self, rgb8: np.ndarray | None) -> None:
        self._pixmap = None if rgb8 is None else numpy_to_pixmap(rgb8)
        self.update()

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        """Przyjmuje gotowa pixmape podgladu.

        Konwersja tablicy numpy na QPixmap kosztuje kilka milisekund przy
        obrazie 1600 px, a nawigator pokazuje dokladnie to samo, co plotno -
        nie ma powodu robic jej dwa razy w jednej klatce.
        """
        self._pixmap = None if pixmap is None or pixmap.isNull() else pixmap
        self.update()

    def set_view_rect(self, rect: QRectF | None) -> None:
        """Widoczny fragment jako ulamki szerokosci i wysokosci zdjecia."""
        self._view_rect = rect
        self.update()

    # --- rysowanie ------------------------------------------------------

    def _image_rect(self) -> QRectF | None:
        if self._pixmap is None or self._pixmap.isNull():
            return None
        area = QRectF(self.rect().adjusted(6, 6, -6, -6))
        size = self._pixmap.size()
        scale = min(area.width() / size.width(), area.height() / size.height())
        width, height = size.width() * scale, size.height() * scale
        return QRectF(
            area.left() + (area.width() - width) / 2.0,
            area.top() + (area.height() - height) / 2.0,
            width,
            height,
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(24, 24, 26))

        target = self._image_rect()
        if target is None:
            painter.setPen(QColor(110, 110, 116))
            painter.drawText(self.rect(), Qt.AlignCenter, "nawigator")
            return

        painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))

        if self._view_rect is None:
            return
        visible = QRectF(
            target.left() + self._view_rect.left() * target.width(),
            target.top() + self._view_rect.top() * target.height(),
            self._view_rect.width() * target.width(),
            self._view_rect.height() * target.height(),
        )
        if visible.width() >= target.width() and visible.height() >= target.height():
            return  # widac cale zdjecie, ramka nic by nie wniosla

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 160), 3))
        painter.drawRect(visible)
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1))
        painter.drawRect(visible)

    # --- interakcja -----------------------------------------------------

    def _emit_centre(self, position: QPointF) -> None:
        target = self._image_rect()
        if target is None or not target.contains(position):
            return
        self.centre_requested.emit(
            (position.x() - target.left()) / target.width(),
            (position.y() - target.top()) / target.height(),
        )

    def mousePressEvent(self, event) -> None:
        self._emit_centre(QPointF(event.position()))

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            self._emit_centre(QPointF(event.position()))
