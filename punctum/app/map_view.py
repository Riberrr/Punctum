"""Zakladka "Mapa": lista zdjec obok mapy, przypisywanie wspolrzednych.

Zakladki siedza na samej gorze okna, wiec w widoku mapy nie widac paska
miniatur - lista zdjec musi tu byc wlasna. Nie jest to jednak kopia paska:
tam liczy sie podglad kadru, tutaj to, ktore zdjecia maja juz lokalizacje
i ktore sa wybrane do nadania nowej.

Wspolrzedne nie ida do pliku ze zdjeciem. Ladują w sidecarze, tak jak korekty,
a do metadanych trafiaja dopiero w pliku wynikowym przy eksporcie.
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, QRectF, QSize, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from .exif_panel import ExifPanel
from .map_page import MAP_HTML
from .markers import EDIT_ROLE, GEO_ROLE, LEGEND, MARK_COLUMN, paint_marks

# Miniatura w liscie: na tyle duza, zeby rozpoznac kadr, na tyle mala, zeby
# przy dwustu zdjeciach dalo sie przewijac liste, a nie album.
THUMB_SIZE = QSize(96, 66)


class PhotoRowDelegate(QStyledItemDelegate):
    """Wiersz listy: znaczniki, nazwa przy lewej krawedzi, miniatura z prawej.

    Zwykla pozycja QListWidget stawia ikone przed tekstem, a miniatury maja
    rozne proporcje - kazda nazwa zaczynala sie wiec w innym miejscu i lista
    byla nie do przeczytania. Tutaj nazwa ma stala kolumne, a obrazki rowna
    prawa krawedz.
    """

    PADDING = 8
    GAP = 8

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, THUMB_SIZE.height() + 8)

    def paint(self, painter: QPainter, option, index) -> None:
        rect = option.rect
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#34343c"))
            painter.drawRoundedRect(QRectF(rect).adjusted(2, 1, -2, -1), 4, 4)

        right = rect.right() - self.PADDING
        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            pixmap = icon.pixmap(THUMB_SIZE)
            ratio = pixmap.devicePixelRatio() or 1.0
            width, height = pixmap.width() / ratio, pixmap.height() / ratio
            target = QRectF(
                right - width, rect.center().y() - height / 2.0, width, height
            )
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
            right -= width + self.GAP

        marks = QRectF(rect.left() + self.PADDING, rect.top(), MARK_COLUMN, rect.height())
        paint_marks(painter, marks, bool(index.data(EDIT_ROLE)), bool(index.data(GEO_ROLE)))

        text_left = marks.right()
        painter.setPen(
            QColor("#ffffff") if option.state & QStyle.State_Selected else QColor("#a2a2aa")
        )
        painter.setFont(option.font)
        metrics = QFontMetrics(option.font)
        text = metrics.elidedText(
            index.data(Qt.DisplayRole) or "", Qt.ElideMiddle, int(right - text_left)
        )
        painter.drawText(
            QRectF(text_left, rect.top(), right - text_left, rect.height()),
            int(Qt.AlignLeft | Qt.AlignVCenter),
            text,
        )
        painter.restore()


class MapBridge(QObject):
    """Wolane z JavaScriptu. Kazda metoda zamienia zdarzenie na sygnal Qt."""

    map_clicked = Signal(float, float)
    marker_clicked = Signal(str)
    place_found = Signal(float, float, str)
    page_ready = Signal(bool)  # czy mapa sie wczytala (biblioteka z sieci)

    @Slot(bool)
    def ready(self, has_map: bool) -> None:
        self.page_ready.emit(has_map)

    @Slot(float, float)
    def mapClicked(self, latitude: float, longitude: float) -> None:  # noqa: N802
        self.map_clicked.emit(latitude, longitude)

    @Slot(str)
    def markerClicked(self, path: str) -> None:  # noqa: N802
        self.marker_clicked.emit(path)

    @Slot(float, float, str)
    def placeFound(self, latitude: float, longitude: float, name: str) -> None:  # noqa: N802
        self.place_found.emit(latitude, longitude, name)


class MapView(QWidget):
    """Lista zdjec plus mapa. Zwraca na zewnatrz gotowe decyzje uzytkownika."""

    # sciezki zdjec, szerokosc, dlugosc  (None, None = skasowanie lokalizacji)
    location_assigned = Signal(list, object, object)
    photo_activated = Signal(str)  # dwuklik na liscie - przejscie do edycji

    def __init__(self, parent=None):
        super().__init__(parent)
        self.locations: dict[str, tuple[float, float]] = {}
        self.edited: set[str] = set()  # zdjecia z zapisanymi poprawkami
        self.icons: dict = {}  # miniatury, po sciezkach
        self.has_map = False  # czy biblioteka mapy wczytala sie z sieci
        self.answered = False  # czy strona w ogole sie odezwala (do testow)
        self._ready = False
        self._pending = False  # strona jeszcze sie laduje, pinezki czekaja

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setFixedWidth(300)
        # Miniatury biora sie z paska zdjec - te same obrazki sa juz
        # zdekodowane, wiec lista nic nie dolicza.
        self.list.setIconSize(THUMB_SIZE)
        self.list.setSpacing(1)
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(PhotoRowDelegate(self.list))
        self.list.setToolTip(LEGEND)
        self.list.itemSelectionChanged.connect(self._on_selection)
        self.list.itemDoubleClicked.connect(
            lambda item: self.photo_activated.emit(item.data(Qt.UserRole))
        )

        self.tag_button = QPushButton("Przypisz zaznaczonym")
        self.tag_button.setCheckable(True)
        self.tag_button.setToolTip(
            "Włącz, zaznacz zdjęcia na liście i kliknij miejsce na mapie.\n"
            "Wszystkie zaznaczone dostaną te współrzędne."
        )
        self.tag_button.toggled.connect(self._on_tagging)

        self.clear_button = QPushButton("Usuń lokalizację")
        self.clear_button.setToolTip("Zdejmuje współrzędne z zaznaczonych zdjęć")
        self.clear_button.clicked.connect(self._on_clear)

        self.fit_button = QPushButton("Pokaż wszystkie")
        self.fit_button.setToolTip("Dopasuj mapę tak, żeby było widać wszystkie pinezki")
        self.fit_button.clicked.connect(lambda: self._js("fitToMarkers()"))

        self.status = QLabel("")
        self.status.setObjectName("metaLabel")
        self.status.setWordWrap(True)

        self.web = QWebEngineView()
        # Strona zaczyna zycie biala, a okno jest ciemne - bez tego wejscie
        # na zakladke blyska bielą, zanim doleci pierwszy kafelek.
        self.web.page().setBackgroundColor(QColor("#1e1e20"))
        self.bridge = MapBridge()
        channel = QWebChannel(self.web.page())
        channel.registerObject("bridge", self.bridge)
        self.web.page().setWebChannel(channel)
        self.bridge.page_ready.connect(self._on_page_ready)
        self.bridge.map_clicked.connect(self._on_map_click)
        self.bridge.marker_clicked.connect(self._on_marker_click)
        self.bridge.place_found.connect(self._on_place_found)
        # Baza "http://localhost/" jest potrzebna, zeby strona mogla siegac po
        # kafelki i Nominatim - dokument bez adresu nie ma prawa do sieci.
        self.web.setHtml(MAP_HTML, QUrl("http://localhost/"))

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(4)
        buttons.addWidget(self.tag_button)
        buttons.addWidget(self.clear_button)

        side = QVBoxLayout()
        side.setContentsMargins(8, 8, 4, 8)
        side.setSpacing(6)
        side.addWidget(QLabel("Zdjęcia"))
        side.addWidget(self.list, 1)
        side.addLayout(buttons)
        side.addWidget(self.fit_button)
        side.addWidget(self.status)

        # Panel metadanych po prawej. W tej zakladce jest na niego miejsce,
        # wiec stoi otwarty - inaczej niz w Edycji, gdzie rozwija sie
        # z sekcji z danymi zdjecia.
        #
        # Panel siedzi we wlasnej ramce z marginesem: bez niego pola dotykaly
        # krawedzi okna i kolumna zlewala sie z mapa.
        self.exif_panel = ExifPanel()
        self.panel_host = QWidget()
        self.panel_host.setObjectName("sidePanel")
        self.panel_host.setAttribute(Qt.WA_StyledBackground, True)
        self.panel_host.setFixedWidth(348)
        host_layout = QVBoxLayout(self.panel_host)
        host_layout.setContentsMargins(10, 10, 10, 10)
        host_layout.setSpacing(0)
        host_layout.addWidget(self.exif_panel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(side)
        layout.addWidget(self.web, 1)
        layout.addWidget(self.panel_host)

    # ------------------------------------------------------------- strona

    def _js(self, code: str) -> None:
        if self._ready:
            self.web.page().runJavaScript(code)

    def _on_page_ready(self, has_map: bool) -> None:
        self.answered = True
        self.has_map = has_map
        self._ready = has_map
        if not has_map:
            self.tag_button.setEnabled(False)
            self.status.setText(
                "Mapa nie wczytała się — potrzebuje połączenia z internetem. "
                "Lista zdjęć i usuwanie lokalizacji działają bez niej."
            )
            return
        if self._pending:
            self._draw_markers()
            self._pending = False

    # -------------------------------------------------------------- dane

    def set_photos(
        self,
        paths: list[str],
        locations: dict[str, tuple[float, float]],
        icons: dict | None = None,
        edited: set[str] | None = None,
    ) -> None:
        """Podaje aktualna zawartosc katalogu, znane lokalizacje i miniatury."""
        self.locations = dict(locations)
        self.edited = set(edited or ())
        self.icons = dict(icons or {})
        self.list.blockSignals(True)
        self.list.clear()
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(f"{os.path.basename(path)}\n\n{LEGEND}")
            self._apply_marks(item, path)
            icon = self.icons.get(path)
            if icon is not None:
                item.setIcon(icon)
            self.list.addItem(item)
        self.list.blockSignals(False)

        if self._ready:
            self._draw_markers()
        else:
            self._pending = True
        self._refresh_status()

    def _apply_marks(self, item: QListWidgetItem, path: str) -> None:
        """Stan zdjecia zapisany w pozycji - rysuje go delegat."""
        item.setData(EDIT_ROLE, path in self.edited)
        item.setData(GEO_ROLE, path in self.locations)

    def _draw_markers(self) -> None:
        self._js("clearMarkers()")
        for path, (latitude, longitude) in self.locations.items():
            name = json.dumps(os.path.basename(path))  # cudzyslowy i ogonki
            self._js(f"addMarker({json.dumps(path)}, {latitude}, {longitude}, {name})")
        self._js("fitToMarkers()")
        self._highlight()

    def set_selection(self, paths: list[str]) -> None:
        """Przenosi zaznaczenie z paska miniatur do listy w widoku mapy."""
        wanted = set(paths)
        self.list.blockSignals(True)
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setSelected(item.data(Qt.UserRole) in wanted)
        self.list.blockSignals(False)
        self._highlight()
        self._refresh_status()

    def set_edited(self, path: str, edited: bool) -> None:
        """Znacznik poprawek dosłany z Edycji - lista ma pokazywac to samo."""
        if (path in self.edited) == edited:
            return
        self.edited.add(path) if edited else self.edited.discard(path)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == path:
                self._apply_marks(item, path)
                return

    def set_thumbnail(self, path: str, icon) -> None:
        """Miniatura dosłana po otwarciu mapy - wpada na swoje miejsce."""
        self.icons[path] = icon
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == path:
                item.setIcon(icon)
                return

    def selected_paths(self) -> list[str]:
        return [item.data(Qt.UserRole) for item in self.list.selectedItems()]

    def _highlight(self) -> None:
        self._js(f"highlight({json.dumps(self.selected_paths())})")

    # ------------------------------------------------------------ akcje

    def _on_selection(self) -> None:
        self._highlight()
        self._refresh_status()
        chosen = self.selected_paths()
        # Jedno zaznaczone zdjecie z lokalizacja: przesun mape na nie, zeby
        # bylo widac, gdzie w ogole jest. Przy wielu tego nie robimy - skok
        # mapy przy kazdym klikniecu w liste byłby nie do zniesienia.
        if len(chosen) == 1 and chosen[0] in self.locations:
            latitude, longitude = self.locations[chosen[0]]
            self._js(f"panTo({latitude}, {longitude})")

    def _on_tagging(self, on: bool) -> None:
        self._js(f"setTagging({'true' if on else 'false'})")
        self._refresh_status()

    def _on_map_click(self, latitude: float, longitude: float) -> None:
        chosen = self.selected_paths()
        if not chosen:
            self.status.setText("Najpierw zaznacz zdjęcia na liście.")
            return
        self.location_assigned.emit(chosen, latitude, longitude)

    def _on_clear(self) -> None:
        chosen = [p for p in self.selected_paths() if p in self.locations]
        if not chosen:
            self.status.setText("Zaznaczone zdjęcia nie mają lokalizacji.")
            return
        self.location_assigned.emit(chosen, None, None)

    def _on_marker_click(self, path: str) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == path:
                self.list.setCurrentItem(item)
                self.list.scrollToItem(item)
                return

    def _on_place_found(self, latitude: float, longitude: float, name: str) -> None:
        self.status.setText(
            f"{name}: {latitude:.5f}, {longitude:.5f}\n"
            "Kliknij mapę w trybie przypisywania, żeby nadać ten punkt."
        )

    def apply_locations(self, changed: dict[str, tuple[float, float] | None]) -> None:
        """Przyjmuje zmiany z okna glownego i odswieza liste oraz pinezki."""
        for path, location in changed.items():
            if location is None:
                self.locations.pop(path, None)
            else:
                self.locations[path] = location
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) in changed:
                self._apply_marks(item, item.data(Qt.UserRole))
        self._draw_markers()
        self._refresh_status()

    def _refresh_status(self) -> None:
        total = self.list.count()
        with_location = sum(
            1 for row in range(total)
            if self.list.item(row).data(Qt.UserRole) in self.locations
        )
        chosen = len(self.selected_paths())
        parts = [f"Z lokalizacją: {with_location} z {total}"]
        if chosen:
            parts.append(f"zaznaczonych: {chosen}")
        if self.tag_button.isChecked() and chosen:
            parts.append("kliknij miejsce na mapie")
        self.status.setText("  •  ".join(parts))
