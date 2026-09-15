"""Okno eksportu: gdzie, pod jaka nazwa i w jakiej jakosci zapisac zdjecia."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.export import (
    EXISTING_LABELS,
    FORMAT_LABELS,
    NAMING_CUSTOM,
    NAMING_ORIGINAL,
    ExportOptions,
)
from ..core.settings import NOISE_QUALITY_LABELS


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("metaLabel")
    label.setWordWrap(True)
    return label


class ExportDialog(QDialog):
    """Pracuje na kopii nastaw - "Anuluj" nie zostawia polowy zmian."""

    def __init__(self, options: ExportOptions, sources: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Eksportuj zdjęcia")
        self.setMinimumWidth(560)
        self.options = ExportOptions(**vars(options))
        self.sources = sources

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        count = len(sources)
        self.headline = QLabel(
            f"Do wyeksportowania: {count} "
            + ("zdjęcie" if count == 1 else "zdjęcia" if 2 <= count <= 4 else "zdjęć")
        )
        self.headline.setObjectName("cameraLabel")
        layout.addWidget(self.headline)
        self.edited_hint = _hint("")
        self.edited_hint.hide()
        layout.addWidget(self.edited_hint)

        layout.addWidget(self._location_group())
        layout.addWidget(self._naming_group())
        layout.addWidget(self._format_group())

        self.preview_label = QLabel()
        self.preview_label.setObjectName("settingsLabel")
        layout.addWidget(self.preview_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.export_button = buttons.button(QDialogButtonBox.Ok)
        self.export_button.setText("Eksportuj")
        buttons.button(QDialogButtonBox.Cancel).setText("Anuluj")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_into_widgets()
        self._refresh_preview()

    # ------------------------------------------------------------ sekcje

    def _location_group(self) -> QGroupBox:
        group = QGroupBox("Lokalizacja")
        form = QFormLayout(group)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("wybierz katalog docelowy")
        self.folder_edit.textChanged.connect(self._refresh_preview)
        browse = QPushButton("Wybierz…")
        browse.clicked.connect(self._choose_folder)
        row_layout.addWidget(self.folder_edit, 1)
        row_layout.addWidget(browse)
        form.addRow("Katalog:", row)

        subfolder_row = QWidget()
        subfolder_layout = QHBoxLayout(subfolder_row)
        subfolder_layout.setContentsMargins(0, 0, 0, 0)
        self.subfolder_box = QCheckBox("Umieść w podfolderze:")
        self.subfolder_box.toggled.connect(self._on_subfolder_toggled)
        self.subfolder_edit = QLineEdit()
        self.subfolder_edit.textChanged.connect(self._refresh_preview)
        subfolder_layout.addWidget(self.subfolder_box)
        subfolder_layout.addWidget(self.subfolder_edit, 1)
        form.addRow("", subfolder_row)

        self.existing_box = QComboBox()
        for key, label in EXISTING_LABELS.items():
            self.existing_box.addItem(label, key)
        form.addRow("Istniejące pliki:", self.existing_box)
        form.addRow("", _hint(
            "Kolizje nazw sprawdzamy przed rozpoczęciem, więc pytanie pojawi się "
            "raz — eksport nie zatrzyma się w połowie."
        ))
        return group

    def _naming_group(self) -> QGroupBox:
        group = QGroupBox("Nazwa pliku")
        layout = QVBoxLayout(group)

        self.naming_group = QButtonGroup(self)
        self.original_radio = QRadioButton("Zachowaj oryginalną nazwę")
        self.custom_radio = QRadioButton("Nadaj nazwę z numeratorem")
        for button in (self.original_radio, self.custom_radio):
            self.naming_group.addButton(button)
            layout.addWidget(button)
        self.naming_group.buttonToggled.connect(self._on_naming_toggled)

        self.custom_row = QWidget()
        form = QFormLayout(self.custom_row)
        form.setContentsMargins(22, 2, 0, 0)
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("np. Wakacje")
        self.custom_edit.textChanged.connect(self._refresh_preview)
        form.addRow("Tekst:", self.custom_edit)

        self.start_number_box = QSpinBox()
        self.start_number_box.setRange(0, 999999)
        self.start_number_box.valueChanged.connect(self._refresh_preview)
        form.addRow("Numer początkowy:", self.start_number_box)

        self.digits_box = QSpinBox()
        self.digits_box.setRange(1, 8)
        self.digits_box.valueChanged.connect(self._refresh_preview)
        form.addRow("Cyfr w numerze:", self.digits_box)
        layout.addWidget(self.custom_row)
        return group

    def _format_group(self) -> QGroupBox:
        group = QGroupBox("Format i jakość")
        form = QFormLayout(group)

        self.format_box = QComboBox()
        for extension, label in FORMAT_LABELS.items():
            self.format_box.addItem(label, extension)
        self.format_box.currentIndexChanged.connect(self._on_format_changed)
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

        self.noise_box = QComboBox()
        for key, label in NOISE_QUALITY_LABELS.items():
            self.noise_box.addItem(label, key)
        form.addRow("Odszumianie:", self.noise_box)
        return group

    # ------------------------------------------------------------- stan

    def _load_into_widgets(self) -> None:
        o = self.options
        self.folder_edit.setText(o.folder)
        self.subfolder_box.setChecked(o.use_subfolder)
        self.subfolder_edit.setText(o.subfolder)
        self.subfolder_edit.setEnabled(o.use_subfolder)
        self.existing_box.setCurrentIndex(max(0, self.existing_box.findData(o.on_existing)))
        (self.custom_radio if o.naming == NAMING_CUSTOM else self.original_radio).setChecked(True)
        self.custom_edit.setText(o.custom_name)
        self.start_number_box.setValue(o.start_number)
        self.digits_box.setValue(o.number_digits)
        self.custom_row.setEnabled(o.naming == NAMING_CUSTOM)
        self.format_box.setCurrentIndex(max(0, self.format_box.findData(o.file_format)))
        self.quality_box.setValue(o.quality)
        self.max_side_box.setValue(o.max_side)
        self.noise_box.setCurrentIndex(max(0, self.noise_box.findData(o.noise_quality)))
        self._on_format_changed()

    def collect(self) -> ExportOptions:
        o = ExportOptions(**vars(self.options))
        o.folder = self.folder_edit.text().strip()
        o.use_subfolder = self.subfolder_box.isChecked()
        o.subfolder = self.subfolder_edit.text().strip()
        o.on_existing = self.existing_box.currentData()
        o.naming = NAMING_CUSTOM if self.custom_radio.isChecked() else NAMING_ORIGINAL
        o.custom_name = self.custom_edit.text().strip()
        o.start_number = self.start_number_box.value()
        o.number_digits = self.digits_box.value()
        o.file_format = self.format_box.currentData()
        o.quality = self.quality_box.value()
        o.max_side = self.max_side_box.value()
        o.noise_quality = self.noise_box.currentData()
        return o

    # ---------------------------------------------------------- reakcje

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Katalog docelowy", self.folder_edit.text()
        )
        if folder:
            self.folder_edit.setText(folder)

    def _on_subfolder_toggled(self, checked: bool) -> None:
        self.subfolder_edit.setEnabled(checked)
        self._refresh_preview()

    def _on_naming_toggled(self) -> None:
        self.custom_row.setEnabled(self.custom_radio.isChecked())
        self._refresh_preview()

    def _on_format_changed(self) -> None:
        is_jpeg = self.format_box.currentData() == ".jpg"
        self.quality_box.setEnabled(is_jpeg)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """Pokazuje pelna sciezke pierwszego pliku - najprostszy sposob, zeby
        uzytkownik od razu zobaczyl skutek wszystkich nastaw naraz."""
        options = self.collect()
        sample = self.sources[0] if self.sources else "P1170926.RW2"
        target = os.path.join(options.target_folder(), options.file_name(sample, 0))
        self.preview_label.setText(f"Pierwszy plik:  {target}")

        ready = bool(options.folder) and os.path.isdir(options.folder)
        if not options.folder:
            self.preview_label.setText("Wskaż katalog docelowy.")
        elif not os.path.isdir(options.folder):
            self.preview_label.setText(f"Katalog nie istnieje:  {options.folder}")
        self.export_button.setEnabled(ready and bool(self.sources))

    def set_edited_count(self, edited: int) -> None:
        """Ostrzega, ze czesc zaznaczonych zdjec nie ma jeszcze korekt.

        Program pamieta nastawy tylko dla zdjec, ktore byly otwarte. Reszta
        wyjdzie taka, jaka zapisal aparat - lepiej powiedziec to wprost, niz
        pozwolic uzytkownikowi odkryc to po kwadransie liczenia.
        """
        total = len(self.sources)
        if edited >= total or total <= 1:
            self.edited_hint.hide()
            return
        self.edited_hint.setText(
            f"Korekty zapisane dla {edited} z {total} zdjęć. Pozostałe zostaną "
            "wyeksportowane bez zmian, tak jak wyszły z aparatu."
        )
        self.edited_hint.show()

    def _on_accept(self) -> None:
        self.options = self.collect()
        self.accept()
