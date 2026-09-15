"""Glowne okno aplikacji."""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QRect, QRectF, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core import EditParams, RawImage, develop, geometry_size, histogram
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
from ..core.settings import ENGINE_CPU, ENGINE_GPU, Settings
from .edit_panel import EditPanel, HistogramWidget, InfoPanel
from .export_dialog import ExportDialog
from .filmstrip import Filmstrip
from .gpu_renderer import GpuRenderer
from .image_view import ImageView
from .navigator import Navigator
from .settings_dialog import SettingsDialog
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

RAW_EXTENSIONS = (".rw2", ".raw", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".dng", ".raf", ".pef")

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
        self.setStyleSheet(stylesheet())

        self.settings = Settings.load()
        self.pool = QThreadPool.globalInstance()
        self.thumb_pool = QThreadPool()

        self.paths: list[str] = []
        self.metadata: dict[str, PhotoMetadata] = {}
        # Nastawy edycji per zdjecie. Bez tego powrot do wczesniej poprawionego
        # zdjecia gubilby prace, a eksport wsadowy nakladalby na wszystkie
        # pliki ustawienia tego jednego, ktore akurat jest otwarte.
        self.edits: dict[str, EditParams] = {}
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

        self._apply_settings()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.view = ImageView()
        self.view.zoom_changed.connect(lambda z: self.zoom_label.setText(f"{z * 100:.0f} %"))
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

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self.navigator)
        right_layout.addWidget(self.histogram_widget)
        right_layout.addWidget(self.info_panel)
        right_layout.addWidget(self.edit_panel, 1)
        right.setMinimumWidth(300)
        right.setMaximumWidth(350)

        self.before_button = QPushButton("Przed / po")
        self.before_button.setToolTip("Przytrzymaj, aby zobaczyć zdjęcie bez korekt")
        self.before_button.pressed.connect(self._show_before)
        self.before_button.released.connect(self._show_after)

        self.fit_button = QPushButton("Dopasuj")
        self.fit_button.clicked.connect(self.view.fit_to_window)
        self.actual_button = QPushButton("100 %")
        self.actual_button.clicked.connect(self.view.zoom_actual)
        self.zoom_label = QLabel("—")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("metaLabel")
        self.detail_label.setMinimumWidth(70)

        self.export_button = QPushButton("Eksportuj…")
        self.export_button.clicked.connect(self.export_current)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setSpacing(6)
        toolbar_layout.addWidget(self.before_button)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.fit_button)
        toolbar_layout.addWidget(self.actual_button)
        toolbar_layout.addWidget(self.zoom_label)
        toolbar_layout.addWidget(self.detail_label)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.export_button)

        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(0, 0, 0, 0)
        centre_layout.setSpacing(0)
        centre_layout.addWidget(toolbar)
        centre_layout.addWidget(self.view, 1)

        self.filmstrip = Filmstrip()
        self.filmstrip.photo_selected.connect(self.open_photo)
        self.filmstrip.setFixedHeight(150)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addWidget(centre, 1)
        top_layout.addWidget(right)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(self.filmstrip)
        splitter.setStretchFactor(0, 1)
        splitter.setCollapsible(0, False)

        self.setCentralWidget(splitter)
        self.status = self.statusBar()
        self.status.showMessage("Otwórz folder ze zdjęciami:  Ctrl+O")

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
        self.cancel_export_button = QPushButton("Przerwij")
        self.cancel_export_button.clicked.connect(self._cancel_export)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.cancel_export_button)
        self.progress_widget.hide()
        self.status.addPermanentWidget(self.progress_widget)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Plik")
        for text, shortcut, slot in (
            ("&Otwórz folder…", QKeySequence.Open, self.open_folder),
            ("&Eksportuj…", QKeySequence("Ctrl+E"), self.export_current),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        file_menu.addSeparator()
        settings_action = QAction("&Ustawienia…", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()
        quit_action = QAction("Zakończ", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("&Widok")
        for text, shortcut, slot in (
            ("Dopasuj do okna", "Ctrl+0", self.view.fit_to_window),
            ("Powiększenie 100 %", "Ctrl+1", self.view.zoom_actual),
            ("Automatyczna korekcja", "Ctrl+U", self._run_auto),
        ):
            action = QAction(text, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            view_menu.addAction(action)

        crop_action = QAction("Kadrowanie", self)
        crop_action.setShortcut(QKeySequence("R"))
        crop_action.triggered.connect(
            lambda: self.edit_panel.crop_button.setChecked(not self.crop_mode)
        )
        view_menu.addAction(crop_action)

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
        self.edit_panel.set_wheel_protection(s.wheel_lockout_ms, s.wheel_dwell_ms)

        if self.gpu.available and self.settings.render_engine == ENGINE_CPU:
            if self.gpu_source_ready:
                self.gpu.release_source()
                self.gpu_source_ready = False
        elif self.gpu_allowed() and self.full_raw is not None and not self.gpu_source_ready:
            self.gpu_source_ready = self.gpu.set_source(self.full_raw.camera_linear)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.system, self)
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
        self.status.showMessage(f"Zapisano ustawienia  •  podgląd: {self._engine_name()}")

    def _engine_name(self) -> str:
        if not self.gpu.available:
            return "procesor (brak OpenGL)"
        if self.settings.render_engine == ENGINE_CPU:
            return "procesor (wymuszony)"
        if self.settings.render_engine == ENGINE_GPU:
            return "karta graficzna (wymuszona)"
        return "karta graficzna" if self.gpu_source_ready else "procesor"

    # --------------------------------------------------------------- folder

    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Wybierz folder ze zdjęciami")
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder: str) -> None:
        try:
            names = sorted(os.listdir(folder))
        except OSError as exc:
            QMessageBox.warning(self, "Punctum", f"Nie udało się otworzyć folderu:\n{exc}")
            return

        self.paths = [
            os.path.join(folder, name)
            for name in names
            if name.lower().endswith(RAW_EXTENSIONS)
        ]
        self.metadata.clear()
        self.filmstrip.set_paths(self.paths)
        self.view.clear_image()
        self.navigator.set_image(None)
        self.histogram_widget.set_histogram(None)
        self.info_panel.set_metadata(None)
        self.full_raw = self.proxy = None

        if not self.paths:
            self.status.showMessage(f"{folder} — nie znaleziono plików RAW")
            return

        self.setWindowTitle(f"Punctum — {os.path.basename(folder)}")
        self.status.showMessage(f"Wczytywanie miniatur… ({len(self.paths)} zdjęć)")
        if self.settings.last_folder != folder:
            self.settings.last_folder = folder
            self.settings.save()

        for index, path in enumerate(self.paths):
            task = ThumbnailTask(index, path)
            task.signals.thumbnail_ready.connect(self._on_thumbnail)
            self.thumb_pool.start(task)

        self.filmstrip.setCurrentRow(0)

    def _on_thumbnail(self, index: int, image, meta: PhotoMetadata) -> None:
        self.filmstrip.set_thumbnail(index, image)
        if 0 <= index < len(self.paths):
            self.metadata[self.paths[index]] = meta
            if self.paths[index] == self.current_path:
                self.info_panel.set_metadata(meta)
        if self.thumb_pool.activeThreadCount() <= 1:
            self.status.showMessage(f"{len(self.paths)} zdjęć")

    # ---------------------------------------------------------------- zdjecie

    def remember_current_edits(self) -> None:
        """Zapisuje nastawy biezacego zdjecia, zanim przejdziemy na inne."""
        if self.current_path and self.full_raw is not None:
            self.edits[self.current_path] = self.export_params()

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
        self.info_panel.set_metadata(self.metadata.get(path))
        self.status.showMessage(f"Wczytywanie {os.path.basename(path)}…")
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
        self.edit_panel.set_as_shot_temp(raw.as_shot_temp, raw.as_shot_tint)
        self.before_image = develop(self.proxy, EditParams(), denoise=False)
        self.export_button.setEnabled(True)

        # Zdjecie bez zapisanych korekt musi pokazac czyste suwaki. Zostawienie
        # nastaw z poprzedniego zdjecia bylo mylace: panel twierdzil, ze jest
        # korekta, ktorej podglad nie pokazywal.
        saved = self.edits.get(path)
        if saved is not None:
            self.orientation, self.crop = saved.orientation, saved.crop
        self.edit_panel.load_params(saved if saved is not None else EditParams())
        self.view.set_crop_fractions(self.crop)

        # Do pamieci karty wgrywamy PELNA rozdzielczosc, nie proxy. Dzieki temu
        # z jednej tekstury powstaje i podglad dopasowany do okna, i ostry
        # fragment przy powiekszeniu 400 % - bez ponownego liczenia czegokolwiek
        # na procesorze.
        self.gpu_source_ready = self.gpu_allowed() and self.gpu.set_source(raw.camera_linear)

        self.status.showMessage(
            f"{os.path.basename(path)}  •  {raw.raw_width}×{raw.raw_height}  •  "
            f"balans bieli {raw.as_shot_temp:.0f} K  •  podgląd: {self._engine_name()}"
        )
        self._render_preview()

    def _on_raw_failed(self, path: str, message: str) -> None:
        if path != self.current_path:
            return
        self.view.clear_image()
        self.navigator.set_image(None)
        self.histogram_widget.set_histogram(None)
        self.status.showMessage(f"Nie udało się wczytać {os.path.basename(path)} — {message}")

    # ----------------------------------------------------------- parametry

    def display_params(self) -> EditParams:
        """Parametry uzyte do podgladu.

        W trybie kadrowania celowo pokazujemy zdjecie NIEPRZYCIETE - inaczej
        nie dalo by sie rozciagnac ramki z powrotem na odrzucony fragment.
        """
        crop = FULL_CROP if self.crop_mode else self.crop
        return self.edit_panel.params(self.orientation, crop)

    def export_params(self) -> EditParams:
        return self.edit_panel.params(self.orientation, self.crop)

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
        self.view.set_image(rgb8, image_size)
        self.navigator.set_pixmap(self.view.base_pixmap())
        self.histogram_widget.set_histogram(histogram(rgb8))
        if self.crop_mode:
            self.view.set_crop_fractions(self.crop)
        # odszumianie liczy procesor, wiec dokladamy je dopiero po chwili ciszy
        if params.noise_luminance > 0.5 or params.noise_color > 0.5:
            self._noise_pending = (rgb8, params)
            self.noise_timer.start()
        else:
            self._noise_pending = None
            self.noise_timer.stop()

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
        task = NoiseReductionTask(self._job_counter, image, params)
        task.signals.render_ready.connect(self._on_noise_ready)
        self.pool.start(task)

    def _on_noise_ready(self, job_id: int, rgb8: np.ndarray) -> None:
        if job_id != self._latest_job or self.full_raw is None:
            return
        self.current_image = rgb8
        self.view.set_image(rgb8, self.view.image_size)
        self.navigator.set_pixmap(self.view.base_pixmap())
        self.histogram_widget.set_histogram(histogram(rgb8))

    def _render_detail(self, rect: QRect, scale: float) -> None:
        if self.full_raw is None:
            return
        params = self.display_params()

        if self.gpu_source_ready:
            rgb8 = self.gpu.render(
                self.full_raw, params,
                max(1, round(rect.width() * scale)), max(1, round(rect.height() * scale)),
                region=(rect.x(), rect.y(), rect.width(), rect.height()), scale=scale,
                nearest=scale >= self.settings.pixel_peek_zoom,
            )
            if rgb8 is not None:
                self.view.set_detail(rgb8, rect, scale)
                self.detail_label.setText("pełna ostrość")
                return

        self._job_counter += 1
        self._latest_detail = self._job_counter
        task = DetailRenderTask(self._job_counter, self.full_raw, params, rect, scale)
        task.signals.detail_ready.connect(self._on_detail_ready)
        self.pool.start(task)
        self.detail_label.setText("ostrzenie…")

    def _on_detail_ready(self, job_id: int, rgb8, rect: QRect, scale: float) -> None:
        if job_id != self._latest_detail:
            return
        self.view.set_detail(rgb8, rect, scale)
        self.detail_label.setText("pełna ostrość")

    def _on_view_rect(self, rect: QRectF) -> None:
        self.navigator.set_view_rect(None if rect.isNull() else rect)
        if rect.width() >= 1.0 and rect.height() >= 1.0:
            self.detail_label.setText("")

    # ------------------------------------------------------------- przed/po

    def _show_before(self) -> None:
        if self.before_image is None:
            return
        self.view.clear_detail()
        self.view.set_image(
            self.before_image,
            geometry_size(self.full_raw, EditParams()) if self.full_raw else (1, 1),
        )
        self.histogram_widget.set_histogram(histogram(self.before_image))

    def _show_after(self) -> None:
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
            "Kadrowanie: ciągnij za krawędzie (Shift zachowuje proporcje), "
            "poza kadrem obracasz zdjęcie. Enter zatwierdza."
            if enabled
            else f"{len(self.paths)} zdjęć"
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
        self.status.showMessage("Dobieranie parametrów…")
        task = AutoToneTask(self.current_path, self.full_raw, self.display_params())
        task.signals.auto_ready.connect(self._on_auto_ready)
        self.pool.start(task)

    def _on_auto_ready(self, path: str, values: dict) -> None:
        self.edit_panel.auto_button.setEnabled(True)
        if path != self.current_path or not values:
            return
        self.edit_panel.apply_values(values)
        summary = "  ".join(f"{k} {v:+g}" for k, v in values.items() if v)
        self.status.showMessage(f"Korekcja automatyczna:  {summary}")

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
        s.save()

    def _ask_about_conflicts(self, plan) -> str | None:
        """Jedno pytanie o wszystkie kolizje naraz, zadane przed startem."""
        count = len(plan.conflicts)
        box = QMessageBox(self)
        box.setWindowTitle("Pliki już istnieją")
        box.setIcon(QMessageBox.Question)
        box.setText(
            f"W katalogu docelowym jest już {count} "
            + ("plik" if count == 1 else "pliki" if 2 <= count <= 4 else "plików")
            + " o takich nazwach."
        )
        box.setInformativeText("\n".join(os.path.basename(p) for p in plan.conflicts[:6])
                               + ("\n…" if count > 6 else ""))
        overwrite = box.addButton("Zastąp", QMessageBox.DestructiveRole)
        skip = box.addButton("Pomiń istniejące", QMessageBox.AcceptRole)
        unique = box.addButton("Nowe nazwy", QMessageBox.AcceptRole)
        box.addButton("Anuluj", QMessageBox.RejectRole)
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
                self, "Punctum", "Eksport już trwa. Poczekaj albo go przerwij."
            )
            return

        self.remember_current_edits()
        sources = self.filmstrip.selected_paths() or [self.current_path]
        edited = sum(1 for path in sources if path in self.edits)

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
            self.status.showMessage("Nie zapisano nic — wszystkie pliki pominięto.")
            return

        try:
            os.makedirs(options.target_folder(), exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Punctum", f"Nie udało się utworzyć katalogu:\n{exc}")
            return

        params = {source: self.edits.get(source, EditParams()) for source, _ in pairs}
        task = ExportTask(pairs, params, options)
        task.signals.export_progress.connect(self._on_export_progress)
        task.signals.export_finished.connect(self._on_export_finished)
        self.export_task = task
        self._skipped_in_export = skipped

        self.progress_bar.setRange(0, len(pairs))
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"Eksport 0 / {len(pairs)}")
        self.progress_widget.show()
        self.cancel_export_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.pool.start(task)

    def _on_export_progress(self, done: int, total: int, name: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_label.setText(
            f"Eksport {done} / {total}" + (f"  •  {name}" if name else "")
        )

    def _on_export_finished(self, saved: int, failed: int, errors: list) -> None:
        cancelled = self.export_task is not None and self.export_task.cancelled
        self.export_task = None
        self.progress_widget.hide()
        self.export_button.setEnabled(True)

        parts = [f"Zapisano {saved}"]
        if getattr(self, "_skipped_in_export", 0):
            parts.append(f"pominięto {self._skipped_in_export}")
        if failed:
            parts.append(f"błędów: {failed}")
        if cancelled:
            parts.append("przerwano")
        self.status.showMessage("Eksport zakończony  •  " + ", ".join(parts))

        if errors:
            box = QMessageBox(self)
            box.setWindowTitle("Eksport — problemy")
            box.setIcon(QMessageBox.Warning)
            box.setText(f"{failed} zdjęć nie udało się zapisać.")
            box.setDetailedText("\n".join(errors))
            box.exec()

    def _cancel_export(self) -> None:
        if self.export_task is not None:
            self.export_task.cancel()
            self.progress_label.setText("Przerywanie…")
            self.cancel_export_button.setEnabled(False)
