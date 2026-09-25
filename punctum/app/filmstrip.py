"""Pasek miniatur na dole okna."""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate

from .image_view import numpy_to_pixmap
from .markers import EDIT_ROLE, GEO_ROLE, LEGEND, PIN_SIZE, paint_dot, paint_pin
from ..przeklad import t

# Miniatura jest przechowywana w rozdzielczosci wyzszej niz wyswietlana:
# kafelki rosna razem z paskiem (do 260 px wysokosci), a obrazek 150 px
# rozciagniety do takiego kafelka bylby rozmyty. Kosztuje to okolo dwa razy
# wiecej pamieci na miniatury; czas wczytywania sie nie zmienia, bo i tak
# dekodujemy podglad wbudowany w plik, a nie pelne zdjecie.
THUMB_SIZE = QSize(300, 208)
THUMB_ASPECT = THUMB_SIZE.width() / THUMB_SIZE.height()
# Czesc wysokosci paska, ktora nie jest obrazkiem: podpis, odstepy i pasek
# przewijania. Przy dawnej stalej wysokosci 150 px dawalo to kafelek 104 px.
TILE_OVERHEAD = 46
TEXT_HEIGHT = 30


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
        self._fit_tiles(150)
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
        self.setToolTip(t(LEGEND))
        self.currentItemChanged.connect(self._on_current_changed)

    def _fit_tiles(self, height: int) -> None:
        """Kafelki dopasowane do wysokosci paska - jeden rzad, bez przewijania w pionie.

        Liczone z wysokosci calego widzetu, nie obszaru widoku: ten zmienia sie,
        gdy pojawia sie poziomy pasek przewijania, a zmiana kafelkow potrafi
        ten pasek schowac - i tak w kolko.
        """
        icon_height = max(40, height - TILE_OVERHEAD)
        icon = QSize(round(icon_height * THUMB_ASPECT), icon_height)
        if icon == self.iconSize():
            return
        self.setIconSize(icon)
        self.setGridSize(QSize(icon.width() + 14, icon.height() + TEXT_HEIGHT))

    def resizeEvent(self, event) -> None:
        self._fit_tiles(event.size().height())
        super().resizeEvent(event)

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
            item.setToolTip(f"{os.path.basename(path)}\n\n{t(LEGEND)}")
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
            item.setText(item.text() + t("  (błąd)"))
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
