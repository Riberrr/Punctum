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

import os

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer, Signal
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
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from .skala import px, pxf
from ..przeklad import t
from .style import ASSETS_DIRECTORY

HANDLE_GRAB_PX = 11  # promien chwytania uchwytu, w pikselach ekranu
SPLIT_GRAB_PX = 8  # jak blisko linii podzialu kursor ja chwyta
SPLIT_KNOB_PX = 12  # promien kolka na linii podzialu
ROTATE_BAND_PX = 70  # jak daleko poza kadrem lapie kursor obrotu
MIN_CROP_PX = 32  # najmniejszy dopuszczalny kadr


def draw_badge(painter: QPainter, text: str, x: float, top: float,
               right_aligned: bool = False) -> None:
    """Podpis "Przed" / "Po" na ciemnym tle, w pikselach okna. `x` to lewa
    krawedz podpisu albo - przy `right_aligned` - prawa."""
    metrics = painter.fontMetrics()
    width = metrics.horizontalAdvance(text) + pxf(14.0)
    box = QRectF(x - width if right_aligned else x, top, width, metrics.height() + pxf(6.0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(28, 28, 32, 190))
    painter.drawRoundedRect(box, pxf(4.0), pxf(4.0))
    painter.setPen(QColor(235, 235, 240))
    painter.drawText(box, Qt.AlignCenter, text)


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

        # Podzielony podglad przed/po (punkt 19). Wersja "przed" lezy nad
        # "po" w prostokacie, ktory przycina swoje dzieci do lewej strony
        # linii. Obie wersje zyja w tych samych wspolrzednych sceny, wiec
        # powiekszenie, przesuwanie i ostry fragment dzialaja bez zadnej
        # synchronizacji - tego nie dalyby dwa osobne widoki.
        self._split_clip = QGraphicsRectItem()
        self._split_clip.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)
        self._split_clip.setPen(QPen(Qt.NoPen))
        self._split_clip.setBrush(QBrush(Qt.NoBrush))
        self._split_clip.setZValue(2)
        self._split_clip.hide()
        self._before_base = QGraphicsPixmapItem(self._split_clip)
        self._before_base.setTransformationMode(Qt.SmoothTransformation)
        self._before_base.setCacheMode(QGraphicsPixmapItem.DeviceCoordinateCache)
        self._before_detail = QGraphicsPixmapItem(self._split_clip)
        self._before_detail.setTransformationMode(Qt.SmoothTransformation)
        self._before_detail.setZValue(1)
        self._before_detail.hide()
        self._scene.addItem(self._split_clip)
        self._split_on = False
        self._split = 0.5  # polozenie linii jako ulamek szerokosci zdjecia
        self._split_hover = False
        # podpis "Po" w rogu, gdy obok stoi widok "przed" (tryb obok siebie)
        self._after_badge = False

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

    def set_image(self, rgb8: np.ndarray, image_size: tuple[int, int],
                  odswiez_detal: bool = True) -> None:
        """Ustawia podglad. `image_size` to rozmiar obrazu w pelnej rozdzielczosci.

        `odswiez_detal=False`: ten sam stan nastaw (np. dojechalo odszumianie
        podgladu) - ostry fragment jest juz wlasciwy albo w drodze.
        """
        width, height = image_size
        first = self._base.pixmap().isNull()
        resized = self._image_size != (width, height)

        pixmap = numpy_to_pixmap(rgb8)
        self._base.setPixmap(pixmap)
        self._proxy_scale = pixmap.width() / float(max(width, 1))
        self._base.setScale(1.0 / self._proxy_scale if self._proxy_scale else 1.0)
        self._image_size = (width, height)
        self._scene.setSceneRect(0.0, 0.0, float(width), float(height))

        # Ostry fragment zostaje na miejscu, dopoki nie przyjdzie nowy (punkt 32):
        # chowanie go przy kazdym ruchu suwaka odslanialo na chwile rozmyty
        # podglad pod spodem - to byly mikromigniecia przy powiekszeniu.
        # Zmiane geometrii (obrot, kadr) zalatwia okno przez clear_detail.
        if first or resized:
            self._detail.hide()
            if not self._crop_mode or first:
                self._crop = QRectF(0.0, 0.0, float(width), float(height))
            self.fit_to_window()
        elif odswiez_detal:
            self._schedule_detail()
        self._update_split()
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
        self._before_detail.hide()

    def clear_image(self) -> None:
        self._base.setPixmap(QPixmap())
        self._before_base.setPixmap(QPixmap())
        self.clear_detail()
        self._image_size = (0, 0)
        self._scene.setSceneRect(0, 0, 0, 0)
        self._update_split()

    @property
    def image_size(self) -> tuple[int, int]:
        return self._image_size

    def base_pixmap(self) -> QPixmap:
        """Gotowa pixmapa podgladu - zeby nawigator nie konwertowal jej drugi raz."""
        return self._base.pixmap()

    # --------------------------------------------------- podzial przed/po

    def set_split(self, enabled: bool) -> None:
        """Wlacza linie podzialu. Obraz "przed" podaje okno (set_before_image) -
        widok nie wie, jak go policzyc."""
        self._split_on = enabled
        if not enabled:
            self._before_base.setPixmap(QPixmap())
            self._before_detail.hide()
            self._set_split_hover(False)
        self._update_split()

    @property
    def split_enabled(self) -> bool:
        return self._split_on

    @property
    def split_visible(self) -> bool:
        return self._split_clip.isVisible()

    @property
    def split_position(self) -> float:
        return self._split

    def set_split_position(self, fraction: float) -> None:
        self._split = float(np.clip(fraction, 0.0, 1.0))
        self._update_split()

    def set_before_image(self, rgb8: np.ndarray) -> None:
        """Obraz "przed" w tej samej geometrii co biezacy podglad."""
        pixmap = numpy_to_pixmap(rgb8)
        self._before_base.setPixmap(pixmap)
        self._before_base.setScale(self._image_size[0] / float(max(pixmap.width(), 1)))
        self._before_detail.hide()
        self._update_split()
        # ostry fragment "przed" trzeba dorysowac tak samo jak "po"
        self._schedule_detail()

    def set_before_detail(self, rgb8: np.ndarray, rect: QRect, scale: float) -> None:
        if self._before_base.pixmap().isNull():
            return
        self._before_detail.setPixmap(numpy_to_pixmap(rgb8))
        self._before_detail.setScale(1.0 / scale if scale else 1.0)
        self._before_detail.setPos(float(rect.x()), float(rect.y()))
        self._before_detail.show()

    def detail_visible(self) -> bool:
        """Czy ostry fragment strony "przed" jest na miejscu."""
        return self._before_detail.isVisible()

    def _update_split(self) -> None:
        width, height = self._image_size
        # W kadrowaniu podzial znika: ramka pokazuje zdjecie nieprzyciete,
        # a obraz "przed" jest liczony w geometrii kadru.
        visible = (
            self._split_on and not self._crop_mode and width > 0
            and not self._before_base.pixmap().isNull()
        )
        self._split_clip.setVisible(visible)
        if visible:
            self._split_clip.setRect(QRectF(0.0, 0.0, width * self._split, float(height)))
        self.viewport().update()

    def _split_line(self) -> tuple[float, float, float] | None:
        """Linia podzialu w pikselach okna: (x, gora, dol) albo None."""
        if not self._split_clip.isVisible():
            return None
        width, height = self._image_size
        top = self.mapFromScene(QPointF(width * self._split, 0.0))
        bottom = self.mapFromScene(QPointF(width * self._split, float(height)))
        view = self.viewport().rect()
        y0, y1 = max(float(top.y()), float(view.top())), min(float(bottom.y()), float(view.bottom()))
        if y1 <= y0:
            return None
        return float(top.x()), y0, y1

    def _near_split(self, position: QPointF) -> bool:
        line = self._split_line()
        if line is None:
            return False
        x, y0, y1 = line
        return abs(position.x() - x) <= px(SPLIT_GRAB_PX) and y0 <= position.y() <= y1

    def _set_split_hover(self, hover: bool) -> None:
        if hover == self._split_hover:
            return
        self._split_hover = hover
        # Kursor ustawiamy na viewporcie, bo tam trzyma go tryb przeciagania
        # dlonia; po zejsciu z linii wracamy do otwartej dloni. Bez tego trybu
        # (kadrowanie) viewport ma zostac bez kursora - wlasny przykrylby
        # kursory uchwytow ustawiane na samym widoku.
        if hover:
            self.viewport().setCursor(Qt.SplitHCursor)
        elif self.dragMode() == QGraphicsView.ScrollHandDrag:
            self.viewport().setCursor(Qt.OpenHandCursor)
        else:
            self.viewport().unsetCursor()

    # ---------------------------------------------------------- detal

    def _schedule_detail(self) -> None:
        self._detail_timer.start()

    def widoczny_fragment(self) -> tuple[QRect, float] | None:
        """Wycinek zdjecia na ekranie i powiekszenie - albo None, gdy ostry
        fragment nie jest potrzebny (podglad wystarcza albo trwa kadrowanie)."""
        if self._base.pixmap().isNull() or self._crop_mode:
            return None
        if self._zoom <= self._proxy_scale * 1.1:
            return None
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        region = visible.intersected(self._scene.sceneRect())
        if region.width() < 2 or region.height() < 2:
            return None
        rect = QRect(
            int(np.floor(region.left())),
            int(np.floor(region.top())),
            int(np.ceil(region.width())),
            int(np.ceil(region.height())),
        )
        return rect, float(self._zoom)

    def _request_detail(self) -> None:
        if self._base.pixmap().isNull() or self._crop_mode:
            return
        if self._zoom <= self._proxy_scale * 1.1:
            self.clear_detail()  # proxy jest juz wystarczajaco ostre
            return
        fragment = self.widoczny_fragment()
        if fragment is not None:
            self.detail_needed.emit(*fragment)

    # ------------------------------------------------------ powiekszanie

    def fit_to_window(self) -> None:
        if self._base.pixmap().isNull():
            return
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11() * self._gestosc()
        self._fitted = True
        self.zoom_changed.emit(self._zoom)
        self._after_view_change()

    def zoom_to(self, factor: float) -> None:
        if self._base.pixmap().isNull():
            return
        factor = max(self.MIN_ZOOM, min(self.MAX_ZOOM, factor))
        self.resetTransform()
        scale = factor / self._gestosc()
        self.scale(scale, scale)
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
        return min(viewport.width() / rect.width(), viewport.height() / rect.height()) * self._gestosc()

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

    def _gestosc(self) -> float:
        """Pikseli ekranu na piksel okna (skala Windows razy skala interfejsu).

        Powiekszenie `zoom` liczymy w pikselach EKRANU: 100 % ma pokazac jeden
        piksel zdjecia na jednym pikselu monitora, niezaleznie od tego, jak
        bardzo powiekszone sa napisy i przyciski. Transformacja widoku dziala
        w pikselach okna, wiec przelicza sie ja przez te gestosc.
        """
        return self.devicePixelRatioF() or 1.0

    def event(self, event) -> bool:
        if event.type() == QEvent.DevicePixelRatioChange and not self._base.pixmap().isNull():
            # Okno przeszlo na monitor o innej gestosci: ta sama transformacja
            # znaczy tam inne powiekszenie. Dopasowany widok dopasowujemy od
            # nowa, a przy recznym powiekszeniu trzymamy procent, nie transformacje.
            if self._fitted:
                self.fit_to_window()
            else:
                self.resetTransform()
                scale = self._zoom / self._gestosc()
                self.scale(scale, scale)
                self._after_view_change()
        return super().event(event)

    def zoom_about(self, factor: float, position: QPointF) -> None:
        """Powiekszenie wokol punktu okna - dla kolka nad widokiem "przed".

        Kotwica "pod mysza" liczy sie z polozenia kursora nad TYM widokiem,
        a kursor stoi wtedy nad sasiednim, wiec punkt trzymamy sami.
        """
        if self._base.pixmap().isNull():
            return
        factor = max(self.MIN_ZOOM, min(self.MAX_ZOOM, factor))
        point = self.mapToScene(position.toPoint())
        anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.scale(factor / self._zoom, factor / self._zoom)
        self.setTransformationAnchor(anchor)
        centre = QPointF(self.viewport().rect().center())
        self.centerOn(point + (centre - position) * (self._gestosc() / factor))
        self._zoom = factor
        self._fitted = False
        self.zoom_changed.emit(factor)
        self._after_view_change()

    def pan_by(self, dx: float, dy: float) -> None:
        """Przesuniecie o piksele okna, jak przeciagniecie dlonia."""
        self.horizontalScrollBar().setValue(round(self.horizontalScrollBar().value() - dx))
        self.verticalScrollBar().setValue(round(self.verticalScrollBar().value() - dy))

    def toggle_fit(self) -> None:
        self.zoom_actual() if self._fitted else self.fit_to_window()

    def set_after_badge(self, shown: bool) -> None:
        self._after_badge = shown
        self.viewport().update()

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
        # Kolko i podpisy podzialu stoja w miejscu okna, a nie zdjecia -
        # przesuniete kopiowaniem pikseli zostawialyby smuge.
        if self._split_clip.isVisible() or self._after_badge:
            self.viewport().update()
        self._emit_view_rect()
        self._schedule_detail()

    # ------------------------------------------------------- kadrowanie

    def set_crop_mode(self, enabled: bool) -> None:
        self._crop_mode = enabled
        self.setDragMode(QGraphicsView.NoDrag if enabled else QGraphicsView.ScrollHandDrag)
        if enabled:
            self.clear_detail()
            # "przed" w starej geometrii kadru po wyjsciu z kadrowania bylby
            # nieaktualny - okno policzy go od nowa
            self._before_base.setPixmap(QPixmap())
            self._set_split_hover(False)
            self.fit_to_window()
        else:
            self.unsetCursor()
            self._schedule_detail()
        self._update_split()

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
            if distance <= px(HANDLE_GRAB_PX) and distance < best_distance:
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

    _rotate_cursor_cache: QCursor | None = None

    def _rotate_cursor(self) -> QCursor:
        # Wariant @2x wybieramy sami: QPixmap z pliku, inaczej niz QIcon,
        # nie siega po niego automatycznie, a na ekranie 150 % kursor 32 px
        # bylby rozmyty. Goracy punkt w srodku luku, w pikselach logicznych.
        if ImageView._rotate_cursor_cache is None:
            hidpi = self.devicePixelRatioF() > 1.25
            name = "rotate-cursor@2x.png" if hidpi else "rotate-cursor.png"
            pixmap = QPixmap(os.path.join(ASSETS_DIRECTORY, name))
            if pixmap.isNull():
                return QCursor(Qt.CrossCursor)
            if hidpi:
                pixmap.setDevicePixelRatio(2.0)
            ImageView._rotate_cursor_cache = QCursor(pixmap, 16, 16)
        return ImageView._rotate_cursor_cache

    def mousePressEvent(self, event) -> None:
        # Linia podzialu ma pierwszenstwo przed przesuwaniem zdjecia dlonia -
        # inaczej chwycenie jej przesuwaloby caly widok.
        if event.button() == Qt.LeftButton and self._near_split(QPointF(event.position())):
            self._drag_kind = "split"
            event.accept()
            return
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

        if self._drag_kind == "split":
            width = self._image_size[0]
            if width:
                self.set_split_position(self.mapToScene(event.position().toPoint()).x() / width)
            return
        if self._drag_kind is None and not self._crop_mode:
            self._set_split_hover(self._near_split(position))

        if self._crop_mode and self._drag_kind is None:
            handle = self._handle_at(position)
            if handle:
                self.setCursor(self.CURSORS[handle])
            elif self._crop.contains(self.mapToScene(event.position().toPoint())):
                self.setCursor(Qt.SizeAllCursor)
            else:
                # poza kadrem przeciaganie obraca - kursor ma to powiedziec
                # jeszcze przed kliknieciem (punkt 24 planu)
                self.setCursor(self._rotate_cursor())

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
        if kind == "split":
            self._set_split_hover(self._near_split(QPointF(event.position())))
            return
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
        # Na ekranie os y idzie w dol, wiec rosnacy kat atan2 to ruch reki
        # zgodnie z zegarem; dodatni kat obrotu (konwencja cv2) obraca zdjecie
        # przeciwnie. Stad minus - obraz ma isc za reka.
        self._rotation = float(np.clip(self._rotation_at_press - delta, -45.0, 45.0))
        self.rotation_changed.emit(self._rotation)

    # --- rysowanie nakladki ----------------------------------------------

    def _draw_split(self, painter: QPainter) -> None:
        line = self._split_line()
        if line is None:
            return
        x, y0, y1 = line
        painter.save()
        # Linia, kolko i podpisy maja stala wielkosc na ekranie, wiec rysujemy
        # je w pikselach okna, a nie sceny.
        painter.resetTransform()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(0, 0, 0, 110), 3.0))
        painter.drawLine(QPointF(x, y0), QPointF(x, y1))
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
        painter.drawLine(QPointF(x, y0), QPointF(x, y1))

        # kolko z grotami w polowie widocznej czesci linii - mowi, ze linie
        # da sie chwycic, zanim kursor na nia trafi
        cy = (y0 + y1) / 2.0
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
        painter.setBrush(QColor(28, 28, 32, 210))
        painter.drawEllipse(QPointF(x, cy), pxf(SPLIT_KNOB_PX), pxf(SPLIT_KNOB_PX))
        painter.setBrush(Qt.NoBrush)
        for side in (-1.0, 1.0):
            tip, back = x + side * pxf(7.0), x + side * pxf(3.0)
            painter.drawPolyline([QPointF(back, cy - pxf(4.0)), QPointF(tip, cy), QPointF(back, cy + pxf(4.0))])

        # podpisy u gory, po obu stronach linii
        draw_badge(painter, t("Przed"), x - pxf(10.0), y0 + pxf(10.0), right_aligned=True)
        draw_badge(painter, t("Po"), x + pxf(10.0), y0 + pxf(10.0))
        painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        self._draw_split(painter)
        if self._after_badge and not self._crop_mode:
            painter.save()
            painter.resetTransform()
            draw_badge(painter, t("Po"), pxf(10.0), pxf(10.0))
            painter.restore()
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

        # stala grubosc linii na ekranie: piksel okna w jednostkach sceny
        pixel = self._gestosc() / max(self._zoom, 1e-6)

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
            size = pxf(10.0 if len(name) == 2 else 8.0) * pixel
            painter.drawRect(QRectF(point.x() - size / 2, point.y() - size / 2, size, size))

        painter.restore()


class BeforeView(QGraphicsView):
    """Widok "przed" w trybie porownania obok siebie.

    Nie ma wlasnego powiekszenia ani polozenia: przepisuje je z glownego
    widoku przy kazdej jego zmianie (`follow`), a kolko i przeciaganie
    przekazuje glownemu. Dzieki temu jedno zrodlo prawdy zostaje w ImageView,
    razem z nawigatorem, suwakiem powiekszenia i liczeniem ostrego fragmentu -
    oba widoki maja ten sam rozmiar, wiec pokazuja ten sam wycinek zdjecia.
    """

    def __init__(self, main: ImageView, parent=None):
        super().__init__(parent)
        self._main = main
        self._scene = QGraphicsScene(self)
        self._base = QGraphicsPixmapItem()
        self._base.setTransformationMode(Qt.SmoothTransformation)
        self._base.setCacheMode(QGraphicsPixmapItem.DeviceCoordinateCache)
        self._detail = QGraphicsPixmapItem()
        self._detail.setTransformationMode(Qt.SmoothTransformation)
        self._detail.setZValue(1)
        self._detail.hide()
        self._scene.addItem(self._base)
        self._scene.addItem(self._detail)
        self.setScene(self._scene)

        self.setRenderHints(QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor(18, 18, 20))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.viewport().setCursor(Qt.OpenHandCursor)
        self._drag_from: QPointF | None = None

        main.view_rect_changed.connect(lambda _rect: self.follow())

    # ----------------------------------------------------------- obrazy

    def set_before_image(self, rgb8: np.ndarray) -> None:
        width, height = self._main.image_size
        pixmap = numpy_to_pixmap(rgb8)
        self._base.setPixmap(pixmap)
        self._base.setScale(width / float(max(pixmap.width(), 1)))
        self._detail.hide()
        self._scene.setSceneRect(0.0, 0.0, float(width), float(height))
        self.follow()
        # ostry fragment liczy sie z widocznego wycinka glownego widoku
        self._main._schedule_detail()

    def set_before_detail(self, rgb8: np.ndarray, rect: QRect, scale: float) -> None:
        if self._base.pixmap().isNull():
            return
        self._detail.setPixmap(numpy_to_pixmap(rgb8))
        self._detail.setScale(1.0 / scale if scale else 1.0)
        self._detail.setPos(float(rect.x()), float(rect.y()))
        self._detail.show()

    def clear(self) -> None:
        self._base.setPixmap(QPixmap())
        self._detail.hide()

    def has_image(self) -> bool:
        return not self._base.pixmap().isNull()

    def detail_visible(self) -> bool:
        return self._detail.isVisible()

    # -------------------------------------------------- za glownym widokiem

    def follow(self) -> None:
        if not self.isVisible():
            return
        main = self._main
        width, height = main.image_size
        self._scene.setSceneRect(0.0, 0.0, float(width), float(height))
        self.setTransform(main.transform())
        self.centerOn(main.mapToScene(main.viewport().rect().center()))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.follow()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.follow()

    # ----------------------------------------------- przekazywanie gestow

    def wheelEvent(self, event: QWheelEvent) -> None:
        step = 1.0015 ** event.angleDelta().y()
        self._main.zoom_about(self._main.zoom * step, QPointF(event.position()))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_from = QPointF(event.position())
            self.viewport().setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_from is None:
            return
        position = QPointF(event.position())
        delta = position - self._drag_from
        self._drag_from = position
        self._main.pan_by(delta.x(), delta.y())

    def mouseReleaseEvent(self, event) -> None:
        self._drag_from = None
        self.viewport().setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        self._main.toggle_fit()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.resetTransform()
        draw_badge(painter, t("Przed"), pxf(10.0), pxf(10.0))
        painter.restore()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.viewport().update()  # podpis stoi w miejscu okna
