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
from datetime import date, datetime

from PySide6.QtCore import QDate, QLocale, QObject, QRectF, QSize, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QShortcut,
)
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.slad import wczytaj_gpx, wspolrzedne_z_tekstu
from .exif_panel import ExifPanel
from .map_page import strona
from .podpowiedzi import podpowiedz
from .markers import EDIT_ROLE, GEO_ROLE, LEGEND, MARK_COLUMN, paint_marks
from .slad_dialog import SladDialog
from .style import ikona
from ..przeklad import N_, jezyk, mnoga, t

# Wiersz naglowka dnia niesie tu date w ISO ("" = zdjecia bez daty).
# Zwykly wiersz zdjecia ma w tej roli None - po tym je odrozniamy.
DAY_ROLE = Qt.UserRole + 20
HEADER_HEIGHT = 26

# Nominatim prosi o najwyzej jedno zapytanie na sekunde. Nazwe miejsca
# pobieramy wiec dopiero, gdy zaznaczenie na chwile sie uspokoi - przewijanie
# listy strzalkami nie zasypuje serwera.
PLACE_DELAY_MS = 800

# Miniatura w liscie: na tyle duza, zeby rozpoznac kadr, na tyle mala, zeby
# przy dwustu zdjeciach dalo sie przewijac liste, a nie album.
THUMB_SIZE = QSize(96, 66)

# Filtry listy: klucz -> napis w menu lejka. Klucze ida tez do testow.
FILTR_WSZYSTKIE = "wszystkie"
FILTRY = (
    (FILTR_WSZYSTKIE, N_("Wszystkie zdjęcia")),
    ("z_lokalizacja", N_("Z lokalizacją")),
    ("bez_lokalizacji", N_("Bez lokalizacji")),
    ("nadana", N_("Z lokalizacją nadaną na mapie")),
    ("poprawione", N_("Z poprawkami")),
)


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
        if index.data(DAY_ROLE) is not None:
            return QSize(0, HEADER_HEIGHT)
        return QSize(0, THUMB_SIZE.height() + 8)

    def _paint_header(self, painter: QPainter, option, index) -> None:
        """Naglowek dnia: data i liczba zdjec, z kreska pod spodem."""
        rect = QRectF(option.rect).adjusted(self.PADDING, 0, -self.PADDING, 0)
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#c8c8ce"))
        painter.drawText(rect, int(Qt.AlignLeft | Qt.AlignVCenter), index.data(Qt.DisplayRole) or "")
        painter.setPen(QColor("#3a3a42"))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

    def paint(self, painter: QPainter, option, index) -> None:
        rect = option.rect
        painter.save()
        if index.data(DAY_ROLE) is not None:
            self._paint_header(painter, option, index)
            painter.restore()
            return
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
    place_named = Signal(float, float, str)  # odwrotne geokodowanie; "" = nie wyszlo
    page_ready = Signal(bool)  # czy mapa sie wczytala (biblioteka z sieci)

    @Slot(float, float, str)
    def placeNamed(self, latitude: float, longitude: float, name: str) -> None:  # noqa: N802
        self.place_named.emit(latitude, longitude, name)

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
    location_restored = Signal(list)  # zdjecia wracajace do wspolrzednych z aparatu
    undo_requested = Signal()
    redo_requested = Signal()
    # sciezka -> (szerokosc, dlugosc): kazde zdjecie wlasny punkt ze sladu GPX
    locations_matched = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.paths: list[str] = []
        # Czas wykonania zdjec (z aparatu, bez strefy) - do dni i do sladu.
        self.times: dict[str, datetime | None] = {}
        self.grupuj = True  # naglowki dni na liscie
        self.places: dict[tuple[float, float], str] = {}  # nazwy miejsc, po wspolrzednych
        self._place_timer = QTimer(self)
        self._place_timer.setSingleShot(True)
        self._place_timer.setInterval(PLACE_DELAY_MS)
        self._place_timer.timeout.connect(self._pokaz_miejsce)
        self.locations: dict[str, tuple[float, float]] = {}
        # Wspolrzedne z aparatu - odrozniaja "zdjecie ma GPS" od "my je
        # zmienilismy", czyli to, co umie cofnac przycisk przywracania.
        self.camera: dict[str, tuple[float, float]] = {}
        self.filtr = FILTR_WSZYSTKIE
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
        # Naglowki dni sa nizsze od wierszy zdjec - rowne wysokosci odpadaja.
        self.list.setUniformItemSizes(False)
        self.list.setItemDelegate(PhotoRowDelegate(self.list))
        self.list.setToolTip(t(LEGEND))
        self.list.itemSelectionChanged.connect(self._on_selection)
        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.itemDoubleClicked.connect(
            lambda item: None if self._naglowek(item)
            else self.photo_activated.emit(item.data(Qt.UserRole))
        )
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu_listy)
        # Skroty dzialaja tylko na liscie - w polu wyszukiwarki mapy Ctrl+C
        # i Ctrl+V maja kopiowac tekst, a nie wspolrzedne.
        QShortcut(QKeySequence.Copy, self.list, self.kopiuj_lokalizacje,
                  context=Qt.WidgetShortcut)
        QShortcut(QKeySequence.Paste, self.list, self.wklej_lokalizacje,
                  context=Qt.WidgetShortcut)

        self.tag_button = QPushButton(t("Przypisz zaznaczonym"))
        self.tag_button.setCheckable(True)
        podpowiedz(self.tag_button, "mapa.przypisz")
        self.tag_button.toggled.connect(self._on_tagging)

        self.clear_button = QPushButton(t("Usuń lokalizację"))
        podpowiedz(self.clear_button, "mapa.usun")
        self.clear_button.clicked.connect(self._on_clear)

        self.fit_button = QPushButton(t("Pokaż wszystkie"))
        podpowiedz(self.fit_button, "mapa.pokaz_wszystkie")
        self.fit_button.clicked.connect(lambda: self._js("fitToMarkers()"))

        self.track_button = QPushButton(t("Ślad GPX…"))
        podpowiedz(self.track_button, "mapa.slad")
        self.track_button.clicked.connect(self.wybierz_slad)

        self.undo_button = QPushButton(t("Cofnij"))
        self.undo_button.setIcon(ikona("undo"))
        podpowiedz(self.undo_button, "mapa.cofnij")
        self.undo_button.clicked.connect(self.undo_requested.emit)
        self.redo_button = QPushButton(t("Ponów"))
        self.redo_button.setIcon(ikona("redo"))
        podpowiedz(self.redo_button, "mapa.ponow")
        self.redo_button.clicked.connect(self.redo_requested.emit)
        self.set_history_state(False, False)

        self.restore_button = QPushButton(t("Przywróć lokalizację z aparatu"))
        self.restore_button.setIcon(ikona("geotag-reset"))
        podpowiedz(self.restore_button, "mapa.przywroc")
        self.restore_button.clicked.connect(self._on_restore)
        self.restore_button.setEnabled(False)

        # Male przyciski nad lista: szybkie zaznaczanie i lejek. Dzialaja na
        # tym, co widac - zaznaczanie ukrytych filtrem zdjec konczyloby sie
        # nadaniem lokalizacji zdjeciom, ktorych uzytkownik nie widzial.
        self.select_all_button = self._maly_przycisk("select-all", "mapa.zaznacz_wszystkie")
        self.select_all_button.clicked.connect(lambda: self._zaznacz(lambda p: True))
        self.select_located_button = self._maly_przycisk("geotag", "mapa.zaznacz_geotag")
        self.select_located_button.clicked.connect(
            lambda: self._zaznacz(lambda p: p in self.locations)
        )
        self.select_missing_button = self._maly_przycisk("no-geotag", "mapa.zaznacz_bez_geotagu")
        self.select_missing_button.clicked.connect(
            lambda: self._zaznacz(lambda p: p not in self.locations)
        )
        self.filter_button = self._maly_przycisk("filter", "mapa.filtr")
        self.filter_button.setCheckable(True)  # wcisniety = lista jest przefiltrowana
        self.filter_button.setPopupMode(QToolButton.InstantPopup)
        self.filter_menu = QMenu(self.filter_button)
        self.filter_actions = QActionGroup(self.filter_menu)
        for klucz, napis in FILTRY:
            action = QAction(t(napis), self.filter_menu)
            action.setCheckable(True)
            action.setChecked(klucz == self.filtr)
            action.setData(klucz)
            self.filter_actions.addAction(action)
            self.filter_menu.addAction(action)
            if klucz == FILTR_WSZYSTKIE:
                self.filter_menu.addSeparator()
        self.filter_actions.triggered.connect(lambda a: self.set_filter(a.data()))
        # Grupowanie to sposob pokazania listy, nie filtr - stad osobna
        # pozycja pod kreska, poza grupa wzajemnie wykluczajacych sie filtrow.
        self.filter_menu.addSeparator()
        self.group_action = QAction(t("Grupuj po dniach"), self.filter_menu)
        self.group_action.setCheckable(True)
        self.group_action.setChecked(self.grupuj)
        self.group_action.toggled.connect(self.set_grouping)
        self.filter_menu.addAction(self.group_action)
        self.filter_button.setMenu(self.filter_menu)
        # Klikniecie przycisku z menu potrafi przelaczyc jego wcisniecie,
        # nawet gdy nic nie wybrano - stan ma zalezec tylko od filtra.
        self.filter_menu.aboutToHide.connect(
            lambda: self.filter_button.setChecked(self.filtr != FILTR_WSZYSTKIE)
        )

        self.status = QLabel("")
        self.status.setObjectName("metaLabel")
        self.status.setWordWrap(True)
        # Nazwa miejsca osobno od stanu: stan przepisuje sie przy kazdym
        # kliknieciu, a nazwa przychodzi z sieci z opoznieniem.
        self.place_label = QLabel("")
        self.place_label.setObjectName("metaLabel")
        self.place_label.setWordWrap(True)
        self.place_label.hide()

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
        self.bridge.place_named.connect(self._on_place_named)
        # Baza "http://localhost/" jest potrzebna, zeby strona mogla siegac po
        # kafelki i Nominatim - dokument bez adresu nie ma prawa do sieci.
        self.web.setHtml(strona(), QUrl("http://localhost/"))

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(4)
        buttons.addWidget(self.tag_button)
        buttons.addWidget(self.clear_button)

        side = QVBoxLayout()
        side.setContentsMargins(8, 8, 4, 8)
        side.setSpacing(6)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)
        header.addWidget(QLabel(t("Zdjęcia")), 1)
        for button in (self.select_all_button, self.select_located_button,
                       self.select_missing_button):
            header.addWidget(button)
        header.addSpacing(6)
        header.addWidget(self.filter_button)

        history = QHBoxLayout()
        history.setContentsMargins(0, 0, 0, 0)
        history.setSpacing(4)
        history.addWidget(self.undo_button)
        history.addWidget(self.redo_button)

        side.addLayout(header)
        side.addWidget(self.list, 1)
        view_row = QHBoxLayout()
        view_row.setContentsMargins(0, 0, 0, 0)
        view_row.setSpacing(4)
        view_row.addWidget(self.fit_button)
        view_row.addWidget(self.track_button)

        side.addLayout(buttons)
        side.addLayout(view_row)
        side.addLayout(history)
        side.addWidget(self.restore_button)
        side.addWidget(self.status)
        side.addWidget(self.place_label)

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
                t("Mapa nie wczytała się — potrzebuje połączenia z internetem. "
                "Lista zdjęć i usuwanie lokalizacji działają bez niej.")
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
        camera: dict[str, tuple[float, float]] | None = None,
        times: dict[str, datetime | None] | None = None,
    ) -> None:
        """Podaje aktualna zawartosc katalogu, znane lokalizacje i miniatury."""
        self.paths = list(paths)
        self.locations = dict(locations)
        self.camera = dict(camera or {})
        self.edited = set(edited or ())
        self.icons = dict(icons or {})
        self.times = dict(times or {})
        self._zbuduj_liste()

        if self._ready:
            self._draw_markers()
        else:
            self._pending = True
        self._refresh_status()

    def _wiersz_zdjecia(self, path: str) -> QListWidgetItem:
        item = QListWidgetItem(os.path.basename(path))
        item.setData(Qt.UserRole, path)
        item.setToolTip(f"{os.path.basename(path)}\n\n{t(LEGEND)}")
        self._apply_marks(item, path)
        icon = self.icons.get(path)
        if icon is not None:
            item.setIcon(icon)
        return item

    def _wiersz_dnia(self, dzien: date | None, ile: int) -> QListWidgetItem:
        if dzien is None:
            napis = t("Bez daty wykonania")
        else:
            # Nazwy dni i miesiecy daje Qt w jezyku interfejsu - po polsku
            # w dopelniaczu ("12 wrzesnia"), czego strftime nie umie.
            napis = QLocale(jezyk()).toString(
                QDate(dzien.year, dzien.month, dzien.day), "dddd, d MMMM yyyy")
        item = QListWidgetItem(f"{napis}  ·  {ile}")
        item.setData(DAY_ROLE, dzien.isoformat() if dzien else "")
        # Naglowek nie daje sie zaznaczyc: inaczej trafialby do zaznaczenia
        # razem ze zdjeciami i mylil liczniki. Klikniecie obsluguje sam widok.
        item.setFlags(Qt.ItemIsEnabled)
        item.setToolTip(t("Kliknij, żeby zaznaczyć wszystkie zdjęcia z tego dnia."))
        return item

    def _zbuduj_liste(self) -> None:
        """Wiersze zdjec, przy grupowaniu poprzedzielane naglowkami dni.

        Dni ida po kolei w czasie, a wewnatrz dnia zostaje kolejnosc z paska
        miniatur. Zdjecia bez daty laduja na koncu pod wlasnym naglowkiem.
        """
        wybrane = set(self.selected_paths())
        self.list.blockSignals(True)
        self.list.clear()
        if self.grupuj and any(self.times.get(p) for p in self.paths):
            dni: dict[date | None, list[str]] = {}
            for path in self.paths:
                czas = self.times.get(path)
                dni.setdefault(czas.date() if czas else None, []).append(path)
            kolejnosc = sorted(d for d in dni if d is not None)
            if None in dni:
                kolejnosc.append(None)
            for dzien in kolejnosc:
                self.list.addItem(self._wiersz_dnia(dzien, len(dni[dzien])))
                for path in dni[dzien]:
                    self.list.addItem(self._wiersz_zdjecia(path))
        else:
            for path in self.paths:
                self.list.addItem(self._wiersz_zdjecia(path))
        for item in self.photo_items():
            item.setSelected(item.data(Qt.UserRole) in wybrane)
        self.list.blockSignals(False)
        self._zastosuj_filtr()

    def set_grouping(self, on: bool) -> None:
        if self.grupuj == on:
            return
        self.grupuj = on
        self.group_action.setChecked(on)
        self._zbuduj_liste()

    @staticmethod
    def _naglowek(item: QListWidgetItem) -> bool:
        return item.data(DAY_ROLE) is not None

    def photo_items(self) -> list[QListWidgetItem]:
        """Wiersze zdjec, bez naglowkow dni."""
        items = (self.list.item(row) for row in range(self.list.count()))
        return [item for item in items if not self._naglowek(item)]

    def _zdjecia_dnia(self, header: QListWidgetItem) -> list[QListWidgetItem]:
        """Widoczne wiersze zdjec pod danym naglowkiem, do nastepnego."""
        wynik = []
        for row in range(self.list.row(header) + 1, self.list.count()):
            item = self.list.item(row)
            if self._naglowek(item):
                break
            if not item.isHidden():
                wynik.append(item)
        return wynik

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Klikniecie w naglowek zaznacza caly dzien - potem jedno klikniecie
        w mape nadaje lokalizacje wszystkim zdjeciom z tego dnia."""
        if not self._naglowek(item):
            return
        dzien = {i.data(Qt.UserRole) for i in self._zdjecia_dnia(item)}
        self.list.blockSignals(True)
        for photo in self.photo_items():
            photo.setSelected(photo.data(Qt.UserRole) in dzien)
        self.list.blockSignals(False)
        self._on_selection()

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
        self._odswiez_przywracanie()

    def set_edited(self, path: str, edited: bool) -> None:
        """Znacznik poprawek dosłany z Edycji - lista ma pokazywac to samo."""
        if (path in self.edited) == edited:
            return
        self.edited.add(path) if edited else self.edited.discard(path)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == path:
                self._apply_marks(item, path)
                break
        if self.filtr == "poprawione":
            self._zastosuj_filtr()

    def set_thumbnail(self, path: str, icon) -> None:
        """Miniatura dosłana po otwarciu mapy - wpada na swoje miejsce."""
        self.icons[path] = icon
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == path:
                item.setIcon(icon)
                return

    def selected_paths(self) -> list[str]:
        # W kolejnosci listy, nie klikniec - przy grupowaniu to kolejnosc dni.
        return [item.data(Qt.UserRole) for item in self.photo_items() if item.isSelected()]

    def _highlight(self) -> None:
        self._js(f"highlight({json.dumps(self.selected_paths())})")

    # ------------------------------------------------------------ akcje

    def _on_selection(self) -> None:
        self._highlight()
        self._refresh_status()
        self._odswiez_przywracanie()
        chosen = self.selected_paths()
        # Jedno zaznaczone zdjecie z lokalizacja: przesun mape na nie, zeby
        # bylo widac, gdzie w ogole jest. Przy wielu tego nie robimy - skok
        # mapy przy kazdym klikniecu w liste byłby nie do zniesienia.
        if len(chosen) == 1 and chosen[0] in self.locations:
            latitude, longitude = self.locations[chosen[0]]
            self._js(f"panTo({latitude}, {longitude})")
        self._place_timer.start()

    def _on_tagging(self, on: bool) -> None:
        self._js(f"setTagging({'true' if on else 'false'})")
        self._refresh_status()

    def _on_map_click(self, latitude: float, longitude: float) -> None:
        chosen = self.selected_paths()
        if not chosen:
            self.status.setText(t("Najpierw zaznacz zdjęcia na liście."))
            return
        self.location_assigned.emit(chosen, latitude, longitude)

    def _on_clear(self) -> None:
        chosen = [p for p in self.selected_paths() if p in self.locations]
        if not chosen:
            self.status.setText(t("Zaznaczone zdjęcia nie mają lokalizacji."))
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
            + t("Kliknij mapę w trybie przypisywania, żeby nadać ten punkt.")
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
        self._zastosuj_filtr()
        self._draw_markers()
        self._refresh_status()
        self._odswiez_przywracanie()

    # ------------------------------------------ zaznaczanie, filtr, historia

    def _maly_przycisk(self, nazwa: str, tip: str) -> QToolButton:
        button = QToolButton()
        button.setIcon(ikona(nazwa))
        button.setIconSize(QSize(16, 16))
        button.setAutoRaise(True)
        podpowiedz(button, tip)
        return button

    def set_history_state(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_button.setEnabled(can_undo)
        self.redo_button.setEnabled(can_redo)

    def _zmieniona(self, path: str) -> bool:
        """Zdjecie ma GPS z aparatu, a lista pokazuje inne wspolrzedne - nasze."""
        return path in self.camera and self.locations.get(path) != self.camera[path]

    def _odswiez_przywracanie(self) -> None:
        self.restore_button.setEnabled(any(self._zmieniona(p) for p in self.selected_paths()))

    def _on_restore(self) -> None:
        chosen = [p for p in self.selected_paths() if self._zmieniona(p)]
        if chosen:
            self.location_restored.emit(chosen)

    def _pasuje(self, path: str) -> bool:
        if self.filtr == "z_lokalizacja":
            return path in self.locations
        if self.filtr == "bez_lokalizacji":
            return path not in self.locations
        if self.filtr == "nadana":
            return path in self.locations and self.locations.get(path) != self.camera.get(path)
        if self.filtr == "poprawione":
            return path in self.edited
        return True

    def set_filter(self, klucz: str) -> None:
        self.filtr = klucz
        for action in self.filter_actions.actions():
            action.setChecked(action.data() == klucz)
        self._zastosuj_filtr()

    def _zastosuj_filtr(self) -> None:
        """Chowa wiersze spoza filtra i zdejmuje z nich zaznaczenie.

        Ukryte, a nadal zaznaczone zdjecie dostaloby lokalizacje przy
        nastepnym kliknieciu w mape - bez sladu na liscie, ze w ogole bralo
        w tym udzial.
        """
        self.filter_button.setChecked(self.filtr != FILTR_WSZYSTKIE)
        self.list.blockSignals(True)
        header = None
        header_visible = False
        for row in range(self.list.count()):
            item = self.list.item(row)
            if self._naglowek(item):
                # Naglowek dnia chowa sie razem z ostatnim swoim zdjeciem -
                # pusty dzien na przefiltrowanej liscie tylko by przeszkadzal.
                if header is not None:
                    header.setHidden(not header_visible)
                header, header_visible = item, False
                continue
            hidden = not self._pasuje(item.data(Qt.UserRole))
            item.setHidden(hidden)
            header_visible = header_visible or not hidden
            if hidden and item.isSelected():
                item.setSelected(False)
        if header is not None:
            header.setHidden(not header_visible)
        self.list.blockSignals(False)
        self._on_selection()

    def visible_paths(self) -> list[str]:
        return [item.data(Qt.UserRole) for item in self.photo_items() if not item.isHidden()]

    def _zaznacz(self, warunek) -> None:
        self.list.blockSignals(True)
        for item in self.photo_items():
            item.setSelected(not item.isHidden() and warunek(item.data(Qt.UserRole)))
        self.list.blockSignals(False)
        self._on_selection()

    def _refresh_status(self) -> None:
        total = len(self.paths)
        with_location = sum(1 for path in self.paths if path in self.locations)
        chosen = len(self.selected_paths())
        parts = [t("Z lokalizacją: {z} z {n}", z=with_location, n=total)]
        if chosen:
            parts.append(t("zaznaczonych: {n}", n=chosen))
        if self.tag_button.isChecked() and chosen:
            parts.append(t("kliknij miejsce na mapie"))
        self.status.setText("  •  ".join(parts))

    # ------------------------------------------------- schowek, menu listy

    def _zrodlo_kopii(self) -> str | None:
        """Zdjecie, z ktorego kopiujemy: biezace, jesli ma lokalizacje,
        a inaczej pierwsze zaznaczone z lokalizacja."""
        current = self.list.currentItem()
        if (current is not None and not self._naglowek(current) and current.isSelected()
                and current.data(Qt.UserRole) in self.locations):
            return current.data(Qt.UserRole)
        return next((p for p in self.selected_paths() if p in self.locations), None)

    def kopiuj_lokalizacje(self) -> None:
        """Wspolrzedne do schowka systemowego jako zwykly tekst.

        Schowek systemowy, a nie wlasna pamiec: te same wspolrzedne da sie
        wkleic do przegladarki, a do nas - skopiowane z Google Maps.
        """
        path = self._zrodlo_kopii()
        if path is None:
            self.status.setText(t("Zaznaczone zdjęcie nie ma lokalizacji do skopiowania."))
            return
        latitude, longitude = self.locations[path]
        QGuiApplication.clipboard().setText(f"{latitude:.6f}, {longitude:.6f}")
        self.status.setText(t("Skopiowano lokalizację {wsp} ze zdjęcia {plik}",
                              wsp=f"{latitude:.5f}, {longitude:.5f}",
                              plik=os.path.basename(path)))

    def wklej_lokalizacje(self) -> None:
        """Wspolrzedne ze schowka dla wszystkich zaznaczonych zdjec."""
        miejsce = wspolrzedne_z_tekstu(QGuiApplication.clipboard().text())
        if miejsce is None:
            self.status.setText(t("W schowku nie ma współrzędnych."))
            return
        chosen = self.selected_paths()
        if not chosen:
            self.status.setText(t("Najpierw zaznacz zdjęcia na liście."))
            return
        self.location_assigned.emit(chosen, miejsce[0], miejsce[1])

    def _menu_listy(self, pos) -> None:
        menu = QMenu(self.list)
        kopiuj = menu.addAction(t("Kopiuj lokalizację"), self.kopiuj_lokalizacje)
        kopiuj.setShortcut(QKeySequence.Copy)
        kopiuj.setEnabled(self._zrodlo_kopii() is not None)
        wklej = menu.addAction(t("Wklej lokalizację"), self.wklej_lokalizacje)
        wklej.setShortcut(QKeySequence.Paste)
        wklej.setEnabled(bool(self.selected_paths()) and wspolrzedne_z_tekstu(
            QGuiApplication.clipboard().text()) is not None)
        menu.addSeparator()
        usun = menu.addAction(t("Usuń lokalizację"), self._on_clear)
        usun.setEnabled(any(p in self.locations for p in self.selected_paths()))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------ slad GPX

    def wybierz_slad(self) -> None:
        folder = os.path.dirname(self.paths[0]) if self.paths else ""
        plik, _ = QFileDialog.getOpenFileName(
            self, t("Wybierz ślad GPX"), folder, t("Ślad GPS (*.gpx)"))
        if plik:
            self.dopasuj_slad(plik)

    def dopasuj_slad(self, plik: str, dialog_hook=None) -> None:
        """Wczytuje slad, rysuje go na mapie i pyta o przesuniecie czasu.

        Bierze zaznaczone zdjecia, a bez zaznaczenia - wszystkie widoczne na
        liscie. `dialog_hook` dostaje okno zamiast `exec()` (testy).
        """
        try:
            slad = wczytaj_gpx(plik)
        except (OSError, SyntaxError, ValueError) as exc:  # ParseError to SyntaxError
            QMessageBox.warning(self, "Punctum", t("Nie udało się wczytać śladu:\n{blad}", blad=exc))
            return
        if not len(slad):
            QMessageBox.information(
                self, "Punctum",
                t("W pliku nie ma punktów z czasem — nie da się do nich dopasować zdjęć."))
            return
        self._js(f"showTrack({json.dumps(slad.do_mapy())})")
        chosen = self.selected_paths()
        photos = chosen or self.visible_paths()
        dialog = SladDialog(slad, plik, {p: self.times.get(p) for p in photos},
                            set(self.locations), bool(chosen), self)
        accepted = dialog_hook(dialog) if dialog_hook else dialog.exec() == QDialog.Accepted
        if accepted and dialog.wynik:
            self.locations_matched.emit(dict(dialog.wynik))

    # ------------------------------------------------------- nazwa miejsca

    @staticmethod
    def _klucz_miejsca(latitude: float, longitude: float) -> tuple[float, float]:
        # Cztery miejsca po przecinku to ok. 10 m - zdjecia z jednego
        # spaceru po rynku dziela jedna nazwe i jedno zapytanie.
        return round(latitude, 4), round(longitude, 4)

    def _pokaz_miejsce(self) -> None:
        """Nazwa miejsca dla jednego zaznaczonego zdjecia z lokalizacja."""
        chosen = self.selected_paths()
        if len(chosen) != 1 or chosen[0] not in self.locations:
            self.place_label.hide()
            return
        klucz = self._klucz_miejsca(*self.locations[chosen[0]])
        if klucz in self.places:
            self.place_label.setText(t("Miejsce: {nazwa}", nazwa=self.places[klucz]))
            self.place_label.show()
            return
        if not self._ready:
            self.place_label.hide()
            return
        self.place_label.setText(t("Szukanie nazwy miejsca…"))
        self.place_label.show()
        self._js(f"reverseGeocode({klucz[0]}, {klucz[1]}, {json.dumps(jezyk())})")

    def _on_place_named(self, latitude: float, longitude: float, name: str) -> None:
        klucz = self._klucz_miejsca(latitude, longitude)
        if name:
            self.places[klucz] = name  # porazki nie pamietamy - siec moze wrocic
        chosen = self.selected_paths()
        if (len(chosen) == 1 and chosen[0] in self.locations
                and self._klucz_miejsca(*self.locations[chosen[0]]) == klucz):
            if name:
                self.place_label.setText(t("Miejsce: {nazwa}", nazwa=name))
                self.place_label.show()
            else:
                self.place_label.hide()
