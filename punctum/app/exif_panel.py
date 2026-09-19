"""Panel metadanych: podglad wszystkich tagow i edycja tych, ktore sie da.

Jedna klasa, dwa miejsca w oknie - w Edycji siedzi w zwijanej sekcji pod
danymi zdjecia, w Mapie stoi po prawej stronie jako pelna kolumna. Obie
kopie pokazuja ten sam stan, bo obie dostaja nastawy z okna glownego.

Puste pole znaczy "nie zmieniam", a nie "skasuj tag". Kasowanie metadanych
jest nieodwracalne, wiec nie moze sie zdarzyc przez nieuwage - zdjete pole
trzeba wyczyscic osobnym przyciskiem.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.exif_edit import FIELDS, GROUPS, current_values, is_writable_format, validate


class ExifPanel(QWidget):
    """Formularz pol edytowalnych plus podglad wszystkich tagow."""

    changed = Signal(dict)  # komplet zmienionych pol
    write_requested = Signal()  # zapis do pliku zrodlowego

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: str | None = None
        self.original: dict[str, str] = {}  # co jest w pliku
        self.editors: dict[str, QWidget] = {}
        self._loading = False

        form_host = QWidget()
        form = QVBoxLayout(form_host)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        for group in GROUPS:
            label = QLabel(group.upper())
            label.setObjectName("sectionLabel")
            form.addWidget(label)
            grid = QFormLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(4)
            grid.setLabelAlignment(Qt.AlignLeft)
            grid.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for field in (f for f in FIELDS if f.group == group):
                grid.addRow(field.label, self._editor(field))
            form.addLayout(grid)

        self.problem = QLabel("")
        self.problem.setObjectName("metaLabel")
        self.problem.setWordWrap(True)
        form.addWidget(self.problem)
        form.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidget(form_host)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)

        self.all_button = QPushButton("Wszystkie tagi")
        self.all_button.setCheckable(True)
        self.all_button.setToolTip("Pokaż wszystko, co jest zapisane w pliku")
        self.all_button.toggled.connect(self._on_show_all)

        self.write_button = QPushButton("Zapisz do oryginału")
        self.write_button.setToolTip(
            "Wpisuje metadane wprost w plik ze zdjęciem — bezstratnie, tylko\n"
            "nagłówek, z zachowaniem daty pliku. Pliki RAW zostają nietknięte:\n"
            "tam metadane czekają w pliku XMP i trafią do wyeksportowanego zdjęcia."
        )
        self.write_button.clicked.connect(self.write_requested.emit)

        self.clear_button = QPushButton("Wyczyść zmiany")
        self.clear_button.setToolTip("Cofa niezapisane zmiany w tym panelu")
        self.clear_button.clicked.connect(self._on_clear)

        # Dwa rzedy, nie jeden: w kolumnie szerokosci 330 px trzeci przycisk
        # obcinal sobie napis ("apisz do oryginał").
        buttons = QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(4)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)
        top_row.addWidget(self.all_button)
        top_row.addWidget(self.clear_button)
        buttons.addLayout(top_row)
        buttons.addWidget(self.write_button)

        self.table = QWidget()
        self.table_layout = QGridLayout(self.table)
        self.table_layout.setContentsMargins(0, 0, 0, 0)
        self.table_layout.setHorizontalSpacing(10)
        self.table_layout.setVerticalSpacing(2)
        self.table_scroll = QScrollArea()
        self.table_scroll.setWidget(self.table)
        self.table_scroll.setWidgetResizable(True)
        self.table_scroll.setFrameShape(QScrollArea.NoFrame)
        self.table_scroll.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.table_scroll, 1)
        layout.addLayout(buttons)
        self.buttons = buttons

    def _editor(self, field) -> QWidget:
        """Pole formularza dobrane do rodzaju danych."""
        if field.kind == "choice":
            widget = QComboBox()
            widget.addItem("", "")
            for value, label in field.choices:
                widget.addItem(label, value)
            widget.currentIndexChanged.connect(lambda _=0: self._on_edited())
        elif field.kind == "multiline":
            widget = QPlainTextEdit()
            widget.setFixedHeight(46)
            widget.textChanged.connect(self._on_edited)
        else:
            widget = QLineEdit()
            widget.setPlaceholderText(field.hint)
            widget.textEdited.connect(lambda _="": self._on_edited())
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        widget.setToolTip(field.hint)
        self.editors[field.key] = widget
        return widget

    # ---------------------------------------------------------- odczyt

    def _value_of(self, key: str) -> str:
        widget = self.editors[key]
        if isinstance(widget, QComboBox):
            return widget.currentData() or ""
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText().strip()
        return widget.text().strip()

    def _set_value(self, key: str, text: str) -> None:
        widget = self.editors[key]
        if isinstance(widget, QComboBox):
            index = widget.findData(text)
            widget.setCurrentIndex(max(0, index))
        elif isinstance(widget, QPlainTextEdit):
            widget.setPlainText(text)
        else:
            widget.setText(text)

    def changes(self) -> dict[str, str]:
        """Pola rozniace sie od tego, co jest w pliku - tylko te zapisujemy."""
        result: dict[str, str] = {}
        for key in self.editors:
            value = self._value_of(key)
            if value and value != self.original.get(key, ""):
                result[key] = value
        return result

    # ----------------------------------------------------------- stan

    def set_photo(self, path: str | None, overrides: dict[str, str] | None) -> None:
        """Pokazuje metadane zdjecia: to, co w pliku, plus nasze zmiany."""
        self.path = path
        self._loading = True
        self.original = current_values(path) if path else {}
        overrides = overrides or {}
        for key in self.editors:
            self._set_value(key, overrides.get(key, self.original.get(key, "")))
        self._loading = False

        writable = bool(path) and is_writable_format(path)
        self.write_button.setEnabled(writable)
        if not path:
            self.problem.setText("")
        elif not writable:
            self.problem.setText(
                f"{os.path.basename(path)}: tego formatu nie zapiszemy w miejscu — "
                "metadane czekają w pliku XMP i trafią do wyeksportowanego zdjęcia."
            )
        else:
            self.problem.setText("")
        if self.all_button.isChecked():
            self._fill_table()

    def _on_edited(self) -> None:
        if self._loading:
            return
        problems = [
            f"{key}: {message}"
            for key in self.editors
            if (message := validate(key, self._value_of(key))) is not None
        ]
        self.problem.setText("  •  ".join(problems))
        if not problems:
            self.changed.emit(self.changes())

    def _on_clear(self) -> None:
        self._loading = True
        for key in self.editors:
            self._set_value(key, self.original.get(key, ""))
        self._loading = False
        self.problem.setText("")
        self.changed.emit({})

    # ------------------------------------------------ wszystkie tagi

    def _on_show_all(self, on: bool) -> None:
        self.scroll.setVisible(not on)
        self.table_scroll.setVisible(on)
        if on:
            self._fill_table()

    def _fill_table(self) -> None:
        """Pelna lista tagow, tylko do odczytu.

        Odczyt idzie z pliku dopiero przy pokazaniu tabelki - przy katalogu
        z 2000 zdjec nie ma sensu czytac wszystkich tagow kazdego zdjecia
        tylko dlatego, ze uzytkownik je przekliknal.
        """
        from ..core.exif_edit import read_all_tags

        while self.table_layout.count():
            item = self.table_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        rows = read_all_tags(self.path) if self.path else []
        if not rows:
            self.table_layout.addWidget(QLabel("Brak metadanych w pliku"), 0, 0)
            return

        for row, tag in enumerate(rows):
            name = QLabel(f"{tag.group} · {tag.name}")
            name.setObjectName("metaLabel")
            value = QLabel(tag.value)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.table_layout.addWidget(name, row, 0, Qt.AlignTop)
            self.table_layout.addWidget(value, row, 1, Qt.AlignTop)
        self.table_layout.setColumnStretch(1, 1)


# Sekcja zwijana zyje teraz w InfoPanel (app/edit_panel.py): metadane sa
# chowanym dnem sekcji z danymi zdjecia, a nie osobnym blokiem z naglowkiem.
