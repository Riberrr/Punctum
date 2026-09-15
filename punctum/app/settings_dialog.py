"""Okno ustawien aplikacji.

Zakladki odpowiadaja obszarom dzialania programu, nie modulom kodu - dzieki
temu kolejne parametry beda mialy gdzie trafic bez przebudowy okna.

Dialog pracuje na KOPII ustawien. Zmiany zapisuja sie dopiero po nacisnieciu
"Zapisz", wiec "Anuluj" naprawde anuluje, a nie zostawia polowy zmian.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.hardware import SystemInfo
from ..core.settings import (
    ENGINE_AUTO,
    ENGINE_CPU,
    ENGINE_GPU,
    NOISE_QUALITY_LABELS,
    PREVIEW_SIZES,
    Settings,
    settings_path,
)

ENGINE_DESCRIPTIONS = {
    ENGINE_AUTO: "Użyj karty graficznej, jeśli jest dostępna; w razie problemu przejdź na procesor.",
    ENGINE_GPU: "Wymuś liczenie na karcie. Podgląd odświeża się w kilka milisekund.",
    ENGINE_CPU: "Wymuś liczenie na procesorze. Wolniejsze, ale niezależne od sterowników.",
}


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("metaLabel")
    label.setWordWrap(True)
    return label


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, system: SystemInfo, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ustawienia — Punctum")
        self.setMinimumWidth(560)
        self.settings = settings.copy()
        self.system = system

        self.tabs = QTabWidget()
        self.tabs.addTab(self._performance_tab(), "Wydajność")
        self.tabs.addTab(self._preview_tab(), "Podgląd")
        self.tabs.addTab(self._export_tab(), "Eksport")
        self.tabs.addTab(self._about_tab(), "O programie")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        buttons.button(QDialogButtonBox.Save).setText("Zapisz")
        buttons.button(QDialogButtonBox.Cancel).setText("Anuluj")
        buttons.button(QDialogButtonBox.RestoreDefaults).setText("Przywróć domyślne")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

        self._load_into_widgets()

    # ------------------------------------------------------- zakładki

    def _performance_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        # --- wykryty sprzet ---------------------------------------------
        hardware = QGroupBox("Wykryty sprzęt")
        form = QFormLayout(hardware)
        form.setLabelAlignment(Qt.AlignRight)

        self.cpu_label = QLabel(self.system.cpu.summary)
        self.cpu_label.setWordWrap(True)
        self.gpu_label = QLabel(self.system.gpu.summary)
        self.gpu_label.setWordWrap(True)
        self.system_label = QLabel(f"{self.system.system}  •  Python {self.system.python}")

        form.addRow("Procesor:", self.cpu_label)
        form.addRow("Karta graficzna:", self.gpu_label)
        form.addRow("System:", self.system_label)
        layout.addWidget(hardware)

        # --- wybor silnika ----------------------------------------------
        engine = QGroupBox("Silnik podglądu")
        engine_layout = QVBoxLayout(engine)
        self.engine_group = QButtonGroup(self)
        self.engine_buttons: dict[str, QRadioButton] = {}

        for key in (ENGINE_AUTO, ENGINE_GPU, ENGINE_CPU):
            button = QRadioButton(
                {"auto": "Automatycznie", "gpu": "Karta graficzna", "cpu": "Procesor"}[key]
            )
            self.engine_group.addButton(button)
            self.engine_buttons[key] = button
            engine_layout.addWidget(button)
            hint = _hint(ENGINE_DESCRIPTIONS[key])
            hint.setContentsMargins(22, 0, 0, 6)
            engine_layout.addWidget(hint)

        if not self.system.gpu.available:
            self.engine_buttons[ENGINE_GPU].setEnabled(False)
            engine_layout.addWidget(
                _hint(f"Karta niedostępna: {self.system.gpu.problem or 'brak kontekstu OpenGL'}")
            )
        layout.addWidget(engine)

        # --- zasoby ------------------------------------------------------
        resources = QGroupBox("Zasoby")
        resource_form = QFormLayout(resources)

        self.preview_size_box = QComboBox()
        for size in PREVIEW_SIZES:
            self.preview_size_box.addItem(f"{size} px", size)
        resource_form.addRow("Rozmiar podglądu:", self.preview_size_box)
        resource_form.addRow("", _hint(
            "Dłuższy bok obrazu liczonego dla widoku dopasowanego do okna. "
            "Przy powiększeniu i tak dokładany jest fragment z pełnej rozdzielczości."
        ))

        self.threads_box = QSpinBox()
        self.threads_box.setRange(0, 32)
        self.threads_box.setSpecialValueText("automatycznie")
        resource_form.addRow("Wątki miniatur:", self.threads_box)
        cores = self.system.cpu.cores_logical or 4
        resource_form.addRow("", _hint(f"Zero oznacza dobór automatyczny: {max(2, cores - 1)}."))

        layout.addWidget(resources)
        layout.addStretch(1)
        return page

    def _preview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        timing = QGroupBox("Opóźnienia")
        form = QFormLayout(timing)

        self.detail_delay_box = QSpinBox()
        self.detail_delay_box.setRange(0, 2000)
        self.detail_delay_box.setSingleStep(20)
        self.detail_delay_box.setSuffix(" ms")
        form.addRow("Doliczanie ostrego fragmentu:", self.detail_delay_box)
        form.addRow("", _hint(
            "Po tym czasie od zatrzymania kadru wczytywany jest fragment "
            "w pełnej rozdzielczości."
        ))

        self.noise_delay_box = QSpinBox()
        self.noise_delay_box.setRange(0, 5000)
        self.noise_delay_box.setSingleStep(50)
        self.noise_delay_box.setSuffix(" ms")
        form.addRow("Redukcja szumu:", self.noise_delay_box)
        form.addRow("", _hint(
            "Odszumianie liczy procesor, więc czeka, aż przestaniesz ruszać suwakiem."
        ))
        layout.addWidget(timing)

        quality = QGroupBox("Jakość")
        quality_form = QFormLayout(quality)

        self.preview_noise_box = QComboBox()
        for key, label in NOISE_QUALITY_LABELS.items():
            self.preview_noise_box.addItem(label, key)
        quality_form.addRow("Odszumianie podglądu:", self.preview_noise_box)

        self.pixel_peek_box = QDoubleSpinBox()
        self.pixel_peek_box.setRange(1.0, 16.0)
        self.pixel_peek_box.setSingleStep(0.5)
        self.pixel_peek_box.setSuffix(" ×")
        quality_form.addRow("Podgląd pikseli od:", self.pixel_peek_box)
        quality_form.addRow("", _hint(
            "Powyżej tego powiększenia obraz skalowany jest najbliższym sąsiadem, "
            "żeby było widać prawdziwe piksele zamiast interpolacji."
        ))

        self.navigator_box = QCheckBox("Pokazuj nawigator nad histogramem")
        quality_form.addRow("", self.navigator_box)
        layout.addWidget(quality)

        layout.addStretch(1)
        return page

    def _export_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        output = QGroupBox("Plik wynikowy")
        form = QFormLayout(output)

        self.format_box = QComboBox()
        for extension, label in ((".jpg", "JPEG"), (".png", "PNG"), (".tif", "TIFF")):
            self.format_box.addItem(label, extension)
        form.addRow("Format:", self.format_box)

        self.quality_box = QSpinBox()
        self.quality_box.setRange(50, 100)
        form.addRow("Jakość JPEG:", self.quality_box)

        self.max_side_box = QSpinBox()
        self.max_side_box.setRange(0, 20000)
        self.max_side_box.setSingleStep(100)
        self.max_side_box.setSpecialValueText("pełna rozdzielczość")
        self.max_side_box.setSuffix(" px")
        form.addRow("Dłuższy bok:", self.max_side_box)

        self.export_noise_box = QComboBox()
        for key, label in NOISE_QUALITY_LABELS.items():
            self.export_noise_box.addItem(label, key)
        form.addRow("Odszumianie:", self.export_noise_box)
        form.addRow("", _hint(
            "Przy eksporcie warto wybrać wariant dokładny — liczy się raz, "
            "a różnica jest widoczna w pełnej rozdzielczości."
        ))
        layout.addWidget(output)

        destination = QGroupBox("Katalog docelowy")
        destination_layout = QHBoxLayout(destination)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("pytaj przy każdym eksporcie")
        browse = QPushButton("Wybierz…")
        browse.clicked.connect(self._choose_folder)
        destination_layout.addWidget(self.folder_edit, 1)
        destination_layout.addWidget(browse)
        layout.addWidget(destination)

        general = QGroupBox("Ogólne")
        general_layout = QVBoxLayout(general)
        self.reopen_box = QCheckBox("Otwieraj ostatnio używany folder przy starcie")
        general_layout.addWidget(self.reopen_box)
        layout.addWidget(general)

        layout.addStretch(1)
        return page

    def _about_tab(self) -> QWidget:
        from .. import __version__

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        title = QLabel("Punctum")
        title.setObjectName("cameraLabel")
        layout.addWidget(title)
        layout.addWidget(_hint(f"Wersja {__version__} — program do obróbki zdjęć RAW"))

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Procesor:", _hint(self.system.cpu.name))
        form.addRow("Karta graficzna:", _hint(self.system.gpu.name))
        if self.system.gpu.driver:
            form.addRow("Sterownik OpenGL:", _hint(self.system.gpu.driver))
        if self.system.gpu.glsl:
            form.addRow("Wersja GLSL:", _hint(self.system.gpu.glsl))
        form.addRow("Plik ustawień:", _hint(settings_path()))
        layout.addLayout(form)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        layout.addWidget(line2)
        layout.addWidget(_hint(self._library_versions()))
        layout.addStretch(1)
        return page

    def _library_versions(self) -> str:
        entries = []
        for label, module in (
            ("rawpy", "rawpy"), ("numpy", "numpy"),
            ("OpenCV", "cv2"), ("Pillow", "PIL"),
        ):
            try:
                imported = __import__(module)
                version = getattr(imported, "__version__", "?")
            except Exception:
                version = "brak"
            entries.append(f"{label} {version}")
        try:
            from PySide6 import __version__ as pyside

            entries.append(f"PySide6 {pyside}")
        except Exception:
            pass
        return "Biblioteki:  " + "  •  ".join(entries)

    # ----------------------------------------------------- stan widżetów

    def _load_into_widgets(self) -> None:
        s = self.settings
        self.engine_buttons[s.render_engine].setChecked(True)
        self.preview_size_box.setCurrentIndex(
            max(0, self.preview_size_box.findData(s.preview_size))
        )
        self.threads_box.setValue(s.thumbnail_threads)
        self.detail_delay_box.setValue(s.detail_delay_ms)
        self.noise_delay_box.setValue(s.noise_delay_ms)
        self.preview_noise_box.setCurrentIndex(
            max(0, self.preview_noise_box.findData(s.preview_noise_quality))
        )
        self.pixel_peek_box.setValue(s.pixel_peek_zoom)
        self.navigator_box.setChecked(s.show_navigator)
        self.format_box.setCurrentIndex(max(0, self.format_box.findData(s.export_format)))
        self.quality_box.setValue(s.export_quality)
        self.max_side_box.setValue(s.export_max_side)
        self.export_noise_box.setCurrentIndex(
            max(0, self.export_noise_box.findData(s.export_noise_quality))
        )
        self.folder_edit.setText(s.export_folder)
        self.reopen_box.setChecked(s.reopen_last_folder)

    def _collect_from_widgets(self) -> Settings:
        s = self.settings.copy()
        for key, button in self.engine_buttons.items():
            if button.isChecked():
                s.render_engine = key
        s.preview_size = self.preview_size_box.currentData()
        s.thumbnail_threads = self.threads_box.value()
        s.detail_delay_ms = self.detail_delay_box.value()
        s.noise_delay_ms = self.noise_delay_box.value()
        s.preview_noise_quality = self.preview_noise_box.currentData()
        s.pixel_peek_zoom = self.pixel_peek_box.value()
        s.show_navigator = self.navigator_box.isChecked()
        s.export_format = self.format_box.currentData()
        s.export_quality = self.quality_box.value()
        s.export_max_side = self.max_side_box.value()
        s.export_noise_quality = self.export_noise_box.currentData()
        s.export_folder = self.folder_edit.text().strip()
        s.reopen_last_folder = self.reopen_box.isChecked()
        return s.normalised()

    # ------------------------------------------------------------ akcje

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Domyślny katalog eksportu", self.folder_edit.text()
        )
        if folder:
            self.folder_edit.setText(folder)

    def _restore_defaults(self) -> None:
        keep_last = self.settings.last_folder
        self.settings = Settings()
        self.settings.last_folder = keep_last
        self._load_into_widgets()

    def _on_accept(self) -> None:
        self.settings = self._collect_from_widgets()
        self.accept()

    def result_settings(self) -> Settings:
        return self.settings
