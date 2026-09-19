"""Pasek miniatur na dole okna."""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate

from .image_view import numpy_to_pixmap
from .markers import EDIT_ROLE, GEO_ROLE, LEGEND, PIN_SIZE, paint_dot, paint_pin

THUMB_SIZE = QSize(150, 104)


class BadgeDelegate(QStyledItemDelegate):
    """Rysuje znaczniki w rogach kafelka, juz po zwyklym rysowaniu pozycji.

    Znaczniki nie moga siedziec w podpisie: podpis jest wysrodkowany, wiec
    kazdy dodatkowy znak przesuwalby nazwe pliku i lista przestawalaby sie
    czytac jedna pod druga.
    """

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        rect = option.rect
        width, height = PIN_SIZE
        if index.data(EDIT_ROLE):
            paint_dot(painter, QPointF(rect.left() + 11.0, rect.top() + 12.0))
        if index.data(GEO_ROLE):
            paint_pin(
                painter,
                QRectF(rect.right() - width - 6.0, rect.top() + 5.0, width, height),
            )


class Filmstrip(QListWidget):
    """Lista zdjec z folderu. Miniatury doplywaja asynchronicznie."""

    photo_selected = Signal(str)
    # Gotowa miniatura: sciezka i ikona. Slucha jej lista w zakladce mapy,
    # zeby obrazki doplywaly tam tak samo, jak do paska.
    thumbnail_ready = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setIconSize(THUMB_SIZE)
        self.setGridSize(QSize(THUMB_SIZE.width() + 14, THUMB_SIZE.height() + 30))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        # Wielokrotny wybor sluzy eksportowi wsadowemu. Podglad pokazuje
        # zawsze zdjecie biezace (currentItem), a zaznaczenie decyduje tylko
        # o tym, co trafi do eksportu.
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.setSpacing(2)
        self.setUniformItemSizes(True)
        self.setItemDelegate(BadgeDelegate(self))
        self._edited: set[str] = set()
        self._located: set[str] = set()
        self._thumbnails: dict[str, QIcon] = {}
        self.setToolTip(LEGEND)
        self.currentItemChanged.connect(self._on_current_changed)

    def set_paths(
        self,
        paths: list[str],
        edited: set[str] | None = None,
        located: set[str] | None = None,
    ) -> None:
        self.clear()
        self._edited = set(edited or ())
        self._located = set(located or ())
        # Miniatury przezywaja zmiane filtra formatow - te same pliki nie maja
        # powodu dekodowac sie drugi raz tylko dlatego, ze lista sie przepisala.
        self._thumbnails = {p: i for p, i in self._thumbnails.items() if p in set(paths)}
        placeholder = QPixmap(THUMB_SIZE)
        placeholder.fill(Qt.darkGray)
        icon = QIcon(placeholder)
        for path in paths:
            item = QListWidgetItem(
                self._thumbnails.get(path, icon), os.path.basename(path)
            )
            item.setData(Qt.UserRole, path)
            item.setData(EDIT_ROLE, path in self._edited)
            item.setData(GEO_ROLE, path in self._located)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            item.setToolTip(f"{os.path.basename(path)}\n\n{LEGEND}")
            self.addItem(item)

    def _item_for(self, path: str) -> QListWidgetItem | None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.UserRole) == path:
                return item
        return None

    def set_edited(self, path: str, edited: bool) -> None:
        """Zmienia znacznik poprawek przy jednym zdjeciu."""
        if (path in self._edited) == edited:
            return
        self._edited.add(path) if edited else self._edited.discard(path)
        item = self._item_for(path)
        if item is not None:
            item.setData(EDIT_ROLE, edited)

    def set_located(self, path: str, located: bool) -> None:
        """Zmienia znacznik wspolrzednych przy jednym zdjeciu."""
        if (path in self._located) == located:
            return
        self._located.add(path) if located else self._located.discard(path)
        item = self._item_for(path)
        if item is not None:
            item.setData(GEO_ROLE, located)

    def edited_paths(self) -> set[str]:
        """Zdjecia oznaczone jako poprawione - lista w mapie pokazuje to samo."""
        return set(self._edited)

    def located_count(self) -> int:
        return sum(
            1 for row in range(self.count())
            if self.item(row).data(Qt.UserRole) in self._located
        )

    def edited_count(self) -> int:
        return sum(
            1 for row in range(self.count())
            if self.item(row).data(Qt.UserRole) in self._edited
        )

    def set_thumbnail(self, index: int, image: np.ndarray | None) -> None:
        item = self.item(index)
        if item is None:
            return
        if image is None:
            item.setText(item.text() + "  (błąd)")
            return
        pixmap = numpy_to_pixmap(image).scaled(
            THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        icon = QIcon(pixmap)
        item.setIcon(icon)
        self._thumbnails[item.data(Qt.UserRole)] = icon
        self.thumbnail_ready.emit(item.data(Qt.UserRole), icon)

    def icons(self) -> dict[str, QIcon]:
        """Gotowe miniatury, po sciezkach - bez zastepczych szarych plam.

        Sluzy liscie w zakladce mapy: te same obrazki sa juz zdekodowane
        i trzymane tutaj, wiec nie ma powodu czytac plikow drugi raz.
        QIcon dzieli dane wewnetrznie, wiec slownik nic nie kopiuje.
        """
        return dict(self._thumbnails)

    def current_path(self) -> str | None:
        item = self.currentItem()
        return None if item is None else item.data(Qt.UserRole)

    def selected_paths(self) -> list[str]:
        """Zaznaczone zdjecia w kolejnosci, w jakiej leza w pasku."""
        chosen = {item.data(Qt.UserRole) for item in self.selectedItems()}
        return [
            self.item(row).data(Qt.UserRole)
            for row in range(self.count())
            if self.item(row).data(Qt.UserRole) in chosen
        ]

    def _on_current_changed(self, current, previous) -> None:
        if current is not None:
            self.photo_selected.emit(current.data(Qt.UserRole))
