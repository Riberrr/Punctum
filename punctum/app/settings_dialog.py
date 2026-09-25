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
from ..przeklad import N_, jezyk, jezyki, nazwa_jezyka, t
from .podpowiedzi import podpowiedz, podpowiedz_wiersza

ENGINE_DESCRIPTIONS = {
    ENGINE_AUTO: N_("Użyj karty graficznej, jeśli jest dostępna; w razie problemu przejdź na procesor."),
    ENGINE_GPU: N_("Wymuś liczenie na karcie. Podgląd odświeża się w kilka milisekund."),
    ENGINE_CPU: N_("Wymuś liczenie na procesorze. Wolniejsze, ale niezależne od sterowników."),
}


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("metaLabel")
    label.setWordWrap(True)
    return label


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, system: SystemInfo, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Ustawienia — Punctum"))
        self.setMinimumWidth(560)
        self.settings = settings.copy()
        self.system = system

        self.tabs = QTabWidget()
        self.tabs.addTab(self._performance_tab(), t("Wydajność"))
        self.tabs.addTab(self._preview_tab(), t("Podgląd"))
        self.tabs.addTab(self._export_tab(), t("Eksport"))
        self.tabs.addTab(self._about_tab(), t("O programie"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        buttons.button(QDialogButtonBox.Save).setText(t("Zapisz"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("Anuluj"))
        buttons.button(QDialogButtonBox.RestoreDefaults).setText(t("Przywróć domyślne"))
        podpowiedz(buttons.button(QDialogButtonBox.RestoreDefaults), "ustawienia.domyslne")
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

    def show_tab(self, title: str) -> None:
        """Otwiera okno od razu na zakladce o podanym tytule (np. z menu Pomoc)."""
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == title:
                self.tabs.setCurrentIndex(index)
                return

    def _performance_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        # --- wykryty sprzet ---------------------------------------------
        hardware = QGroupBox(t("Wykryty sprzęt"))
        form = QFormLayout(hardware)
        form.setLabelAlignment(Qt.AlignRight)

        self.cpu_label = QLabel(self.system.cpu.summary)
        self.cpu_label.setWordWrap(True)
        self.gpu_label = QLabel(self.system.gpu.summary)
        self.gpu_label.setWordWrap(True)
        self.system_label = QLabel(f"{self.system.system}  •  Python {self.system.python}")

        form.addRow(t("Procesor:"), self.cpu_label)
        form.addRow(t("Karta graficzna:"), self.gpu_label)
        form.addRow(t("System:"), self.system_label)
        layout.addWidget(hardware)

        # --- wybor silnika ----------------------------------------------
        engine = QGroupBox(t("Silnik podglądu"))
        engine_layout = QVBoxLayout(engine)
        self.engine_group = QButtonGroup(self)
        self.engine_buttons: dict[str, QRadioButton] = {}

        for key in (ENGINE_AUTO, ENGINE_GPU, ENGINE_CPU):
            button = QRadioButton(
                {"auto": t("Automatycznie"), "gpu": t("Karta graficzna"), "cpu": t("Procesor")}[key]
            )
            self.engine_group.addButton(button)
            self.engine_buttons[key] = button
            podpowiedz(button, f"ustawienia.silnik_{key}")
            engine_layout.addWidget(button)
            hint = _hint(t(ENGINE_DESCRIPTIONS[key]))
            hint.setContentsMargins(22, 0, 0, 6)
            engine_layout.addWidget(hint)

        if not self.system.gpu.available:
            self.engine_buttons[ENGINE_GPU].setEnabled(False)
            engine_layout.addWidget(
                _hint(t("Karta niedostępna: {powod}",
                        powod=self.system.gpu.problem or t("brak kontekstu OpenGL")))
            )
        layout.addWidget(engine)

        # --- zasoby ------------------------------------------------------
        resources = QGroupBox(t("Zasoby"))
        resource_form = QFormLayout(resources)

        self.preview_size_box = QComboBox()
        for size in PREVIEW_SIZES:
            self.preview_size_box.addItem(f"{size} px", size)
        resource_form.addRow(t("Rozmiar podglądu:"), self.preview_size_box)
        podpowiedz_wiersza(resource_form, self.preview_size_box, "ustawienia.rozmiar_podgladu")
        resource_form.addRow("", _hint(
            t("Dłuższy bok obrazu liczonego dla widoku dopasowanego do okna. "
            "Przy powiększeniu i tak dokładany jest fragment z pełnej rozdzielczości.")
        ))

        self.threads_box = QSpinBox()
        self.threads_box.setRange(0, 32)
        self.threads_box.setSpecialValueText(t("automatycznie"))
        resource_form.addRow(t("Wątki miniatur:"), self.threads_box)
        podpowiedz_wiersza(resource_form, self.threads_box, "ustawienia.watki")
        cores = self.system.cpu.cores_logical or 4
        resource_form.addRow("", _hint(t("Zero oznacza dobór automatyczny: {n}.", n=max(2, cores - 1))))

        layout.addWidget(resources)
        layout.addStretch(1)
        return page

    def _preview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        timing = QGroupBox(t("Opóźnienia"))
        form = QFormLayout(timing)

        self.detail_delay_box = QSpinBox()
        self.detail_delay_box.setRange(0, 2000)
        self.detail_delay_box.setSingleStep(20)
        self.detail_delay_box.setSuffix(" ms")
        form.addRow(t("Doliczanie ostrego fragmentu:"), self.detail_delay_box)
        podpowiedz_wiersza(form, self.detail_delay_box, "ustawienia.opoznienie_ostrosci")
        form.addRow("", _hint(
            t("Po tym czasie od zatrzymania kadru wczytywany jest fragment "
            "w pełnej rozdzielczości.")
        ))

        self.noise_delay_box = QSpinBox()
        self.noise_delay_box.setRange(0, 5000)
        self.noise_delay_box.setSingleStep(50)
        self.noise_delay_box.setSuffix(" ms")
        form.addRow(t("Usuwanie szumu:"), self.noise_delay_box)
        podpowiedz_wiersza(form, self.noise_delay_box, "ustawienia.opoznienie_szumu")
        form.addRow("", _hint(
            t("Odszumianie liczy procesor, więc czeka, aż przestaniesz ruszać suwakiem.")
        ))
        layout.addWidget(timing)

        quality = QGroupBox(t("Jakość"))
        quality_form = QFormLayout(quality)

        self.preview_noise_box = QComboBox()
        for key, label in NOISE_QUALITY_LABELS.items():
            self.preview_noise_box.addItem(t(label), key)
        quality_form.addRow(t("Odszumianie podglądu:"), self.preview_noise_box)
        podpowiedz_wiersza(quality_form, self.preview_noise_box, "ustawienia.odszumianie_podgladu")

        self.pixel_peek_box = QDoubleSpinBox()
        self.pixel_peek_box.setRange(1.0, 16.0)
        self.pixel_peek_box.setSingleStep(0.5)
        self.pixel_peek_box.setSuffix(" ×")
        quality_form.addRow(t("Podgląd pikseli od:"), self.pixel_peek_box)
        podpowiedz_wiersza(quality_form, self.pixel_peek_box, "ustawienia.podglad_pikseli")
        quality_form.addRow("", _hint(
            t("Powyżej tego powiększenia obraz skalowany jest najbliższym sąsiadem, "
            "żeby było widać prawdziwe piksele zamiast interpolacji.")
        ))

        self.navigator_box = QCheckBox(t("Pokazuj nawigator w lewym panelu"))
        quality_form.addRow("", self.navigator_box)
        podpowiedz(self.navigator_box, "ustawienia.nawigator")
        self.tooltips_box = QCheckBox(t("Pokazuj podpowiedzi"))
        podpowiedz(self.tooltips_box, "ustawienia.podpowiedzi")
        quality_form.addRow("", self.tooltips_box)
        self.tooltip_delay_box = QSpinBox()
        self.tooltip_delay_box.setRange(0, 5000)
        self.tooltip_delay_box.setSingleStep(100)
        self.tooltip_delay_box.setSuffix(" ms")
        quality_form.addRow(t("Opóźnienie podpowiedzi:"), self.tooltip_delay_box)
        podpowiedz_wiersza(quality_form, self.tooltip_delay_box, "ustawienia.opoznienie_podpowiedzi")
        # przy wylaczonych dymkach opoznienie nic nie znaczy
        self.tooltips_box.toggled.connect(self.tooltip_delay_box.setEnabled)
        layout.addWidget(quality)

        wheel = QGroupBox(t("Kółko myszy nad suwakami"))
        wheel_form = QFormLayout(wheel)

        self.wheel_lockout_box = QSpinBox()
        self.wheel_lockout_box.setRange(0, 3000)
        self.wheel_lockout_box.setSingleStep(50)
        self.wheel_lockout_box.setSuffix(" ms")
        self.wheel_lockout_box.setSpecialValueText(t("bez blokady"))
        wheel_form.addRow(t("Blokada po przewinięciu:"), self.wheel_lockout_box)
        podpowiedz_wiersza(wheel_form, self.wheel_lockout_box, "ustawienia.blokada_kolka")
        wheel_form.addRow("", _hint(
            t("Po przewinięciu listy suwaki przez ten czas nie reagują na kółko. "
            "Dzięki temu przewijanie panelu nie zmienia przypadkiem parametrów. "
            "Zero wyłącza zabezpieczenie.")
        ))

        self.wheel_dwell_box = QSpinBox()
        self.wheel_dwell_box.setRange(0, 3000)
        self.wheel_dwell_box.setSingleStep(20)
        self.wheel_dwell_box.setSuffix(" ms")
        wheel_form.addRow(t("Wymagane zatrzymanie:"), self.wheel_dwell_box)
        podpowiedz_wiersza(wheel_form, self.wheel_dwell_box, "ustawienia.zatrzymanie_kolka")
        wheel_form.addRow("", _hint(
            t("Kursor musi postać nad suwakiem tyle czasu, zanim kółko zacznie "
            "go zmieniać. Chroni przed suwakiem, który dopiero podjechał pod "
            "nieruchomy kursor.")
        ))
        layout.addWidget(wheel)

        layout.addStretch(1)
        return page

    def _export_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        output = QGroupBox(t("Plik wynikowy"))
        form = QFormLayout(output)

        self.format_box = QComboBox()
        for extension, label in ((".jpg", "JPEG"), (".png", "PNG"), (".tif", "TIFF")):
            self.format_box.addItem(label, extension)
        form.addRow(t("Format:"), self.format_box)
        podpowiedz_wiersza(form, self.format_box, "ustawienia.format")

        self.quality_box = QSpinBox()
        self.quality_box.setRange(50, 100)
        form.addRow(t("Jakość JPEG:"), self.quality_box)
        podpowiedz_wiersza(form, self.quality_box, "ustawienia.jakosc_jpeg")

        self.max_side_box = QSpinBox()
        self.max_side_box.setRange(0, 20000)
        self.max_side_box.setSingleStep(100)
        self.max_side_box.setSpecialValueText(t("pełna rozdzielczość"))
        self.max_side_box.setSuffix(" px")
        form.addRow(t("Dłuższy bok:"), self.max_side_box)
        podpowiedz_wiersza(form, self.max_side_box, "ustawienia.dluzszy_bok")

        self.export_noise_box = QComboBox()
        for key, label in NOISE_QUALITY_LABELS.items():
            self.export_noise_box.addItem(t(label), key)
        form.addRow(t("Odszumianie:"), self.export_noise_box)
        podpowiedz_wiersza(form, self.export_noise_box, "ustawienia.odszumianie_eksportu")
        form.addRow("", _hint(
            t("Przy eksporcie warto wybrać wariant dokładny — liczy się raz, "
            "a różnica jest widoczna w pełnej rozdzielczości.")
        ))
        layout.addWidget(output)

        destination = QGroupBox(t("Katalog docelowy"))
        destination_layout = QHBoxLayout(destination)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(t("pytaj przy każdym eksporcie"))
        browse = QPushButton(t("Wybierz…"))
        browse.clicked.connect(self._choose_folder)
        podpowiedz(browse, "ustawienia.wybierz_katalog")
        podpowiedz(self.folder_edit, "ustawienia.katalog")
        destination_layout.addWidget(self.folder_edit, 1)
        destination_layout.addWidget(browse)
        layout.addWidget(destination)

        authorship = QGroupBox(t("Autorstwo"))
        authorship_form = QFormLayout(authorship)
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText(t("Imię Nazwisko"))
        authorship_form.addRow(t("Autor:"), self.author_edit)
        podpowiedz_wiersza(authorship_form, self.author_edit, "ustawienia.autor")
        self.copyright_edit = QLineEdit()
        self.copyright_edit.setPlaceholderText(t("np. © 2026 Imię Nazwisko"))
        authorship_form.addRow(t("Prawa autorskie:"), self.copyright_edit)
        podpowiedz_wiersza(authorship_form, self.copyright_edit, "ustawienia.prawa")
        authorship_form.addRow("", _hint(
            t("Wartości podpowiadane w oknie eksportu. Czy trafią do plików, "
            "decydujesz tam, przy każdym eksporcie.")
        ))
        layout.addWidget(authorship)

        general = QGroupBox(t("Ogólne"))
        general_layout = QVBoxLayout(general)
        language_form = QFormLayout()
        self.language_box = QComboBox()
        # Nazwa jezyka w nim samym: tak odnajdzie swoj jezyk ktos, kto nie
        # zna jezyka, w ktorym jest akurat program.
        for kod in jezyki():
            self.language_box.addItem(nazwa_jezyka(kod), kod)
        language_form.addRow(t("Język:"), self.language_box)
        podpowiedz_wiersza(language_form, self.language_box, "ustawienia.jezyk")
        general_layout.addLayout(language_form)
        general_layout.addWidget(_hint(t("Nowy język obowiązuje od ponownego uruchomienia programu.")))
        self.reopen_box = QCheckBox(t("Otwieraj ostatnio używany folder przy starcie"))
        podpowiedz(self.reopen_box, "ustawienia.ostatni_folder")
        general_layout.addWidget(self.reopen_box)
        self.store_edits_box = QCheckBox(t("Zapamiętuj korekty obok zdjęć (pliki XMP)"))
        podpowiedz(self.store_edits_box, "ustawienia.xmp")
        general_layout.addWidget(self.store_edits_box)
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
        layout.addWidget(_hint(t("Wersja {wersja} — edytor zdjęć RAW i JPEG", wersja=__version__)))

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow(t("Procesor:"), _hint(self.system.cpu.name))
        form.addRow(t("Karta graficzna:"), _hint(t(self.system.gpu.name)))
        if self.system.gpu.driver:
            form.addRow(t("Sterownik OpenGL:"), _hint(self.system.gpu.driver))
        if self.system.gpu.glsl:
            form.addRow(t("Wersja GLSL:"), _hint(self.system.gpu.glsl))
        form.addRow(t("Plik ustawień:"), _hint(settings_path()))
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
                version = t("brak")
            entries.append(f"{label} {version}")
        try:
            from PySide6 import __version__ as pyside

            entries.append(f"PySide6 {pyside}")
        except Exception:
            pass
        return t("Biblioteki:  {lista}", lista="  •  ".join(entries))

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
        self.tooltips_box.setChecked(s.show_tooltips)
        self.tooltip_delay_box.setValue(s.tooltip_delay_ms)
        self.tooltip_delay_box.setEnabled(s.show_tooltips)
        self.wheel_lockout_box.setValue(s.wheel_lockout_ms)
        self.wheel_dwell_box.setValue(s.wheel_dwell_ms)
        self.format_box.setCurrentIndex(max(0, self.format_box.findData(s.export_format)))
        self.quality_box.setValue(s.export_quality)
        self.max_side_box.setValue(s.export_max_side)
        self.export_noise_box.setCurrentIndex(
            max(0, self.export_noise_box.findData(s.export_noise_quality))
        )
        self.folder_edit.setText(s.export_folder)
        self.author_edit.setText(s.export_author)
        self.copyright_edit.setText(s.export_copyright)
        # Pusty w ustawieniach = jezyk dobrany przy starcie; pokazujemy ten, ktory dziala.
        self.language_box.setCurrentIndex(
            max(0, self.language_box.findData(s.language or jezyk())))
        self.reopen_box.setChecked(s.reopen_last_folder)
        self.store_edits_box.setChecked(s.store_edits)

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
        s.show_tooltips = self.tooltips_box.isChecked()
        s.tooltip_delay_ms = self.tooltip_delay_box.value()
        s.wheel_lockout_ms = self.wheel_lockout_box.value()
        s.wheel_dwell_ms = self.wheel_dwell_box.value()
        s.export_format = self.format_box.currentData()
        s.export_quality = self.quality_box.value()
        s.export_max_side = self.max_side_box.value()
        s.export_noise_quality = self.export_noise_box.currentData()
        s.export_folder = self.folder_edit.text().strip()
        s.export_author = self.author_edit.text().strip()
        s.export_copyright = self.copyright_edit.text().strip()
        s.language = self.language_box.currentData()
        s.reopen_last_folder = self.reopen_box.isChecked()
        s.store_edits = self.store_edits_box.isChecked()
        return s.normalised()

    # ------------------------------------------------------------ akcje

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, t("Domyślny katalog eksportu"), self.folder_edit.text()
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
