"""Pasek miniatur na dole okna."""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from .image_view import numpy_to_pixmap

THUMB_SIZE = QSize(150, 104)


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
        self._edited: set[str] = set()
        self._thumbnails: dict[str, QIcon] = {}
        self.currentItemChanged.connect(self._on_current_changed)

    def set_paths(self, paths: list[str], edited: set[str] | None = None) -> None:
        self.clear()
        self._edited = set(edited or ())
        # Miniatury przezywaja zmiane filtra formatow - te same pliki nie maja
        # powodu dekodowac sie drugi raz tylko dlatego, ze lista sie przepisala.
        self._thumbnails = {p: i for p, i in self._thumbnails.items() if p in set(paths)}
        placeholder = QPixmap(THUMB_SIZE)
        placeholder.fill(Qt.darkGray)
        icon = QIcon(placeholder)
        for path in paths:
            item = QListWidgetItem(self._thumbnails.get(path, icon), self._caption(path))
            item.setData(Qt.UserRole, path)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self.addItem(item)

    def _caption(self, path: str) -> str:
        """Kropka przed nazwa znaczy: to zdjecie ma juz zapisane korekty.

        Bez tego dzielenie obrobki na dni nie ma sensu - po otwarciu katalogu
        z 2000 zdjec trzeba widziec, gdzie sie skonczylo.
        """
        name = os.path.basename(path)
        return f"• {name}" if path in self._edited else name

    def set_edited(self, path: str, edited: bool) -> None:
        """Zmienia znacznik przy jednym zdjeciu."""
        if (path in self._edited) == edited:
            return
        self._edited.add(path) if edited else self._edited.discard(path)
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.UserRole) == path:
                base = item.text().lstrip("• ")
                item.setText(f"• {base}" if edited else base)
                return

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
