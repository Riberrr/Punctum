"""Glowne okno aplikacji."""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QRect, QRectF, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import (
    FORMAT_ALL,
    FORMAT_JPEG,
    FORMAT_LABELS,
    FORMAT_RAW,
    EditParams,
    RawImage,
    count_formats,
    default_params_for,
    is_jpeg,
    develop,
    edited_photos,
    folder_photos,
    geometry_size,
    histogram,
    matches_filter,
    read_sidecar,
    write_sidecar,
)
from ..core.export import (
    ON_EXISTING_ASK,
    ON_EXISTING_OVERWRITE,
    ON_EXISTING_SKIP,
    ON_EXISTING_UNIQUE,
    ExportOptions,
    plan_export,
    resolve_conflicts,
)
from ..core.hardware import system_info
from ..core.metadata import PhotoMetadata
from ..core.settings import ENGINE_CPU, ENGINE_GPU, LAYOUT_LIMITS, Settings
from .edit_panel import EditPanel, HistogramWidget, InfoPanel
from .exif_panel import ExifPanel
from .export_dialog import ExportDialog
from .filmstrip import Filmstrip
from .gpu_renderer import GpuRenderer
from .image_view import ImageView
from .map_view import MapView
from .navigator import Navigator
from .podpowiedzi import StylPodpowiedzi, WylacznikPodpowiedzi, podpowiedz
# "O programie" nie ma osobnego okna - to strona w ustawieniach.
from .settings_dialog import PAGE_ABOUT, SettingsDialog
from .style import stylesheet
from .workers import (
    AutoToneTask,
    DetailRenderTask,
    ExportTask,
    LoadRawTask,
    NoiseReductionTask,
    RenderTask,
    ThumbnailTask,
)
from .zoom_panel import ZoomPanel
from ..przeklad import mnoga, t

# Reszta parametrow mieszka w `core/settings.py` i jest edytowalna przez
# uzytkownika; te dwa zaleza od wybranego toru liczenia, nie od preferencji.
DEBOUNCE_CPU_MS = 90  # tor numpy: nie liczymy obrazu na kazdy piksel ruchu suwaka
DEBOUNCE_GPU_MS = 0  # tor GPU: tylko scalenie zdarzen z jednego obiegu petli
FULL_CROP = (0.0, 0.0, 1.0, 1.0)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Punctum")
        self.resize(1560, 980)
        # Nakladka na styl daje opoznienie dymkow z ustawien. Zakladana przed
        # arkuszem stylow i raz na aplikacje (testy tworza kilka okien).
        app = QApplication.instance()
        if not isinstance(app.style(), StylPodpowiedzi):
            app.setStyle(StylPodpowiedzi(app.style().name()))
        self.tooltip_style = app.style()
        self.setStyleSheet(stylesheet())

        self.settings = Settings.load()
        self.pool = QThreadPool.globalInstance()
        self.thumb_pool = QThreadPool()

        # Wszystkie zdjecia w otwartym katalogu i te, ktore przepuszcza filtr
        # formatow. Filtr przepisuje tylko `paths`, wiec przelaczenie go nie
        # wymaga ponownego czytania katalogu.
        self.folder_paths: list[str] = []
        self.paths: list[str] = []
        self.metadata: dict[str, PhotoMetadata] = {}
        # Nastawy edycji per zdjecie. Bez tego powrot do wczesniej poprawionego
        # zdjecia gubilby prace, a eksport wsadowy nakladalby na wszystkie
        # pliki ustawienia tego jednego, ktore akurat jest otwarte.
        self.edits: dict[str, EditParams] = {}
        # Zdjecia, ktore mialy zapisana prace juz przy wejsciu do katalogu.
        self.edited_on_disk: set[str] = set()
        self._sidecar_warned = False
        self.export_task: ExportTask | None = None
        self._skipped_in_export = 0
        self.current_path: str | None = None
        self.full_raw: RawImage | None = None
        self.proxy: RawImage | None = None
        self.before_image: np.ndarray | None = None
        self.current_image: np.ndarray | None = None

        self.orientation = 0
        self.crop = FULL_CROP
        self.crop_mode = False

        self._job_counter = 0
        self._latest_job = 0
        self._latest_detail = 0
        # przytrzymany "Przed / po": podglad pokazuje zdjecie bez korekt i nic,
        # co przyjdzie w tym czasie z watkow, nie moze go podmienic
        self._before_shown = False
        self._noise_pending = None  # (obraz bez odszumiania, parametry)

        # Tor tonalny na karcie graficznej. Bez niego podglad liczy numpy,
        # co przy 20 megapikselach zajmuje okolo 0,7 s na kazdy ruch suwaka.
        # Kontekst tworzymy nawet przy wymuszonym procesorze - to z niego
        # pochodza dane karty pokazywane w ustawieniach.
        self.gpu = GpuRenderer()
        self.gpu_source_ready = False
        self.system = system_info(self.gpu.describe())

        self._build_ui()
        self._build_menu()

        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self._render_preview)

        # osobny zegar na odszumianie - liczone na procesorze, wiec czeka,
        # az uzytkownik przestanie ruszac suwakiem
        self.noise_timer = QTimer(self)
        self.noise_timer.setSingleShot(True)
        self.noise_timer.timeout.connect(self._render_noise_pass)

        # Wylacznik dymkow jest filtrem na calej aplikacji: dziala od razu
        # po zmianie ustawienia, bez odtwarzania podpowiedzi w oknach.
        self.tooltip_switch = WylacznikPodpowiedzi(self)
        QApplication.instance().installEventFilter(self.tooltip_switch)
        self._apply_settings()

        # Mapa powstaje TERAZ, zanim okno zostanie pokazane - i jest to
        # decyzja o migotaniu, nie o wydajnosci.
        #
        # QWebEngineView potrzebuje okna natywnego zdolnego do kompozycji
        # OpenGL. Gdy pojawia sie w oknie, ktore juz stoi na ekranie, Qt
        # przebudowuje cale okno najwyzszego poziomu - z zewnatrz wyglada to
        # tak, jakby program na ulamek sekundy znikal i wracal. Zmierzone
        # w tools/diag_zakladki.py: przy leniwej budowie uchwyt okna zmienia
        # sie przy pierwszym wejsciu na zakladke (3477674 -> 3543210), przy
        # budowie przed pokazaniem okna zostaje ten sam.
        #
        # Kosztuje to okolo 260 ms startu (2080 -> 2340 ms), ale dzieje sie
        # zanim uzytkownik cokolwiek zobaczy. Maly widzet OpenGL zamiast mapy
        # nie wystarcza - sprawdzone, okno i tak sie przebudowuje.
        self._ensure_map()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.view = ImageView()
        self.view.zoom_changed.connect(
            lambda z: self.zoom_panel.set_zoom(z, self.view.fit_zoom())
        )
        self.view.view_rect_changed.connect(self._on_view_rect)
        self.view.detail_needed.connect(self._render_detail)
        self.view.crop_changed.connect(self._on_crop_changed)
        self.view.rotation_changed.connect(self._on_rotation_dragged)

        self.navigator = Navigator()
        self.navigator.centre_requested.connect(self.view.centre_on_normalised)
        self.histogram_widget = HistogramWidget()
        self.info_panel = InfoPanel()

        self.edit_panel = EditPanel()
        self.edit_panel.params_changed.connect(self._on_params_changed)
        self.edit_panel.reset_requested.connect(self._on_reset_all)
        self.edit_panel.auto_requested.connect(self._run_auto)
        self.edit_panel.crop_mode_toggled.connect(self._set_crop_mode)
        self.edit_panel.orientation_step.connect(self._rotate_orientation)
        self.edit_panel.crop_reset_requested.connect(self._reset_crop)

        # Metadane sa chowanym dnem sekcji z danymi zdjecia: rozwija je
        # strzalka w rogu tej sekcji, a nie osobny przycisk na calą szerokosc.
        # Dzieki temu panel nie "wyskakuje" - sekcja po prostu rosnie w dol.
        self.exif_panel = ExifPanel()
        self.exif_panel.changed.connect(self._on_metadata_changed)
        self.exif_panel.write_requested.connect(self._write_metadata_to_originals)
        self.exif_panel.setMinimumHeight(240)
        self.info_panel.set_details(self.exif_panel)

        self.zoom_panel = ZoomPanel(ImageView.MAX_ZOOM)
        self.zoom_panel.zoom_requested.connect(self.view.zoom_centred)
        self.zoom_panel.fit_requested.connect(self.view.fit_to_window)
        self.zoom_panel.actual_requested.connect(self.view.zoom_actual)
        self.detail_label = self.zoom_panel.detail_label

        self.before_button = QPushButton(t("Przed / po"))
        podpowiedz(self.before_button, "podglad.przed_po")
        self.before_button.pressed.connect(self._show_before)
        self.before_button.released.connect(self._show_after)
        # Wiersz, nie sam przycisk: obok stanie przelacznik podzielonego
        # podgladu przed/po (punkt 19 planu).
        compare_row = QHBoxLayout()
        compare_row.setContentsMargins(0, 0, 0, 0)
        compare_row.addWidget(self.before_button, 1)
        compare_row.addStretch(1)

        # Lewy panel: gdzie jestem w zdjeciu i co to za zdjecie. Przewija sie
        # w nim tylko rozwiniety EXIF (ma wlasne przewijanie), dlatego sekcja
        # danych dostaje rozciaganie dopiero po rozwinieciu - zwinieta nie
        # moze rozdmuchac ramki na pol okna.
        left = QWidget()
        left.setObjectName("leftPanel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.navigator)
        left_layout.addWidget(self.zoom_panel)
        left_layout.addLayout(compare_row)
        left_layout.addWidget(self.info_panel)
        left_layout.addStretch(1)
        info_index = left_layout.indexOf(self.info_panel)

        def give_space_to_details(on: bool) -> None:
            left_layout.setStretch(info_index, 1 if on else 0)
            left_layout.setStretch(info_index + 1, 0 if on else 1)

        self.info_panel.details_toggled.connect(give_space_to_details)
        self.left_panel = left

        right = QWidget()
        right.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 10, 10, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.histogram_widget)
        right_layout.addWidget(self.edit_panel, 1)
        self.right_panel = right

        # Szerokosci ustawia uzytkownik, ale tylko w granicach. Jawne minimum
        # ma pierwszenstwo przed tym, o co prosi zawartosc - bez tego
        # rozwiniecie metadanych poszerzalo kolumne i przesuwalo podglad.
        for panel, key in ((left, "left_panel_width"), (right, "right_panel_width")):
            low, high = LAYOUT_LIMITS[key]
            panel.setMinimumWidth(low)
            panel.setMaximumWidth(high)

        # Przycisk eksportu stoi w rogu belki zakladek: gorny pasek narzedzi
        # zajmowal caly wiersz na kilka przyciskow, ktore teraz maja swoje
        # miejsca w panelach.
        self.export_button = QPushButton(t("Eksportuj…"))
        podpowiedz(self.export_button, "okno.eksportuj")
        self.export_button.clicked.connect(self.export_current)

        self.filmstrip = Filmstrip()
        self.filmstrip.photo_selected.connect(self.open_photo)
        self.filmstrip.thumbnail_ready.connect(self._on_thumbnail_icon)
        low, high = LAYOUT_LIMITS["filmstrip_height"]
        self.filmstrip.setMinimumHeight(low)
        self.filmstrip.setMaximumHeight(high)

        # Pasek nad miniaturami. Katalogu, w ktorym lezy kilkanascie tysiecy
        # JPEG-ow i garsc RAW-ow, nie da sie przejrzec bez takiego filtra.
        self.format_combo = QComboBox()
        podpowiedz(self.format_combo, "okno.filtr")
        for key in (FORMAT_ALL, FORMAT_RAW, FORMAT_JPEG):
            self.format_combo.addItem(t(FORMAT_LABELS[key]), key)
        index = self.format_combo.findData(self.settings.format_filter)
        self.format_combo.setCurrentIndex(max(0, index))
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        self.format_count = QLabel("")
        self.format_count.setObjectName("metaLabel")

        strip_header = QWidget()
        header_layout = QHBoxLayout(strip_header)
        header_layout.setContentsMargins(8, 3, 8, 3)
        header_layout.setSpacing(8)
        header_layout.addWidget(QLabel(t("Pokaż:")))
        header_layout.addWidget(self.format_combo)
        header_layout.addWidget(self.format_count)
        header_layout.addStretch(1)
        # Stala wysokosc naglowka: bez niej granica wysokosci paska dotyczylaby
        # tylko miniatur, a wolne miejsce z przeciagania przejmowalby naglowek.
        strip_header.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        strip = QWidget()
        strip_layout = QVBoxLayout(strip)
        strip_layout.setContentsMargins(0, 0, 0, 0)
        strip_layout.setSpacing(0)
        strip_layout.addWidget(strip_header)
        strip_layout.addWidget(self.filmstrip, 1)

        # Wolne miejsce przy zmianie rozmiaru okna idzie do podgladu (stretch),
        # panele trzymaja szerokosc ustawiona przez uzytkownika.
        # Zapamietane rozmiary nakladamy dopiero po pokazaniu okna
        # (`_restore_layout`) - wczesniej splitter nie zna swojej prawdziwej
        # szerokosci i przy pierwszym ulozeniu rozdzielilby roznice po swojemu.
        self.panel_splitter = QSplitter(Qt.Horizontal)
        self.panel_splitter.addWidget(left)
        self.panel_splitter.addWidget(self.view)
        self.panel_splitter.addWidget(right)
        for index, stretch in enumerate((0, 1, 0)):
            self.panel_splitter.setStretchFactor(index, stretch)
            self.panel_splitter.setCollapsible(index, False)
        self.panel_splitter.splitterMoved.connect(self._remember_layout)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.panel_splitter)
        splitter.addWidget(strip)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.splitterMoved.connect(self._remember_layout)
        self.strip_splitter = splitter
        self._strip_header = strip_header
        self._layout_restored = False

        # Zakladki na samej gorze. W widoku mapy nie widac paska miniatur,
        # wiec mapa ma wlasna liste zdjec - przy przejsciu podajemy jej
        # aktualna zawartosc katalogu i zaznaczenie.
        #
        # Mapa powstaje dopiero przy pierwszym wejsciu na zakladke. Silnik
        # przegladarki wstaje ponad dwie sekundy i robil to przy KAZDYM
        # uruchomieniu programu, takze wtedy, gdy nikt mapy nie otwieral.
        # Po zmianie okno startuje tak szybko jak wczesniej, a te dwie
        # sekundy placi ten, kto faktycznie chce mape.
        self.map_view: MapView | None = None
        self.map_tab = QWidget()
        map_layout = QVBoxLayout(self.map_tab)
        map_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, t("Edycja"))
        self.tabs.addTab(self.map_tab, t("Mapa"))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 2, 6, 4)
        corner_layout.addWidget(self.export_button)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)

        self.setCentralWidget(self.tabs)
        self.status = self.statusBar()
        self.status.showMessage(t("Otwórz folder ze zdjęciami:  Ctrl+O"))

        # pasek postepu eksportu - siedzi po prawej stronie paska stanu
        # i pojawia sie tylko na czas pracy
        self.progress_widget = QWidget()
        progress_layout = QHBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 0, 6, 0)
        progress_layout.setSpacing(8)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("metaLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setTextVisible(False)
        self.cancel_export_button = QPushButton(t("Przerwij"))
        podpowiedz(self.cancel_export_button, "okno.przerwij")
        self.cancel_export_button.clicked.connect(self._cancel_export)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.cancel_export_button)
        self.progress_widget.hide()
        self.status.addPermanentWidget(self.progress_widget)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(t("&Plik"))
        for text, shortcut, slot in (
            (t("&Otwórz folder…"), QKeySequence.Open, self.open_folder),
            (t("&Eksportuj…"), QKeySequence("Ctrl+E"), self.export_current),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)

        self.recent_menu = file_menu.addMenu(t("Ostatnie katalogi"))
        self._build_recent_menu()
        file_menu.addSeparator()
        settings_action = QAction(t("&Ustawienia…"), self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(lambda: self.open_settings())
        file_menu.addAction(settings_action)

        file_menu.addSeparator()
        quit_action = QAction(t("Zakończ"), self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Korekta i kadrowanie zmieniaja zdjecie, wiec naleza do Edycji,
        # a nie do Widoku. Skroty zostaja te same.
        edit_menu = self.menuBar().addMenu(t("&Edycja"))
        auto_action = QAction(t("Automatyczna korekcja"), self)
        auto_action.setShortcut(QKeySequence("Ctrl+U"))
        auto_action.triggered.connect(self._run_auto)
        edit_menu.addAction(auto_action)
        crop_action = QAction(t("Kadrowanie"), self)
        crop_action.setShortcut(QKeySequence("R"))
        crop_action.triggered.connect(
            lambda: self.edit_panel.crop_button.setChecked(not self.crop_mode)
        )
        edit_menu.addAction(crop_action)

        view_menu = self.menuBar().addMenu(t("&Widok"))
        for text, shortcut, slot in (
            (t("Dopasuj do okna"), "Ctrl+0", self.view.fit_to_window),
            (t("Powiększenie 100 %"), "Ctrl+1", self.view.zoom_actual),
        ):
            action = QAction(text, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            view_menu.addAction(action)

        help_menu = self.menuBar().addMenu(t("Pomo&c"))
        about_action = QAction(t("O programie"), self)
        about_action.triggered.connect(lambda: self.open_settings(PAGE_ABOUT))
        help_menu.addAction(about_action)

    # ------------------------------------------------------------ uklad okna

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._layout_restored:
            self._layout_restored = True
            # po biezacym obiegu petli: okno pokazywane jako zmaksymalizowane
            # dostaje ostateczny rozmiar dopiero chwile po showEvent
            QTimer.singleShot(0, self._restore_layout)

    def _restore_layout(self) -> None:
        """Naklada zapamietane szerokosci paneli i wysokosc paska miniatur."""
        s = self.settings
        sizes = self.panel_splitter.sizes()
        total = sum(sizes)
        centre = max(1, total - s.left_panel_width - s.right_panel_width)
        self.panel_splitter.setSizes([s.left_panel_width, centre, s.right_panel_width])

        sizes = self.strip_splitter.sizes()
        strip = s.filmstrip_height + self._strip_header.sizeHint().height()
        self.strip_splitter.setSizes([max(1, sum(sizes) - strip), strip])

    def _remember_layout(self, *_args) -> None:
        """Przepisuje rozmiary do ustawien; na dysk ida przy zamknieciu okna."""
        left, _centre, right = self.panel_splitter.sizes()
        # Zakladka Mapa chowa splitter - wtedy rozmiary sa zerowe i nic nie mowia.
        if left > 0 and right > 0:
            self.settings.left_panel_width = left
            self.settings.right_panel_width = right
        if self.filmstrip.height() > 0:
            self.settings.filmstrip_height = self.filmstrip.height()

    def _build_recent_menu(self) -> None:
        """Lista ostatnich katalogow. Nieistniejace pomijamy, ale nie kasujemy.

        Dysk zewnetrzny albo karta pamieci potrafi byc chwilowo odlaczona -
        wyrzucenie takiego katalogu z historii przy pierwszym uruchomieniu bez
        niego byloby dla uzytkownika niespodzianka.
        """
        self.recent_menu.clear()
        existing = [f for f in self.settings.recent_folders if os.path.isdir(f)]
        if not existing:
            empty = QAction(t("(pusto)"), self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
            return
        for folder in existing:
            action = QAction(folder, self)
            action.triggered.connect(lambda checked=False, f=folder: self.load_folder(f))
            self.recent_menu.addAction(action)
        self.recent_menu.addSeparator()
        clear = QAction(t("Wyczyść listę"), self)
        clear.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear)

    def _clear_recent(self) -> None:
        self.settings.recent_folders = []
        self.settings.save()
        self._build_recent_menu()

    def closeEvent(self, event) -> None:
        """Ostatnie zdjecie tez ma trafic na dysk.

        Nastawy pozostalych zdjec sa juz zapisane - kazde dostalo swoj plik
        przy przejsciu dalej. Tutaj zostaje wylacznie to, ktore wlasnie jest
        otwarte.
        """
        self.remember_current_edits()
        self.settings.save()
        super().closeEvent(event)

    # ------------------------------------------------------------ ustawienia

    def gpu_allowed(self) -> bool:
        return self.gpu.available and self.settings.render_engine != ENGINE_CPU

    def _apply_settings(self) -> None:
        """Przenosi ustawienia na faktyczne zachowanie programu."""
        s = self.settings

        threads = s.thumbnail_threads or max(2, (os.cpu_count() or 4) - 1)
        self.thumb_pool.setMaxThreadCount(threads)

        # Tor GPU liczy synchronicznie na watku GUI, wiec wystarczy scalic
        # zdarzenia z jednego obiegu petli. Tor procesora idzie na watek
        # roboczy i potrzebuje prawdziwego wyciszenia, zeby nie kolejkowac
        # dziesieciu zadan na jeden przeciag suwaka.
        self.debounce.setInterval(DEBOUNCE_GPU_MS if self.gpu_allowed() else DEBOUNCE_CPU_MS)
        self.noise_timer.setInterval(s.noise_delay_ms)
        self.view.set_detail_delay(s.detail_delay_ms)
        self.navigator.setVisible(s.show_navigator)
        self.tooltip_switch.wlaczone = s.show_tooltips
        self.tooltip_style.opoznienie_ms = s.tooltip_delay_ms
        self.edit_panel.set_wheel_protection(s.wheel_lockout_ms, s.wheel_dwell_ms)

        if self.gpu.available and self.settings.render_engine == ENGINE_CPU:
            if self.gpu_source_ready:
                self.gpu.release_source()
                self.gpu_source_ready = False
        elif self.gpu_allowed() and self.full_raw is not None and not self.gpu_source_ready:
            self.gpu_source_ready = self.gpu.set_source(self.full_raw.camera_linear)

    def open_settings(self, page: str | None = None) -> None:
        dialog = SettingsDialog(self.settings, self.system, self)
        if page is not None:
            dialog.show_page(page)
        if dialog.exec() != SettingsDialog.Accepted:
            return

        previous = self.settings
        self.settings = dialog.result_settings()
        self.settings.save()
        self._apply_settings()

        # rozmiar podgladu zmienia dane wejsciowe, wiec wymaga przeliczenia
        if self.settings.preview_size != previous.preview_size and self.full_raw is not None:
            self.proxy = self.full_raw.proxy(self.settings.preview_size)
            self.before_image = develop(self.proxy, EditParams(), denoise=False)
        self._render_preview()
        self.status.showMessage(t("Zapisano ustawienia  •  podgląd: {silnik}", silnik=self._engine_name()))

    def _engine_name(self) -> str:
        if not self.gpu.available:
            return t("procesor (brak OpenGL)")
        if self.settings.render_engine == ENGINE_CPU:
            return t("procesor (wymuszony)")
        if self.settings.render_engine == ENGINE_GPU:
            return t("karta graficzna (wymuszona)")
        return t("karta graficzna") if self.gpu_source_ready else t("procesor")

    # --------------------------------------------------------------- folder

    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("Wybierz folder ze zdjęciami"))
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder: str) -> None:
        try:
            self.folder_paths = folder_photos(folder)
        except OSError as exc:
            QMessageBox.warning(self, "Punctum", t("Nie udało się otworzyć folderu:\n{blad}", blad=exc))
            return

        self.metadata.clear()
        self.view.clear_image()
        self.navigator.set_image(None)
        self.histogram_widget.set_histogram(None)
        self.info_panel.set_metadata(None)
        self.full_raw = self.proxy = None
        self.current_path = None

        raw_count, jpeg_count = count_formats(self.folder_paths)
        self.format_count.setText(f"{raw_count} RAW  •  {jpeg_count} JPEG")

        if not self.folder_paths:
            self.paths = []
            self.filmstrip.set_paths([])
            self.status.showMessage(t("{katalog} — nie znaleziono zdjęć", katalog=folder))
            return

        self.setWindowTitle(f"Punctum — {os.path.basename(folder)}")
        self.settings.last_folder = folder
        self.settings.remember_folder(folder)
        self.settings.save()
        self._build_recent_menu()

        # Zdjecia z zapisana praca sprawdzamy raz, przy wejsciu do katalogu -
        # to sam rzut oka na liste plikow, bez czytania ich zawartosci.
        self._sidecar_warned = False
        self.edited_on_disk = (
            edited_photos(self.folder_paths) if self.settings.store_edits else set()
        )
        self._refresh_filmstrip()

    def _on_format_changed(self) -> None:
        chosen = self.format_combo.currentData() or FORMAT_ALL
        if self.settings.format_filter != chosen:
            self.settings.format_filter = chosen
            self.settings.save()
        self._refresh_filmstrip()

    def _refresh_filmstrip(self) -> None:
        """Przepisuje pasek miniatur wedlug wybranego filtra formatow.

        Biezace zdjecie zostaje otwarte, jesli przetrwalo filtr - przelaczenie
        widoku nie powinno wyrzucac uzytkownika ze zdjecia, ktore wlasnie
        poprawia.
        """
        chosen = self.format_combo.currentData() or FORMAT_ALL
        previous = self.current_path
        self.paths = [p for p in self.folder_paths if matches_filter(p, chosen)]
        marked = self.edited_on_disk | {
            path for path, params in self.edits.items() if not params.is_default(is_jpeg(path))
        }
        self.filmstrip.set_paths(self.paths, marked, self._located_paths())

        if not self.paths:
            self.status.showMessage(
                t("{filtr}: w tym folderze nie ma takich plików", filtr=t(FORMAT_LABELS[chosen]))
            )
            return

        done = self.filmstrip.edited_count()
        progress = t("  •  poprawionych: {e} z {n}", e=done, n=len(self.paths)) if done else ""
        self.status.showMessage(
            mnoga(len(self.paths), "Wczytywanie miniatur… ({n} zdjęcie){postep}|"
                  "Wczytywanie miniatur… ({n} zdjęcia){postep}|"
                  "Wczytywanie miniatur… ({n} zdjęć){postep}", postep=progress)
        )
        for index, path in enumerate(self.paths):
            task = ThumbnailTask(index, path)
            task.signals.thumbnail_ready.connect(self._on_thumbnail)
            self.thumb_pool.start(task)

        row = self.paths.index(previous) if previous in self.paths else 0
        self.filmstrip.setCurrentRow(row)

    def _on_thumbnail(self, index: int, path: str, image, meta: PhotoMetadata) -> None:
        # Filtr formatow mogl przestawic liste, zanim miniatura dojechala -
        # bez sprawdzenia sciezki trafilaby wtedy pod cudza pozycje.
        self.metadata[path] = meta
        if index >= len(self.paths) or self.paths[index] != path:
            return
        self.filmstrip.set_thumbnail(index, image)
        # GPS z aparatu poznajemy dopiero po przeczytaniu EXIF-u, czyli razem
        # z miniatura - znacznik na liscie musi wiec doplynac tak samo pozno.
        if meta is not None and meta.has_gps:
            self.filmstrip.set_located(path, True)
        if path == self.current_path:
            self.info_panel.set_metadata(meta, self._own_location(path))
        if self.thumb_pool.activeThreadCount() <= 1:
            done = self.filmstrip.edited_count()
            progress = t("  •  poprawionych: {e} z {n}", e=done, n=len(self.paths)) if done else ""
            self.status.showMessage(mnoga(len(self.paths), "{n} zdjęcie{postep}|{n} zdjęcia{postep}|{n} zdjęć{postep}",
                      postep=progress))

    # ---------------------------------------------------------------- zdjecie

    def remember_current_edits(self) -> None:
        """Zapisuje nastawy biezacego zdjecia, zanim przejdziemy na inne."""
        if self.current_path and self.full_raw is not None:
            self.edits[self.current_path] = self.export_params()
            self._store_edits(self.current_path)

    # ---------------------------------------------------------- metadane

    def _on_metadata_changed(self, changes: dict) -> None:
        """Panel EXIF zglosil zmiane pol dla biezacego zdjecia."""
        if not self.current_path:
            return
        params = self._params_for(self.current_path) or default_params_for(self.current_path or "")
        params.metadata = dict(changes)
        self.edits[self.current_path] = params
        self._store_edits(self.current_path)
        # Drugi panel (w zakladce mapy) pokazuje to samo zdjecie, wiec musi
        # dostac ten sam stan - inaczej dwie kopie rozjechalyby sie cicho.
        for panel in self._exif_panels():
            if panel.path == self.current_path and not panel.hasFocus():
                panel.set_photo(self.current_path, params.metadata)

    def _exif_panels(self) -> list:
        panels = [self.exif_panel]
        if self.map_view is not None:
            panels.append(self.map_view.exif_panel)
        return panels

    def _show_metadata(self, path: str | None) -> None:
        params = self._params_for(path) if path else None
        overrides = params.metadata if params is not None else {}
        for panel in self._exif_panels():
            panel.set_photo(path, overrides)

    def _write_metadata_to_originals(self) -> None:
        """Wpisuje metadane i lokalizacje wprost w pliki zrodlowe.

        Domyslnie wszystko siedzi w sidecarach, ale czasem trzeba miec to
        w samych plikach - zeby zobaczyl je inny program. RAW-ow nie ruszamy
        i mowimy o tym wprost, zamiast po cichu ich pomijac.
        """
        from ..core.exif_edit import is_writable_format, write_into_file

        chosen = self.filmstrip.selected_paths() or (
            [self.current_path] if self.current_path else []
        )
        if not chosen:
            return

        self.remember_current_edits()
        written, skipped, errors = 0, [], []
        for path in chosen:
            params = self._params_for(path)
            if params is None or (not params.has_metadata and not params.has_location):
                continue
            location = (
                (params.latitude, params.longitude) if params.has_location else None
            )
            problem = write_into_file(path, params.metadata, location)
            if problem is None:
                written += 1
            # po formacie, nie po tresci komunikatu - ta zalezy od jezyka
            elif not is_writable_format(path):
                skipped.append(os.path.basename(path))
            else:
                errors.append(problem)

        parts = [mnoga(written, "Zapisano do {n} pliku|Zapisano do {n} plików|Zapisano do {n} plików")]
        if skipped:
            parts.append(
                t("pominięto {n} (format bez zapisu EXIF: {pliki})", n=len(skipped),
                  pliki=", ".join(skipped[:3]) + ("…" if len(skipped) > 3 else ""))
            )
        if errors:
            parts.append(t("błędy: {n}", n=len(errors)))
        self.status.showMessage("  •  ".join(parts))
        if errors:
            QMessageBox.warning(self, "Punctum", "\n".join(errors[:10]))

    def _on_thumbnail_icon(self, path: str, icon) -> None:
        """Gotowa miniatura trafia tez do listy w mapie, jesli ta juz stoi."""
        if self.map_view is not None:
            self.map_view.set_thumbnail(path, icon)

    # -------------------------------------------------------------- mapa

    def _own_location(self, path: str) -> tuple[float, float] | None:
        """Wspolrzedne nadane przez nas - te, ktore biora gore nad EXIF-em."""
        params = self.edits.get(path)
        if params is not None and params.has_location:
            return (params.latitude, params.longitude)
        return None

    def _has_location(self, path: str) -> bool:
        """Czy zdjecie ma wspolrzedne - nasze albo z aparatu."""
        if self._own_location(path) is not None:
            return True
        meta = self.metadata.get(path)
        return bool(meta is not None and meta.has_gps)

    def _located_paths(self) -> set[str]:
        """Zdjecia z wspolrzednymi - do znacznikow na liscie.

        Sidecary czytamy tylko dla plikow, ktore je w ogole maja (wiemy to
        z jednego przegladu katalogu), a nie dla wszystkich zdjec - przy 2000
        plikow reszta bylaby czystym czekaniem na dysk. Wynik zostaje potem
        w pamieci, wiec zmiana filtra formatow juz nic nie kosztuje.
        """
        found = {
            path for path, meta in self.metadata.items()
            if meta is not None and meta.has_gps
        }
        candidates = set(self.edits) | (self.edited_on_disk & set(self.paths))
        for path in candidates:
            params = self._params_for(path)
            if params is not None and params.has_location:
                found.add(path)
        return found

    def _known_locations(self) -> dict[str, tuple[float, float]]:
        """Wspolrzedne wszystkich zdjec w katalogu: z naszych nastaw i z EXIF-u.

        Pierwszenstwo ma to, co nadalismy sami - jesli zdjecie mialo juz GPS
        z aparatu, a uzytkownik przestawil je na mapie, liczy sie jego decyzja.
        """
        locations: dict[str, tuple[float, float]] = {}
        for path in self.folder_paths:
            meta = self.metadata.get(path)
            if meta is not None and meta.has_gps:
                locations[path] = (meta.latitude, meta.longitude)
        for path in self.folder_paths:
            params = self._params_for(path)
            if params is not None and params.has_location:
                locations[path] = (params.latitude, params.longitude)
        return locations

    def _ensure_map(self) -> MapView:
        """Buduje mape - normalnie przy starcie, przed pokazaniem okna.

        Zostaje tu na wypadek, gdyby budowa przy starcie sie nie powiodla;
        wtedy zakladka probuje jeszcze raz, a uzytkownik widzi komunikat.
        """
        if self.map_view is None:
            if self.isVisible():
                self.status.showMessage(t("Uruchamianie mapy…"))
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.map_view = MapView()
                self.map_view.location_assigned.connect(self._on_location_assigned)
                self.map_view.photo_activated.connect(self._open_from_map)
                # Drugi panel metadanych - ten sam stan, te same sygnaly, co
                # panel w Edycji. Zdjecie biezace dostaje od razu, bo mapa
                # powstaje dopiero teraz i nie widziala wczesniejszych zmian.
                self.map_view.exif_panel.changed.connect(self._on_metadata_changed)
                self.map_view.exif_panel.write_requested.connect(
                    self._write_metadata_to_originals
                )
                self.map_tab.layout().addWidget(self.map_view)
                self._show_metadata(self.current_path)
            finally:
                QApplication.restoreOverrideCursor()
        return self.map_view

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is not self.map_tab:
            return
        self.remember_current_edits()  # nastawy biezacego zdjecia przed skokiem
        self._ensure_map()
        self.map_view.set_photos(
            self.paths,
            self._known_locations(),
            self.filmstrip.icons(),
            self.filmstrip.edited_paths(),
        )
        chosen = self.filmstrip.selected_paths() or (
            [self.current_path] if self.current_path else []
        )
        self.map_view.set_selection(chosen)

    def _on_location_assigned(self, paths: list, latitude, longitude) -> None:
        """Mapa nadala albo skasowala wspolrzedne zaznaczonym zdjeciom."""
        changed: dict[str, tuple[float, float] | None] = {}
        for path in paths:
            params = self._params_for(path) or default_params_for(path)
            params.latitude = latitude
            params.longitude = longitude
            self.edits[path] = params
            self._store_edits(path)
            changed[path] = None if latitude is None else (latitude, longitude)
            self.filmstrip.set_located(path, self._has_location(path))

        if self.map_view is not None:
            self.map_view.apply_locations(changed)
        if self.current_path in changed:
            self.info_panel.set_metadata(
                self.metadata.get(self.current_path),
                self._own_location(self.current_path),
            )
        if latitude is None:
            self.status.showMessage(mnoga(len(paths), "Usunięto lokalizację z {n} zdjęcia|"
                      "Usunięto lokalizację z {n} zdjęć|Usunięto lokalizację z {n} zdjęć"))
        else:
            self.status.showMessage(
                mnoga(len(paths),
                      "Nadano lokalizację {wsp} — {n} zdjęcie. Zapis w plikach XMP obok "
                      "zdjęć; do metadanych trafi przy eksporcie.|"
                      "Nadano lokalizację {wsp} — {n} zdjęcia. Zapis w plikach XMP obok "
                      "zdjęć; do metadanych trafi przy eksporcie.|"
                      "Nadano lokalizację {wsp} — {n} zdjęć. Zapis w plikach XMP obok "
                      "zdjęć; do metadanych trafi przy eksporcie.",
                      wsp=f"{latitude:.5f}, {longitude:.5f}")
            )

    def _open_from_map(self, path: str) -> None:
        """Dwuklik na liscie w mapie: wroc do edycji tego zdjecia."""
        self.tabs.setCurrentIndex(0)
        if path in self.paths:
            self.filmstrip.setCurrentRow(self.paths.index(path))

    def _params_for(self, path: str) -> EditParams | None:
        """Nastawy zdjecia: z tej sesji albo z dysku. None, gdy nie ma zadnych.

        To jest miejsce, w ktorym trwalosc nastaw spotyka sie z eksportem
        wsadowym - i bez tego caly pomysl rozlozenia pracy na dni nie
        dzialalby. Zdjecia poprawione wczoraj nie sa dzis otwarte, wiec nie ma
        ich w pamieci; eksport bralby dla nich czyste suwaki i po cichu
        wyrzucal wczorajsza robote.
        """
        params = self.edits.get(path)
        if params is not None:
            return params
        if not self.settings.store_edits:
            return None
        params = read_sidecar(path)
        if params is not None:
            self.edits[path] = params
        return params

    def _store_edits(self, path: str) -> None:
        """Zapisuje nastawy na dysk, obok zdjecia.

        Zapis idzie przy kazdym przejsciu na inne zdjecie i przy zamknieciu
        okna, a nie dopiero na koniec sesji: zawieszenie programu po trzech
        godzinach pracy ma kosztowac jedno zdjecie, nie trzy godziny.
        """
        if not self.settings.store_edits:
            return
        params = self.edits.get(path)
        if params is None:
            return
        written = write_sidecar(path, params)
        marked = bool(written) and not params.is_default(is_jpeg(path))
        self.filmstrip.set_edited(path, marked)
        self.filmstrip.set_located(path, self._has_location(path))
        if self.map_view is not None:
            self.map_view.set_edited(path, marked)

        # Katalog tylko do odczytu albo wyjeta karta: bez slowa uzytkownik
        # pracowalby przez godzine w przekonaniu, ze praca sie zapisuje.
        if written is None and not params.is_default(is_jpeg(path)) and not self._sidecar_warned:
            self._sidecar_warned = True
            self.status.showMessage(
                t("Nie udało się zapisać korekt obok zdjęcia — katalog jest tylko "
                "do odczytu albo brakuje miejsca. Praca zostaje tylko w pamięci.")
            )

    def open_photo(self, path: str) -> None:
        if path == self.current_path:
            return
        self.remember_current_edits()
        self.current_path = path
        self.full_raw = self.proxy = None
        self.before_image = self.current_image = None
        self.orientation, self.crop = 0, FULL_CROP
        self.noise_timer.stop()
        self._noise_pending = None
        if self.gpu_source_ready:
            self.gpu.release_source()  # 244 MB tekstury na zdjęcie, warto oddać
            self.gpu_source_ready = False
        self.info_panel.set_metadata(self.metadata.get(path), self._own_location(path))
        # Metadane pokazujemy od razu, nie po zdekodowaniu RAW-a: naglowek
        # czyta sie w kilka milisekund, a panel czekajacy sekunde na tresc
        # wygladalby na zepsuty.
        self._show_metadata(path)
        self.status.showMessage(t("Wczytywanie {plik}…", plik=os.path.basename(path)))
        self.export_button.setEnabled(False)

        task = LoadRawTask(path)
        task.signals.raw_ready.connect(self._on_raw_ready)
        task.signals.raw_failed.connect(self._on_raw_failed)
        self.pool.start(task)

    def _on_raw_ready(self, path: str, raw: RawImage) -> None:
        if path != self.current_path:
            return  # uzytkownik zdazyl przejsc na inne zdjecie
        self.full_raw = raw
        self.proxy = raw.proxy(self.settings.preview_size)
        is_jpeg = raw.source_format == "jpeg"
        self.edit_panel.set_as_shot_temp(raw.as_shot_temp, raw.as_shot_tint, relative=is_jpeg)
        self.before_image = develop(self.proxy, EditParams(), denoise=False)
        self.export_button.setEnabled(True)

        # Zdjecie bez zapisanych korekt musi pokazac czyste suwaki. Zostawienie
        # nastaw z poprzedniego zdjecia bylo mylace: panel twierdzil, ze jest
        # korekta, ktorej podglad nie pokazywal.
        saved = self.edits.get(path)
        damaged = False
        if saved is None and self.settings.store_edits:
            # Praca z poprzedniej sesji lezy obok zdjecia - wczytujemy ja
            # dopiero teraz, przy otwarciu, zeby wejscie do katalogu z 2000
            # zdjec nie czytalo 2000 plikow XML.
            saved = read_sidecar(path)
            if saved is not None:
                self.edits[path] = saved
            else:
                # Znacznik mowi "tu byla praca", a nastaw nie ma - plik jest
                # uszkodzony. Milczenie w tym miejscu byloby najgorsze:
                # uzytkownik zaczalby poprawiac zdjecie od nowa, nie wiedzac,
                # ze cos przepadlo.
                damaged = path in self.edited_on_disk
        if saved is not None:
            self.orientation, self.crop = saved.orientation, saved.crop
        self.edit_panel.load_params(saved if saved is not None else default_params_for(path))
        self.view.set_crop_fractions(self.crop)

        # Do pamieci karty wgrywamy PELNA rozdzielczosc, nie proxy. Dzieki temu
        # z jednej tekstury powstaje i podglad dopasowany do okna, i ostry
        # fragment przy powiekszeniu 400 % - bez ponownego liczenia czegokolwiek
        # na procesorze.
        self.gpu_source_ready = self.gpu_allowed() and self.gpu.set_source(raw.camera_linear)

        white_balance = (
            t("balans bieli względny (JPEG)") if is_jpeg
            else t("balans bieli {k} K", k=f"{raw.as_shot_temp:.0f}")
        )
        if damaged:
            self.status.showMessage(
                t("{plik} — obok leżał plik z korektami, ale nie da się go odczytać. "
                  "Suwaki startują czyste.", plik=os.path.basename(path))
            )
        else:
            restored = t("  •  wczytano zapisane korekty") if saved is not None else ""
            self.status.showMessage(
                f"{os.path.basename(path)}  •  {'JPEG' if is_jpeg else 'RAW'}  •  "
                f"{raw.raw_width}×{raw.raw_height}  •  {white_balance}  •  "
                + t("podgląd: {silnik}", silnik=self._engine_name()) + restored
            )
        self._render_preview()

    def _on_raw_failed(self, path: str, message: str) -> None:
        if path != self.current_path:
            return
        self.view.clear_image()
        self.navigator.set_image(None)
        self.histogram_widget.set_histogram(None)
        self.status.showMessage(t("Nie udało się wczytać {plik} — {blad}", plik=os.path.basename(path), blad=message))

    # ----------------------------------------------------------- parametry

    def display_params(self) -> EditParams:
        """Parametry uzyte do podgladu.

        W trybie kadrowania celowo pokazujemy zdjecie NIEPRZYCIETE - inaczej
        nie dalo by sie rozciagnac ramki z powrotem na odrzucony fragment.
        """
        crop = FULL_CROP if self.crop_mode else self.crop
        return self.edit_panel.params(self.orientation, crop)

    def export_params(self) -> EditParams:
        """Komplet nastaw biezacego zdjecia, razem z lokalizacja.

        Panel suwakow buduje EditParams od zera, a wspolrzednych nie ma na
        zadnym suwaku - bez tego przeniesienia ruch dowolnego suwaka po
        powrocie z mapy kasowalby swiezo nadana lokalizacje.
        """
        params = self.edit_panel.params(self.orientation, self.crop)
        previous = self.edits.get(self.current_path or "")
        if previous is not None:
            params.latitude, params.longitude = previous.latitude, previous.longitude
            params.metadata = dict(previous.metadata)
        return params

    def _on_params_changed(self) -> None:
        self.debounce.start()

    def _on_reset_all(self) -> None:
        self.orientation, self.crop = 0, FULL_CROP
        self.view.set_crop_fractions(FULL_CROP)
        self.edit_panel.reset_all()

    # ----------------------------------------------------------- przeliczanie

    def _render_preview(self) -> None:
        if self.proxy is None or self.full_raw is None:
            return
        params = self.display_params()
        out_w, out_h = geometry_size(self.full_raw, params)

        if self.gpu_source_ready:
            # Rysujemy caly kadr pomniejszony do rozmiaru podgladu. Karta robi
            # to w kilka milisekund, wiec nie ma po co schodzic na watek roboczy
            # ani opozniac reakcji suwaka.
            scale = min(1.0, self.settings.preview_size / float(max(out_w, out_h)))
            rgb8 = self.gpu.render(
                self.full_raw, params,
                max(1, round(out_w * scale)), max(1, round(out_h * scale)),
                region=(0, 0, out_w, out_h), scale=scale,
            )
            if rgb8 is not None:
                self._show_preview(rgb8, (out_w, out_h), params)
                return
            self.gpu_source_ready = False  # karta odmowila, wracamy na procesor

        self._job_counter += 1
        self._latest_job = self._job_counter
        task = RenderTask(self._job_counter, self.proxy, params, denoise=False)
        task.signals.render_ready.connect(self._on_render_ready)
        self.pool.start(task)

    def _show_preview(self, rgb8: np.ndarray, image_size: tuple, params: EditParams) -> None:
        self.current_image = rgb8
        # odszumianie liczy procesor, wiec dokladamy je dopiero po chwili ciszy
        if params.needs_detail_pass(rgb8.shape[1] / float(max(1, image_size[0]))):
            self._noise_pending = (rgb8, params)
            self.noise_timer.start()
        else:
            self._noise_pending = None
            self.noise_timer.stop()
        if self._before_shown:
            return  # pokazemy po puszczeniu przycisku
        self.view.set_image(rgb8, image_size)
        self.navigator.set_pixmap(self.view.base_pixmap())
        self.histogram_widget.set_histogram(histogram(rgb8))
        if self.crop_mode:
            self.view.set_crop_fractions(self.crop)

    def _on_render_ready(self, job_id: int, rgb8: np.ndarray) -> None:
        if job_id != self._latest_job or self.full_raw is None:
            return  # przestarzaly wynik - suwak ruszyl sie w miedzyczasie
        params = self.display_params()
        self._show_preview(rgb8, geometry_size(self.full_raw, params), params)

    def _render_noise_pass(self) -> None:
        if self._noise_pending is None:
            return
        image, params = self._noise_pending
        self._job_counter += 1
        self._latest_job = self._job_counter
        # podglad bywa pomniejszony - promien wyostrzania liczymy w pikselach zdjecia
        scale = image.shape[1] / float(max(1, self.view.image_size[0]))
        task = NoiseReductionTask(self._job_counter, image, params, scale,
                                  quality=self.settings.preview_noise_quality)
        task.signals.render_ready.connect(self._on_noise_ready)
        self.pool.start(task)

    def _on_noise_ready(self, job_id: int, rgb8: np.ndarray) -> None:
        if job_id != self._latest_job or self.full_raw is None:
            return
        self.current_image = rgb8
        if self._before_shown:
            return
        self.view.set_image(rgb8, self.view.image_size)
        self.navigator.set_pixmap(self.view.base_pixmap())
        self.histogram_widget.set_histogram(histogram(rgb8))

    def _render_detail(self, rect: QRect, scale: float) -> None:
        if self.full_raw is None:
            return
        # Przy "przed" ostry fragment tez ma byc bez korekt - inaczej po
        # chwili na zdjecie bez korekt wjezdzal fragment z korektami.
        # EditParams() ma domyslnie kolor 25 i wyostrzanie 40 - "przed" liczymy
        # bez nich, tak jak podglad before_image.
        before = EditParams(noise_color=0.0, sharpen_amount=0.0)
        params = before if self._before_shown else self.display_params()
        # Shader nie odszumia ani nie wyostrza. Gdy ktores jest wlaczone, ostry
        # fragment liczymy na procesorze; z karty wjezdzal fragment BEZ tych
        # efektow na gotowy podglad i efekt suwaka znikal po chwili.
        denoise = params.needs_detail_pass(min(scale, 1.0))

        if self.gpu_source_ready and not denoise:
            rgb8 = self.gpu.render(
                self.full_raw, params,
                max(1, round(rect.width() * scale)), max(1, round(rect.height() * scale)),
                region=(rect.x(), rect.y(), rect.width(), rect.height()), scale=scale,
                nearest=scale >= self.settings.pixel_peek_zoom,
            )
            if rgb8 is not None:
                self.view.set_detail(rgb8, rect, scale)
                self.detail_label.setText(t("pełna ostrość"))
                return

        self._job_counter += 1
        self._latest_detail = self._job_counter
        task = DetailRenderTask(self._job_counter, self.full_raw, params, rect, scale,
                                quality=self.settings.preview_noise_quality)
        task.signals.detail_ready.connect(self._on_detail_ready)
        self.pool.start(task)
        self.detail_label.setText(t("ostrzenie…"))

    def _on_detail_ready(self, job_id: int, rgb8, rect: QRect, scale: float) -> None:
        if job_id != self._latest_detail:
            return
        self.view.set_detail(rgb8, rect, scale)
        self.detail_label.setText(t("pełna ostrość"))

    def _on_view_rect(self, rect: QRectF) -> None:
        self.navigator.set_view_rect(None if rect.isNull() else rect)
        # Zmiana rozmiaru okna przesuwa dolna granice suwaka ("dopasuj"),
        # choc samo powiekszenie stoi w miejscu.
        if not rect.isNull():
            self.zoom_panel.set_zoom(self.view.zoom, self.view.fit_zoom())
        if rect.width() >= 1.0 and rect.height() >= 1.0:
            self.detail_label.setText("")

    # ------------------------------------------------------------- przed/po

    def _show_before(self) -> None:
        if self.before_image is None:
            return
        self._before_shown = True
        self._latest_detail = -1  # fragment liczony jeszcze "po" ma przepasc
        self.view.clear_detail()
        self.view.set_image(
            self.before_image,
            geometry_size(self.full_raw, EditParams()) if self.full_raw else (1, 1),
        )
        self.histogram_widget.set_histogram(histogram(self.before_image))

    def _show_after(self) -> None:
        self._before_shown = False
        self._latest_detail = -1  # fragment "przed" nie moze wjechac na "po"
        if self.current_image is None or self.full_raw is None:
            return
        self.view.set_image(
            self.current_image, geometry_size(self.full_raw, self.display_params())
        )
        self.histogram_widget.set_histogram(histogram(self.current_image))

    # ---------------------------------------------------------- kadrowanie

    def _set_crop_mode(self, enabled: bool) -> None:
        self.crop_mode = enabled
        self.view.set_crop_mode(enabled)
        self.view.set_rotation(self.edit_panel.sliders["rotation"].value())
        self._render_preview()
        self.status.showMessage(
            t("Kadrowanie: ciągnij za krawędzie (Shift zachowuje proporcje), "
            "poza kadrem obracasz zdjęcie. Enter zatwierdza.")
            if enabled
            else mnoga(len(self.paths), "{n} zdjęcie|{n} zdjęcia|{n} zdjęć")
        )

    def _on_crop_changed(self, crop: tuple) -> None:
        self.crop = crop

    def _on_rotation_dragged(self, degrees: float) -> None:
        self.edit_panel.set_rotation_silently(degrees)
        self.debounce.start()

    def _rotate_orientation(self, step: int) -> None:
        if self.full_raw is None:
            return
        self.orientation = (self.orientation + step) % 360
        self.crop = FULL_CROP  # po obrocie o 90° stary kadr nie ma juz sensu
        self.view.set_crop_fractions(FULL_CROP)
        self._render_preview()

    def _reset_crop(self) -> None:
        self.crop = FULL_CROP
        self.view.set_crop_fractions(FULL_CROP)
        self.edit_panel.set_rotation_silently(0.0)
        self.view.set_rotation(0.0)
        self._render_preview()

    def keyPressEvent(self, event) -> None:
        if self.crop_mode and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.edit_panel.crop_button.setChecked(False)
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- automat

    def _run_auto(self) -> None:
        if self.full_raw is None:
            return
        self.edit_panel.auto_button.setEnabled(False)
        self.status.showMessage(t("Dobieranie parametrów…"))
        task = AutoToneTask(self.current_path, self.full_raw, self.display_params())
        task.signals.auto_ready.connect(self._on_auto_ready)
        self.pool.start(task)

    def _on_auto_ready(self, path: str, values: dict) -> None:
        self.edit_panel.auto_button.setEnabled(True)
        if path != self.current_path or not values:
            return
        self.edit_panel.apply_values(values)
        summary = "  ".join(f"{k} {v:+g}" for k, v in values.items() if v)
        self.status.showMessage(t("Korekcja automatyczna:  {opis}", opis=summary))

    # ---------------------------------------------------------------- eksport

    def _export_options(self) -> ExportOptions:
        s = self.settings
        return ExportOptions(
            folder=s.export_folder,
            use_subfolder=s.export_use_subfolder,
            subfolder=s.export_subfolder,
            naming=s.export_naming,
            custom_name=s.export_custom_name,
            start_number=s.export_start_number,
            number_digits=s.export_number_digits,
            on_existing=s.export_on_existing,
            file_format=s.export_format,
            quality=s.export_quality,
            max_side=s.export_max_side,
            noise_quality=s.export_noise_quality,
            add_author=s.export_add_author,
            author=s.export_author,
            add_copyright=s.export_add_copyright,
            copyright=s.export_copyright,
            # Slowa kluczowe, temat i komentarz zaczynaja puste: tag jednej
            # serii nie ma prawa przez nieuwage trafic do nastepnej.
        )

    def _remember_export_options(self, o: ExportOptions) -> None:
        s = self.settings
        (s.export_folder, s.export_use_subfolder, s.export_subfolder) = (
            o.folder, o.use_subfolder, o.subfolder
        )
        (s.export_naming, s.export_custom_name) = (o.naming, o.custom_name)
        (s.export_start_number, s.export_number_digits) = (o.start_number, o.number_digits)
        s.export_on_existing = o.on_existing
        (s.export_format, s.export_quality) = (o.file_format, o.quality)
        (s.export_max_side, s.export_noise_quality) = (o.max_side, o.noise_quality)
        # Same pola wyboru - wartosci autora zmienia sie w ustawieniach
        # (patrz komentarz przy Settings.export_author).
        (s.export_add_author, s.export_add_copyright) = (o.add_author, o.add_copyright)
        s.save()

    def _ask_about_conflicts(self, plan) -> str | None:
        """Jedno pytanie o wszystkie kolizje naraz, zadane przed startem."""
        count = len(plan.conflicts)
        box = QMessageBox(self)
        box.setWindowTitle(t("Pliki już istnieją"))
        box.setIcon(QMessageBox.Question)
        box.setText(
            mnoga(count, "W katalogu docelowym jest już {n} plik o takich nazwach.|"
                  "W katalogu docelowym jest już {n} pliki o takich nazwach.|"
                  "W katalogu docelowym jest już {n} plików o takich nazwach.")
        )
        box.setInformativeText("\n".join(os.path.basename(p) for p in plan.conflicts[:6])
                               + ("\n…" if count > 6 else ""))
        overwrite = box.addButton(t("Zastąp"), QMessageBox.DestructiveRole)
        skip = box.addButton(t("Pomiń istniejące"), QMessageBox.AcceptRole)
        unique = box.addButton(t("Nowe nazwy"), QMessageBox.AcceptRole)
        box.addButton(t("Anuluj"), QMessageBox.RejectRole)
        box.setDefaultButton(unique)
        box.exec()

        clicked = box.clickedButton()
        if clicked is overwrite:
            return ON_EXISTING_OVERWRITE
        if clicked is skip:
            return ON_EXISTING_SKIP
        if clicked is unique:
            return ON_EXISTING_UNIQUE
        return None

    def export_current(self) -> None:
        if self.current_path is None:
            return
        if self.export_task is not None:
            QMessageBox.information(
                self, "Punctum", t("Eksport już trwa. Poczekaj albo go przerwij.")
            )
            return

        self.remember_current_edits()
        sources = self.filmstrip.selected_paths() or [self.current_path]
        edited = sum(1 for path in sources if self._params_for(path) is not None)

        dialog = ExportDialog(self._export_options(), sources, self)
        dialog.set_edited_count(edited)
        if dialog.exec() != ExportDialog.Accepted:
            return

        options = dialog.options
        self._remember_export_options(options)

        plan = plan_export(sources, options)
        policy = options.on_existing
        if plan.has_conflicts and policy == ON_EXISTING_ASK:
            policy = self._ask_about_conflicts(plan)
            if policy is None:
                return
        pairs, skipped = resolve_conflicts(plan, policy)

        if not pairs:
            self.status.showMessage(t("Nie zapisano nic — wszystkie pliki pominięto."))
            return

        try:
            os.makedirs(options.target_folder(), exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Punctum", t("Nie udało się utworzyć katalogu:\n{blad}", blad=exc))
            return

        params = {
            source: self._params_for(source) or default_params_for(source) for source, _ in pairs
        }
        task = ExportTask(pairs, params, options)
        task.signals.export_progress.connect(self._on_export_progress)
        task.signals.export_finished.connect(self._on_export_finished)
        self.export_task = task
        self._skipped_in_export = skipped

        self.progress_bar.setRange(0, len(pairs))
        self.progress_bar.setValue(0)
        self.progress_label.setText(t("Eksport {i} / {n}", i=0, n=len(pairs)))
        self.progress_widget.show()
        self.cancel_export_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.pool.start(task)

    def _on_export_progress(self, done: int, total: int, name: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_label.setText(
            t("Eksport {i} / {n}", i=done, n=total) + (f"  •  {name}" if name else "")
        )

    def _on_export_finished(self, saved: int, failed: int, errors: list) -> None:
        cancelled = self.export_task is not None and self.export_task.cancelled
        self.export_task = None
        self.progress_widget.hide()
        self.export_button.setEnabled(True)

        parts = [t("Zapisano {n}", n=saved)]
        if getattr(self, "_skipped_in_export", 0):
            parts.append(t("pominięto {n}", n=self._skipped_in_export))
        if failed:
            parts.append(t("błędów: {n}", n=failed))
        if cancelled:
            parts.append(t("przerwano"))
        self.status.showMessage(t("Eksport zakończony  •  {wynik}", wynik=", ".join(parts)))

        if errors:
            box = QMessageBox(self)
            box.setWindowTitle(t("Eksport — problemy"))
            box.setIcon(QMessageBox.Warning)
            box.setText(mnoga(failed, "{n} zdjęcia nie udało się zapisać.|{n} zdjęć nie udało się zapisać.|"
                        "{n} zdjęć nie udało się zapisać."))
            box.setDetailedText("\n".join(errors))
            box.exec()

    def _cancel_export(self) -> None:
        if self.export_task is not None:
            self.export_task.cancel()
            self.progress_label.setText(t("Przerywanie…"))
            self.cancel_export_button.setEnabled(False)
