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
    DEFAULT_SUBFOLDER,
    EXISTING_LABELS,
    FORMAT_LABELS,
    NAMING_CUSTOM,
    NAMING_ORIGINAL,
    ExportOptions,
)
from ..core.settings import NOISE_QUALITY_LABELS
from .podpowiedzi import podpowiedz, podpowiedz_wiersza
from ..przeklad import mnoga, t


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("metaLabel")
    label.setWordWrap(True)
    return label


class ExportDialog(QDialog):
    """Pracuje na kopii nastaw - "Anuluj" nie zostawia polowy zmian."""

    def __init__(self, options: ExportOptions, sources: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Eksportuj zdjęcia"))
        self.setMinimumWidth(960)
        self.options = ExportOptions(**vars(options))
        self.sources = sources

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        count = len(sources)
        self.headline = QLabel(
            mnoga(count, "Do wyeksportowania: {n} zdjęcie|Do wyeksportowania: {n} zdjęcia|"
            "Do wyeksportowania: {n} zdjęć")
        )
        self.headline.setObjectName("cameraLabel")
        layout.addWidget(self.headline)
        self.edited_hint = _hint("")
        self.edited_hint.hide()
        layout.addWidget(self.edited_hint)

        # Dwie kolumny: po dolozeniu metadanych okno w jednej kolumnie mialo
        # ponad 900 px wysokosci, a przy skalowaniu 125 % ekran Full HD ma
        # ich do dyspozycji mniej - przyciski wypadalyby pod pasek zadan.
        columns = QHBoxLayout()
        columns.setSpacing(10)
        left = QVBoxLayout()
        left.addWidget(self._location_group())
        left.addWidget(self._naming_group())
        left.addStretch(1)
        right = QVBoxLayout()
        right.addWidget(self._format_group())
        right.addWidget(self._metadata_group())
        right.addStretch(1)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        layout.addLayout(columns)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("settingsLabel")
        layout.addWidget(self.preview_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.export_button = buttons.button(QDialogButtonBox.Ok)
        self.export_button.setText(t("Eksportuj"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("Anuluj"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_into_widgets()
        self._refresh_preview()

    # ------------------------------------------------------------ sekcje

    def _location_group(self) -> QGroupBox:
        group = QGroupBox(t("Lokalizacja"))
        form = QFormLayout(group)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(t("wybierz katalog docelowy"))
        self.folder_edit.textChanged.connect(self._refresh_preview)
        browse = QPushButton(t("Wybierz…"))
        browse.clicked.connect(self._choose_folder)
        row_layout.addWidget(self.folder_edit, 1)
        row_layout.addWidget(browse)
        form.addRow(t("Katalog:"), row)
        podpowiedz(browse, "eksport.wybierz_katalog")
        podpowiedz(self.folder_edit, "eksport.katalog", etykieta=form.labelForField(row))

        subfolder_row = QWidget()
        subfolder_layout = QHBoxLayout(subfolder_row)
        subfolder_layout.setContentsMargins(0, 0, 0, 0)
        self.subfolder_box = QCheckBox(t("Umieść w podfolderze:"))
        self.subfolder_box.toggled.connect(self._on_subfolder_toggled)
        self.subfolder_edit = QLineEdit()
        self.subfolder_edit.textChanged.connect(self._refresh_preview)
        subfolder_layout.addWidget(self.subfolder_box)
        subfolder_layout.addWidget(self.subfolder_edit, 1)
        form.addRow("", subfolder_row)
        podpowiedz(self.subfolder_box, "eksport.podfolder")
        podpowiedz(self.subfolder_edit, "eksport.podfolder")

        self.existing_box = QComboBox()
        for key, label in EXISTING_LABELS.items():
            self.existing_box.addItem(t(label), key)
        form.addRow(t("Istniejące pliki:"), self.existing_box)
        podpowiedz_wiersza(form, self.existing_box, "eksport.istniejace")
        form.addRow("", _hint(
            t("Kolizje nazw sprawdzamy przed rozpoczęciem, więc pytanie pojawi się "
            "raz — eksport nie zatrzyma się w połowie.")
        ))
        return group

    def _naming_group(self) -> QGroupBox:
        group = QGroupBox(t("Nazwa pliku"))
        layout = QVBoxLayout(group)

        self.naming_group = QButtonGroup(self)
        self.original_radio = QRadioButton(t("Zachowaj oryginalną nazwę"))
        self.custom_radio = QRadioButton(t("Nadaj nazwę z numeratorem"))
        podpowiedz(self.original_radio, "eksport.nazwa_oryginalna")
        podpowiedz(self.custom_radio, "eksport.nazwa_numer")
        for button in (self.original_radio, self.custom_radio):
            self.naming_group.addButton(button)
            layout.addWidget(button)
        self.naming_group.buttonToggled.connect(self._on_naming_toggled)

        self.custom_row = QWidget()
        form = QFormLayout(self.custom_row)
        form.setContentsMargins(22, 2, 0, 0)
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText(t("np. Wakacje"))
        self.custom_edit.textChanged.connect(self._refresh_preview)
        form.addRow(t("Tekst:"), self.custom_edit)
        podpowiedz_wiersza(form, self.custom_edit, "eksport.tekst")

        self.start_number_box = QSpinBox()
        self.start_number_box.setRange(0, 999999)
        self.start_number_box.valueChanged.connect(self._refresh_preview)
        form.addRow(t("Numer początkowy:"), self.start_number_box)
        podpowiedz_wiersza(form, self.start_number_box, "eksport.numer_poczatkowy")

        self.digits_box = QSpinBox()
        self.digits_box.setRange(1, 8)
        self.digits_box.valueChanged.connect(self._refresh_preview)
        form.addRow(t("Cyfr w numerze:"), self.digits_box)
        podpowiedz_wiersza(form, self.digits_box, "eksport.cyfry")
        layout.addWidget(self.custom_row)
        return group

    def _format_group(self) -> QGroupBox:
        group = QGroupBox(t("Format i jakość"))
        form = QFormLayout(group)

        self.format_box = QComboBox()
        for extension, label in FORMAT_LABELS.items():
            self.format_box.addItem(label, extension)
        self.format_box.currentIndexChanged.connect(self._on_format_changed)
        form.addRow(t("Format:"), self.format_box)
        podpowiedz_wiersza(form, self.format_box, "eksport.format")

        self.quality_box = QSpinBox()
        self.quality_box.setRange(50, 100)
        form.addRow(t("Jakość JPEG:"), self.quality_box)
        podpowiedz_wiersza(form, self.quality_box, "eksport.jakosc_jpeg")

        self.max_side_box = QSpinBox()
        self.max_side_box.setRange(0, 20000)
        self.max_side_box.setSingleStep(100)
        self.max_side_box.setSpecialValueText(t("pełna rozdzielczość"))
        self.max_side_box.setSuffix(" px")
        form.addRow(t("Dłuższy bok:"), self.max_side_box)
        podpowiedz_wiersza(form, self.max_side_box, "eksport.dluzszy_bok")

        self.noise_box = QComboBox()
        for key, label in NOISE_QUALITY_LABELS.items():
            self.noise_box.addItem(t(label), key)
        form.addRow(t("Odszumianie:"), self.noise_box)
        podpowiedz_wiersza(form, self.noise_box, "eksport.odszumianie")
        return group

    def _metadata_group(self) -> QGroupBox:
        group = QGroupBox(t("Metadane"))
        form = QFormLayout(group)

        # Pole wyboru stoi w miejscu etykiety: wartosc przychodzi wypelniona
        # z ustawien, a zaznaczenie wlacza pole obok - mozna ja wtedy zmienic
        # na ten jeden eksport.
        self.author_box = QCheckBox(t("Autor:"))
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText(t("domyślnego ustawisz w Ustawieniach ▸ Eksport"))
        self.author_box.toggled.connect(
            lambda on: self._on_field_toggled(self.author_edit, on)
        )
        form.addRow(self.author_box, self.author_edit)
        podpowiedz(self.author_box, "eksport.autor")
        podpowiedz(self.author_edit, "eksport.autor")

        self.copyright_box = QCheckBox(t("Prawa autorskie:"))
        self.copyright_edit = QLineEdit()
        self.copyright_edit.setPlaceholderText(t("np. © 2026 Imię Nazwisko"))
        self.copyright_box.toggled.connect(
            lambda on: self._on_field_toggled(self.copyright_edit, on)
        )
        form.addRow(self.copyright_box, self.copyright_edit)
        podpowiedz(self.copyright_box, "eksport.prawa")
        podpowiedz(self.copyright_edit, "eksport.prawa")

        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText(t("oddzielone średnikiem, np. Wakacje 2026; Tatry"))
        form.addRow(t("Słowa kluczowe:"), self.keywords_edit)
        podpowiedz_wiersza(form, self.keywords_edit, "eksport.slowa")
        self.subject_edit = QLineEdit()
        form.addRow(t("Temat:"), self.subject_edit)
        podpowiedz_wiersza(form, self.subject_edit, "eksport.temat")
        self.comment_edit = QLineEdit()
        form.addRow(t("Komentarz:"), self.comment_edit)
        podpowiedz_wiersza(form, self.comment_edit, "eksport.komentarz")
        form.addRow("", _hint(
            t("Wpisane tu pola zastępują te przy zdjęciach, a słowa kluczowe "
            "dopisują się do słów zdjęcia. Data, aparat, naświetlenie "
            "i lokalizacja trafiają do pliku zawsze.")
        ))
        return group

    # ------------------------------------------------------------- stan

    def _load_into_widgets(self) -> None:
        o = self.options
        self.folder_edit.setText(o.folder)
        self.subfolder_box.setChecked(o.use_subfolder)
        self.subfolder_edit.setText(t(o.subfolder) if o.subfolder == DEFAULT_SUBFOLDER else o.subfolder)
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
        self.author_box.setChecked(o.add_author)
        self.author_edit.setText(o.author)
        self.author_edit.setEnabled(o.add_author)
        self.copyright_box.setChecked(o.add_copyright)
        self.copyright_edit.setText(o.copyright)
        self.copyright_edit.setEnabled(o.add_copyright)
        self.keywords_edit.setText(o.keywords)
        self.subject_edit.setText(o.subject)
        self.comment_edit.setText(o.comment)
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
        o.add_author = self.author_box.isChecked()
        o.author = self.author_edit.text().strip()
        o.add_copyright = self.copyright_box.isChecked()
        o.copyright = self.copyright_edit.text().strip()
        o.keywords = self.keywords_edit.text().strip()
        o.subject = self.subject_edit.text().strip()
        o.comment = self.comment_edit.text().strip()
        return o

    # ---------------------------------------------------------- reakcje

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, t("Katalog docelowy"), self.folder_edit.text()
        )
        if folder:
            self.folder_edit.setText(folder)

    def _on_field_toggled(self, edit: QLineEdit, on: bool) -> None:
        edit.setEnabled(on)
        if on and self.isVisible():
            # Zaznaczenie zwykle znaczy "chce to zmienic" - kursor od razu w polu.
            edit.setFocus()
            edit.selectAll()

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
        self.preview_label.setText(t("Pierwszy plik:  {plik}", plik=target))

        ready = bool(options.folder) and os.path.isdir(options.folder)
        if not options.folder:
            self.preview_label.setText(t("Wskaż katalog docelowy."))
        elif not os.path.isdir(options.folder):
            self.preview_label.setText(t("Katalog nie istnieje:  {katalog}", katalog=options.folder))
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
            t("Korekty zapisane dla {e} z {n} zdjęć. Pozostałe zostaną "
              "wyeksportowane bez zmian, tak jak wyszły z aparatu.", e=edited, n=total)
        )
        self.edited_hint.show()

    def _on_accept(self) -> None:
        self.options = self.collect()
        self.accept()
