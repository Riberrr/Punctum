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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setIconSize(THUMB_SIZE)
        self.setGridSize(QSize(THUMB_SIZE.width() + 14, THUMB_SIZE.height() + 30))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.setSpacing(2)
        self.setUniformItemSizes(True)
        self.currentItemChanged.connect(self._on_current_changed)

    def set_paths(self, paths: list[str]) -> None:
        self.clear()
        placeholder = QPixmap(THUMB_SIZE)
        placeholder.fill(Qt.darkGray)
        icon = QIcon(placeholder)
        for path in paths:
            item = QListWidgetItem(icon, os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self.addItem(item)

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
        item.setIcon(QIcon(pixmap))

    def current_path(self) -> str | None:
        item = self.currentItem()
        return None if item is None else item.data(Qt.UserRole)

    def _on_current_changed(self, current, previous) -> None:
        if current is not None:
            self.photo_selected.emit(current.data(Qt.UserRole))
