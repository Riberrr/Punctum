"""Plotno podgladu: wyswietlanie, powiekszanie, przesuwanie i kadrowanie.

Uklad wspolrzednych sceny to piksele obrazu wynikowego w PELNEJ rozdzielczosci,
niezaleznie od tego, co akurat jest wyswietlane. Dzieki temu ramka kadru,
nawigator i warstwa ostrego detalu mowia tym samym jezykiem.

Warstwy sa dwie. Spodnia to podglad z proxy, rozciagniety na cale zdjecie -
pojawia sie natychmiast, ale przy powiekszeniu jest miekki. Wierzchnia to
widoczny fragment przeliczony z pelnej rozdzielczosci prosto w rozdzielczosci
ekranu; doklada sie z opoznieniem ulamka sekundy i to ona daje ostrosc.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

HANDLE_GRAB_PX = 11  # promien chwytania uchwytu, w pikselach ekranu
ROTATE_BAND_PX = 70  # jak daleko poza kadrem lapie kursor obrotu
MIN_CROP_PX = 32  # najmniejszy dopuszczalny kadr


def numpy_to_pixmap(rgb8: np.ndarray) -> QPixmap:
    """Konwersja tablicy RGB uint8 na QPixmap."""
    rgb8 = np.ascontiguousarray(rgb8)
    height, width, _ = rgb8.shape
    image = QImage(rgb8.data, width, height, 3 * width, QImage.Format_RGB888)
    return QPixmap.fromImage(image.copy())


class ImageView(QGraphicsView):
    zoom_changed = Signal(float)
    view_rect_changed = Signal(QRectF)  # widoczny fragment, ulamki 0..1
    detail_needed = Signal(QRect, float)  # prostokat w pikselach zdjecia, skala
    crop_changed = Signal(tuple)  # (left, top, right, bottom) jako ulamki
    rotation_changed = Signal(float)  # nowy kat w stopniach

    MIN_ZOOM = 0.02
    MAX_ZOOM = 16.0
    DETAIL_DELAY_MS = 160

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._base = QGraphicsPixmapItem()
        self._base.setTransformationMode(Qt.SmoothTransformation)
        self._base.setZValue(0)
        # Bez pamieci podrecznej Qt przeskalowuje pixmape podgladu przy kazdym
        # odrysowaniu okna. Przy przeciaganiu ramki kadru to dziesiatki
        # przeskalowan 1600 px na sekunde, czyli caly budzet plynnosci.
        self._base.setCacheMode(QGraphicsPixmapItem.DeviceCoordinateCache)
        self._detail = QGraphicsPixmapItem()
        self._detail.setTransformationMode(Qt.SmoothTransformation)
        self._detail.setZValue(1)
        self._detail.hide()
        self._scene.addItem(self._base)
        self._scene.addItem(self._detail)
        self.setScene(self._scene)

        self.setRenderHints(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor(18, 18, 20))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setMouseTracking(True)

        self._zoom = 1.0
        self._fitted = True
        self._image_size = (0, 0)
        self._proxy_scale = 1.0

        # kadrowanie
        self._crop_mode = False
        self._crop = QRectF()
        self._drag_kind: str | None = None
        self._drag_handle: str | None = None
        self._drag_origin = QPointF()
        self._crop_at_press = QRectF()
        self._rotation = 0.0
        self._rotation_at_press = 0.0
        self._angle_at_press = 0.0

        self._detail_timer = QTimer(self)
        self._detail_timer.setSingleShot(True)
        self._detail_timer.setInterval(self.DETAIL_DELAY_MS)
        self._detail_timer.timeout.connect(self._request_detail)

    def set_detail_delay(self, milliseconds: int) -> None:
        self._detail_timer.setInterval(max(0, int(milliseconds)))

    # ----------------------------------------------------------- obrazy

    def set_image(self, rgb8: np.ndarray, image_size: tuple[int, int]) -> None:
        """Ustawia podglad. `image_size` to rozmiar obrazu w pelnej rozdzielczosci."""
        width, height = image_size
        first = self._base.pixmap().isNull()
        resized = self._image_size != (width, height)

        pixmap = numpy_to_pixmap(rgb8)
        self._base.setPixmap(pixmap)
        self._proxy_scale = pixmap.width() / float(max(width, 1))
        self._base.setScale(1.0 / self._proxy_scale if self._proxy_scale else 1.0)
        self._image_size = (width, height)
        self._scene.setSceneRect(0.0, 0.0, float(width), float(height))

        self.clear_detail()
        if first or resized:
            if not self._crop_mode or first:
                self._crop = QRectF(0.0, 0.0, float(width), float(height))
            self.fit_to_window()
        else:
            self._schedule_detail()
        self._emit_view_rect()

    def set_detail(self, rgb8: np.ndarray, rect: QRect, scale: float) -> None:
        if self._base.pixmap().isNull():
            return
        self._detail.setPixmap(numpy_to_pixmap(rgb8))
        self._detail.setScale(1.0 / scale if scale else 1.0)
        self._detail.setPos(float(rect.x()), float(rect.y()))
        self._detail.show()

    def clear_detail(self) -> None:
        self._detail.hide()

    def clear_image(self) -> None:
        self._base.setPixmap(QPixmap())
        self.clear_detail()
        self._image_size = (0, 0)
        self._scene.setSceneRect(0, 0, 0, 0)

    @property
    def image_size(self) -> tuple[int, int]:
        return self._image_size

    def base_pixmap(self) -> QPixmap:
        """Gotowa pixmapa podgladu - zeby nawigator nie konwertowal jej drugi raz."""
        return self._base.pixmap()

    # ---------------------------------------------------------- detal

    def _schedule_detail(self) -> None:
        self._detail_timer.start()

    def _request_detail(self) -> None:
        if self._base.pixmap().isNull() or self._crop_mode:
            return
        if self._zoom <= self._proxy_scale * 1.1:
            self.clear_detail()  # proxy jest juz wystarczajaco ostre
            return

        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        bounds = self._scene.sceneRect()
        region = visible.intersected(bounds)
        if region.width() < 2 or region.height() < 2:
            return

        rect = QRect(
            int(np.floor(region.left())),
            int(np.floor(region.top())),
            int(np.ceil(region.width())),
            int(np.ceil(region.height())),
        )
        self.detail_needed.emit(rect, float(self._zoom))

    # ------------------------------------------------------ powiekszanie

    def fit_to_window(self) -> None:
        if self._base.pixmap().isNull():
            return
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self._fitted = True
        self.zoom_changed.emit(self._zoom)
        self._after_view_change()

    def zoom_to(self, factor: float) -> None:
        if self._base.pixmap().isNull():
            return
        factor = max(self.MIN_ZOOM, min(self.MAX_ZOOM, factor))
        self.resetTransform()
        self.scale(factor, factor)
        self._zoom = factor
        self._fitted = False
        self.zoom_changed.emit(factor)
        self._after_view_change()

    def zoom_actual(self) -> None:
        self.zoom_to(1.0)

    def fit_zoom(self) -> float:
        """Powiekszenie, przy ktorym cale zdjecie miesci sie w oknie."""
        rect = self._scene.sceneRect()
        viewport = self.viewport().rect()
        if rect.isEmpty() or viewport.isEmpty():
            return 1.0
        return min(viewport.width() / rect.width(), viewport.height() / rect.height())

    def zoom_centred(self, factor: float) -> None:
        """Powiekszenie wokol srodka widoku - dla suwaka.

        `zoom_to` zaczyna od czystej transformacji, wiec przy kazdym ruchu
        suwaka widok wracalby w poblize lewego gornego rogu. Tutaj skalujemy
        wzgledem biezacego stanu, a kotwica "pod mysza" przy kursorze poza
        widokiem sama spada na srodek.
        """
        if self._base.pixmap().isNull():
            return
        factor = max(self.MIN_ZOOM, min(self.MAX_ZOOM, factor))
        self.scale(factor / self._zoom, factor / self._zoom)
        self._zoom = factor
        self._fitted = False
        self.zoom_changed.emit(factor)
        self._after_view_change()

    @property
    def zoom(self) -> float:
        return self._zoom

    def centre_on_normalised(self, x: float, y: float) -> None:
        width, height = self._image_size
        if width and height:
            self.centerOn(x * width, y * height)
            self._after_view_change()

    def _after_view_change(self) -> None:
        self._emit_view_rect()
        self._schedule_detail()

    def _emit_view_rect(self) -> None:
        width, height = self._image_size
        if not width or not height:
            self.view_rect_changed.emit(QRectF())
            return
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        self.view_rect_changed.emit(
            QRectF(
                visible.left() / width,
                visible.top() / height,
                visible.width() / width,
                visible.height() / height,
            )
        )

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._base.pixmap().isNull():
            return
        step = 1.0015 ** event.angleDelta().y()
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom * step))
        self.scale(new_zoom / self._zoom, new_zoom / self._zoom)
        self._zoom = new_zoom
        self._fitted = False
        self.zoom_changed.emit(new_zoom)
        self._after_view_change()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._crop_mode:
            return
        self.zoom_actual() if self._fitted else self.fit_to_window()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fitted:
            self.fit_to_window()
        else:
            self._after_view_change()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._emit_view_rect()
        self._schedule_detail()

    # ------------------------------------------------------- kadrowanie

    def set_crop_mode(self, enabled: bool) -> None:
        self._crop_mode = enabled
        self.setDragMode(QGraphicsView.NoDrag if enabled else QGraphicsView.ScrollHandDrag)
        if enabled:
            self.clear_detail()
            self.fit_to_window()
        else:
            self.unsetCursor()
            self._schedule_detail()
        self.viewport().update()

    def set_crop_fractions(self, crop: tuple[float, float, float, float]) -> None:
        width, height = self._image_size
        if not width or not height:
            return
        left, top, right, bottom = crop
        self._crop = QRectF(
            left * width, top * height, (right - left) * width, (bottom - top) * height
        )
        self.viewport().update()

    def crop_fractions(self) -> tuple[float, float, float, float]:
        width, height = self._image_size
        if not width or not height:
            return (0.0, 0.0, 1.0, 1.0)
        return (
            max(0.0, self._crop.left() / width),
            max(0.0, self._crop.top() / height),
            min(1.0, self._crop.right() / width),
            min(1.0, self._crop.bottom() / height),
        )

    def set_rotation(self, degrees: float) -> None:
        self._rotation = degrees

    def reset_crop(self) -> None:
        width, height = self._image_size
        self._crop = QRectF(0.0, 0.0, float(width), float(height))
        self.viewport().update()
        self.crop_changed.emit(self.crop_fractions())

    # --- trafianie w uchwyty --------------------------------------------

    def _handle_points(self) -> dict[str, QPointF]:
        crop, centre = self._crop, self._crop.center()
        return {
            "tl": QPointF(crop.left(), crop.top()),
            "tr": QPointF(crop.right(), crop.top()),
            "bl": QPointF(crop.left(), crop.bottom()),
            "br": QPointF(crop.right(), crop.bottom()),
            "t": QPointF(centre.x(), crop.top()),
            "b": QPointF(centre.x(), crop.bottom()),
            "l": QPointF(crop.left(), centre.y()),
            "r": QPointF(crop.right(), centre.y()),
        }

    def _handle_at(self, position: QPointF) -> str | None:
        """Ktory uchwyt lezy pod kursorem. `position` w pikselach widoku.

        Trafianie liczymy na ekranie, nie w scenie - uchwyt ma byc tak samo
        latwy do zlapania przy powiekszeniu 10 % i przy 400 %.

        Uwaga na typy: mapFromScene zwraca QPoint (calkowity), a pozycja
        zdarzenia to QPointF. Odejmowanie jednego od drugiego podnosi wyjatek,
        ktory Qt polyka - obsluga myszy przestaje wtedy dzialac bez sladu
        w interfejsie. Stad jawna konwersja obu stron na QPointF.
        """
        if self._crop.isNull():
            return None

        # najpierw rogi: przy malym kadrze pokrywaja sie z uchwytami krawedzi
        best_name, best_distance = None, float("inf")
        for name, point in self._handle_points().items():
            screen = QPointF(self.mapFromScene(point))
            dx, dy = screen.x() - position.x(), screen.y() - position.y()
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= HANDLE_GRAB_PX and distance < best_distance:
                best_name, best_distance = name, distance
                if len(name) == 2:  # rog wygrywa z krawedzia
                    best_distance = -1.0
        return best_name

    CURSORS = {
        "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
        "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
        "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
        "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
    }

    def mousePressEvent(self, event) -> None:
        if not self._crop_mode or event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        position = QPointF(event.position())
        scene_pos = self.mapToScene(event.position().toPoint())
        self._drag_origin = scene_pos
        self._crop_at_press = QRectF(self._crop)

        handle = self._handle_at(position)
        if handle:
            self._drag_kind, self._drag_handle = "resize", handle
        elif self._crop.contains(scene_pos):
            self._drag_kind = "move"
        else:
            self._drag_kind = "rotate"
            self._rotation_at_press = self._rotation
            centre = self._crop.center()
            self._angle_at_press = float(
                np.degrees(np.arctan2(scene_pos.y() - centre.y(), scene_pos.x() - centre.x()))
            )
        self.viewport().update()

    def mouseMoveEvent(self, event) -> None:
        position = QPointF(event.position())

        if self._crop_mode and self._drag_kind is None:
            handle = self._handle_at(position)
            if handle:
                self.setCursor(self.CURSORS[handle])
            elif self._crop.contains(self.mapToScene(event.position().toPoint())):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.CrossCursor)

        if self._drag_kind is None:
            super().mouseMoveEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        if self._drag_kind == "move":
            self._drag_move(scene_pos)
        elif self._drag_kind == "resize":
            self._drag_resize(scene_pos, bool(event.modifiers() & Qt.ShiftModifier))
        elif self._drag_kind == "rotate":
            self._drag_rotate(scene_pos)
        self.viewport().update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_kind is None:
            super().mouseReleaseEvent(event)
            return
        kind, self._drag_kind, self._drag_handle = self._drag_kind, None, None
        if kind == "rotate":
            self.rotation_changed.emit(self._rotation)
        else:
            self.crop_changed.emit(self.crop_fractions())
        self.viewport().update()

    def _bounds(self) -> QRectF:
        return self._scene.sceneRect()

    def _drag_move(self, scene_pos: QPointF) -> None:
        delta = scene_pos - self._drag_origin
        moved = self._crop_at_press.translated(delta)
        bounds = self._bounds()
        if moved.left() < bounds.left():
            moved.moveLeft(bounds.left())
        if moved.top() < bounds.top():
            moved.moveTop(bounds.top())
        if moved.right() > bounds.right():
            moved.moveRight(bounds.right())
        if moved.bottom() > bounds.bottom():
            moved.moveBottom(bounds.bottom())
        self._crop = moved

    def _drag_resize(self, scene_pos: QPointF, keep_aspect: bool) -> None:
        rect = QRectF(self._crop_at_press)
        bounds = self._bounds()
        x = float(np.clip(scene_pos.x(), bounds.left(), bounds.right()))
        y = float(np.clip(scene_pos.y(), bounds.top(), bounds.bottom()))
        handle = self._drag_handle or ""

        if "l" in handle:
            rect.setLeft(min(x, rect.right() - MIN_CROP_PX))
        if "r" in handle:
            rect.setRight(max(x, rect.left() + MIN_CROP_PX))
        if "t" in handle:
            rect.setTop(min(y, rect.bottom() - MIN_CROP_PX))
        if "b" in handle:
            rect.setBottom(max(y, rect.top() + MIN_CROP_PX))

        if keep_aspect and len(handle) == 2:
            source = self._crop_at_press
            ratio = source.width() / max(source.height(), 1e-6)
            height = rect.width() / ratio
            if "t" in handle:
                rect.setTop(rect.bottom() - height)
            else:
                rect.setBottom(rect.top() + height)
            rect = rect.intersected(bounds)

        self._crop = rect.intersected(bounds)

    def _drag_rotate(self, scene_pos: QPointF) -> None:
        centre = self._crop.center()
        angle = float(
            np.degrees(np.arctan2(scene_pos.y() - centre.y(), scene_pos.x() - centre.x()))
        )
        delta = angle - self._angle_at_press
        delta = (delta + 180.0) % 360.0 - 180.0
        self._rotation = float(np.clip(self._rotation_at_press + delta, -45.0, 45.0))
        self.rotation_changed.emit(self._rotation)

    # --- rysowanie nakladki ----------------------------------------------

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if not self._crop_mode or self._crop.isNull():
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Przyciemnienie tego, co wypadnie poza kadrem, rysujemy czterema
        # prostokatami. Roznica dwoch sciezek (QPainterPath.subtracted) daje
        # ten sam obraz, ale uruchamia algorytm przycinania wielokatow przy
        # KAZDYM odrysowaniu - a podczas przeciagania uchwytu odrysowan sa
        # dziesiatki na sekunde.
        shade = QBrush(QColor(0, 0, 0, 150))
        crop = self._crop
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), crop.top() - rect.top()), shade)
        painter.fillRect(QRectF(rect.left(), crop.bottom(), rect.width(), rect.bottom() - crop.bottom()), shade)
        painter.fillRect(QRectF(rect.left(), crop.top(), crop.left() - rect.left(), crop.height()), shade)
        painter.fillRect(QRectF(crop.right(), crop.top(), rect.right() - crop.right(), crop.height()), shade)

        pixel = 1.0 / max(self._zoom, 1e-6)  # stala grubosc linii na ekranie

        # siatka: trojpodzial w spoczynku, gestsza podczas przeciagania
        divisions = 8 if self._drag_kind else 3
        painter.setPen(QPen(QColor(255, 255, 255, 90), pixel))
        for i in range(1, divisions):
            x = self._crop.left() + self._crop.width() * i / divisions
            y = self._crop.top() + self._crop.height() * i / divisions
            painter.drawLine(QPointF(x, self._crop.top()), QPointF(x, self._crop.bottom()))
            painter.drawLine(QPointF(self._crop.left(), y), QPointF(self._crop.right(), y))

        painter.setPen(QPen(QColor(255, 255, 255, 220), pixel * 1.5))
        painter.drawRect(self._crop)

        # uchwyty - rysowane dokladnie tam, gdzie liczymy trafienie kursorem
        painter.setPen(QPen(QColor(40, 40, 44, 200), pixel))
        painter.setBrush(QColor(255, 255, 255, 240))
        for name, point in self._handle_points().items():
            size = (10.0 if len(name) == 2 else 8.0) * pixel
            painter.drawRect(QRectF(point.x() - size / 2, point.y() - size / 2, size, size))

        painter.restore()
