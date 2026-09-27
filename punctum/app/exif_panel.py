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

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.exif_edit import FIELDS, GROUPS, current_values, is_writable_format, validate
from .podpowiedzi import podpowiedz, podpowiedz_wiersza
from .style import ikona
from ..przeklad import t


class ExifPanel(QWidget):
    """Formularz pol edytowalnych plus podglad wszystkich tagow."""

    changed = Signal(dict)  # komplet zmienionych pol
    write_requested = Signal()  # zapis do pliku zrodlowego

    def __init__(self, parent=None, przewijany: bool = True, zwarty: bool = False):
        super().__init__(parent)
        self.path: str | None = None
        self.original: dict[str, str] = {}  # co jest w pliku
        self.editors: dict[str, QWidget] = {}
        self.wiersze: dict[str, _WierszPola] = {}  # tylko w trybie zwartym
        self._edytowany: str | None = None
        self._przed_edycja = ""
        self._loading = False

        form_host = QWidget()
        form = QVBoxLayout(form_host)
        # Margines od prawej: pola konczyly sie tuz przy pasku przewijania
        # i kolumna wygladala na obcieta przy samej krawedzi okna.
        form.setContentsMargins(0, 2, 10, 2)
        form.setSpacing(2 if zwarty else 8)

        for group in GROUPS:
            label = QLabel(t(group).upper())
            label.setObjectName("sectionLabel")
            form.addWidget(label)
            if zwarty:
                for field in (f for f in FIELDS if f.group == group):
                    editor = self._editor(field)
                    editor.installEventFilter(self)
                    if isinstance(editor, QComboBox):
                        editor.activated.connect(
                            lambda _=0, k=field.key: self._edytowany == k and self._zatwierdz(k, 0)
                        )
                    wiersz = _WierszPola(field.key, t(field.label), editor, self)
                    podpowiedz(wiersz.etykieta, f"exif.{field.key}")
                    podpowiedz(editor, f"exif.{field.key}")
                    self.wiersze[field.key] = wiersz
                    form.addWidget(wiersz)
                form.addSpacing(6)
                continue
            grid = QFormLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(4)
            grid.setLabelAlignment(Qt.AlignLeft)
            grid.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            # Waskiej kolumnie wolno zlamac wiersz, zamiast rozpychac panel.
            grid.setRowWrapPolicy(QFormLayout.WrapLongRows)
            for field in (f for f in FIELDS if f.group == group):
                editor = self._editor(field)
                grid.addRow(t(field.label), editor)
                podpowiedz_wiersza(grid, editor, f"exif.{field.key}")
            form.addLayout(grid)

        self.problem = QLabel("")
        self.problem.setObjectName("metaLabel")
        self.problem.setWordWrap(True)
        form.addWidget(self.problem)
        form.addStretch(1)
        if self.wiersze:
            # Wspolna kolumna etykiet, zeby wartosci staly w jednej linii.
            szer = max(w.etykieta.sizeHint().width() for w in self.wiersze.values())
            for wiersz in self.wiersze.values():
                wiersz.etykieta.setFixedWidth(szer)

        self.pola_box = self._obudowa(form_host, przewijany)

        self.all_button = QPushButton(t("Wszystkie tagi"))
        self.all_button.setCheckable(True)
        podpowiedz(self.all_button, "exif.wszystkie_tagi")
        self.all_button.toggled.connect(self._on_show_all)

        self.write_button = QPushButton(t("Zapisz do oryginału"))
        podpowiedz(self.write_button, "exif.zapisz_oryginal")
        self.write_button.clicked.connect(self.write_requested.emit)

        self.clear_button = QPushButton(t("Wyczyść zmiany"))
        podpowiedz(self.clear_button, "exif.wyczysc")
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
        self.table_layout.setContentsMargins(0, 2, 10, 2)
        self.table_layout.setHorizontalSpacing(10)
        self.table_layout.setVerticalSpacing(2)
        self.tabela_box = self._obudowa(self.table, przewijany)
        self.tabela_box.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.pola_box, 1)
        layout.addWidget(self.tabela_box, 1)
        layout.addLayout(buttons)
        self.buttons = buttons

    @staticmethod
    def _obudowa(tresc: QWidget, przewijany: bool) -> QWidget:
        """W Mapie panel jest pelna kolumna i przewija sie sam. W Edycji
        siedzi w sekcji przewijanego panelu: drugi pasek wewnatrz pierwszego
        sciskal pola do kilku wierszy (punkt 30), wiec tam bez obudowy."""
        if przewijany:
            box = QScrollArea()
            box.setWidget(tresc)
            box.setWidgetResizable(True)
            box.setFrameShape(QScrollArea.NoFrame)
            pion = QSizePolicy.Expanding
        else:
            box = tresc
            pion = QSizePolicy.Preferred
        # Panel nie ma prawa poszerzac kolumny, w ktorej stoi: w Edycji
        # rozwiniecie metadanych rozpychalo caly prawy panel, a razem z nim
        # przesuwalo podglad zdjecia.
        box.setSizePolicy(QSizePolicy.Ignored, pion)
        box.setMinimumWidth(0)
        return box

    def _editor(self, field) -> QWidget:
        """Pole formularza dobrane do rodzaju danych."""
        if field.kind == "choice":
            widget = QComboBox()
            widget.addItem("", "")
            for value, label in ((v, t(opis)) for v, opis in field.choices):
                widget.addItem(label, value)
            widget.currentIndexChanged.connect(lambda _=0: self._on_edited())
        elif field.kind == "multiline":
            widget = QPlainTextEdit()
            widget.setFixedHeight(46)
            widget.textChanged.connect(self._on_edited)
        else:
            widget = QLineEdit()
            widget.setPlaceholderText(t(field.hint))
            widget.textEdited.connect(lambda _="": self._on_edited())
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
        if self._edytowany is not None:
            # Wpisana wartosc juz poszla do nastaw (na zywo), wiec przy zmianie
            # zdjecia wystarczy zamknac edytor.
            self.wiersze[self._edytowany].set_edycja(False)
            self._edytowany = None
        self._loading = True
        self.original = current_values(path) if path else {}
        overrides = overrides or {}
        for key in self.editors:
            self._set_value(key, overrides.get(key, self.original.get(key, "")))
        self._loading = False
        self._odswiez_wiersze()

        writable = bool(path) and is_writable_format(path)
        self.write_button.setEnabled(writable)
        if not path:
            self.problem.setText("")
        elif not writable:
            self.problem.setText(
                t("{plik}: tego formatu nie zapiszemy w miejscu — metadane czekają "
                  "w pliku XMP i trafią do wyeksportowanego zdjęcia.",
                  plik=os.path.basename(path))
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
        self._odswiez_wiersze()
        if not problems:
            self.changed.emit(self.changes())

    def _on_clear(self) -> None:
        self._loading = True
        for key in self.editors:
            self._set_value(key, self.original.get(key, ""))
        self._loading = False
        self.problem.setText("")
        self._odswiez_wiersze()
        self.changed.emit({})

    # ------------------------------------------------ zwarte wiersze

    def _odswiez_wiersze(self) -> None:
        for key, wiersz in self.wiersze.items():
            widget = self.editors[key]
            value = self._value_of(key)
            tekst = widget.currentText() if isinstance(widget, QComboBox) else value
            wiersz.pokaz(tekst, bool(value) and value != self.original.get(key, ""))

    def edytuj(self, key: str) -> None:
        """Otwiera edytor jednego pola; poprzednio edytowane sie zamyka."""
        if self._edytowany == key:
            return
        self.zakoncz_edycje()
        self._edytowany = key
        self._przed_edycja = self._value_of(key)
        self.wiersze[key].set_edycja(True)
        editor = self.editors[key]
        editor.setFocus(Qt.OtherFocusReason)
        if isinstance(editor, QLineEdit):
            editor.selectAll()

    def zakoncz_edycje(self, anuluj: bool = False) -> None:
        key = self._edytowany
        if key is None:
            return
        # Najpierw zdjac stan: schowanie edytora wysyla FocusOut, ktory
        # inaczej wrocilby tu drugi raz.
        self._edytowany = None
        if anuluj and self._value_of(key) != self._przed_edycja:
            self._loading = True
            self._set_value(key, self._przed_edycja)
            self._loading = False
            self._on_edited()
        self.wiersze[key].set_edycja(False)
        self._odswiez_wiersze()

    def _zatwierdz(self, key: str, krok: int) -> None:
        # Blad walidacji zostawia pole otwarte - opis bledu stoi pod polami.
        if validate(key, self._value_of(key)) is not None:
            return
        self.zakoncz_edycje()
        if krok:
            klucze = list(self.wiersze)
            i = klucze.index(key) + krok
            if 0 <= i < len(klucze):
                self.edytuj(klucze[i])

    def eventFilter(self, obj, event) -> bool:
        key = self._edytowany
        if key is not None and obj is self.editors.get(key):
            typ = event.type()
            if typ == QEvent.KeyPress:
                klawisz = event.key()
                if klawisz == Qt.Key_Escape:
                    self.zakoncz_edycje(anuluj=True)
                    return True
                # Shift+Enter zostaje w opisie jako nowa linia.
                if klawisz in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
                    self._zatwierdz(key, 0)
                    return True
                if klawisz in (Qt.Key_Tab, Qt.Key_Backtab):
                    self._zatwierdz(key, -1 if klawisz == Qt.Key_Backtab else 1)
                    return True
            elif typ == QEvent.FocusOut and event.reason() not in (
                Qt.PopupFocusReason, Qt.ActiveWindowFocusReason
            ):
                # Rozwiniecie listy wyboru albo przelaczenie okna to nie koniec
                # edycji; klik gdzie indziej w programie - tak.
                QTimer.singleShot(0, lambda k=key: self._edytowany == k and self.zakoncz_edycje())
        return super().eventFilter(obj, event)

    # ------------------------------------------------ wszystkie tagi

    def _on_show_all(self, on: bool) -> None:
        self.pola_box.setVisible(not on)
        self.tabela_box.setVisible(on)
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
            self.table_layout.addWidget(QLabel(t("Brak metadanych w pliku")), 0, 0)
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


class _WierszPola(QWidget):
    """Zwarty wiersz "etykieta  wartosc" z rysikiem pod kursorem (punkt 30 D).

    Edytor pola jest ten sam co w pelnym formularzu, tylko schowany - odczyt,
    zmiany i zapis do sidecara ida wiec jedna droga, a wiersz przelacza
    jedynie, co widac. Rozwiniete metadane zajmuja przez to tyle miejsca co
    podglad, a nie 19 pol edycji.
    """

    def __init__(self, klucz: str, etykieta: str, edytor: QWidget, panel: "ExifPanel"):
        super().__init__()
        self.klucz = klucz
        self.edytor = edytor
        self._panel = panel
        self.etykieta = QLabel(etykieta)
        self.etykieta.setObjectName("metaLabel")
        self.wartosc = QLabel("—")
        self.wartosc.setWordWrap(True)
        self.wartosc.setMinimumWidth(1)
        self.wartosc.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.rysik = QToolButton()
        self.rysik.setObjectName("exifRysik")
        self.rysik.setIcon(ikona("edit"))
        self.rysik.setIconSize(QSize(12, 12))
        self.rysik.setAutoRaise(True)
        self.rysik.setFixedSize(18, 18)
        self.rysik.setCursor(Qt.PointingHandCursor)
        podpowiedz(self.rysik, "exif.rysik")
        self.rysik.clicked.connect(lambda: panel.edytuj(klucz))
        # Miejsce po rysiku zostaje: inaczej wartosc przeskakiwalaby o 18 px
        # przy kazdym przejechaniu kursorem po wierszach.
        polityka = self.rysik.sizePolicy()
        polityka.setRetainSizeWhenHidden(True)
        self.rysik.setSizePolicy(polityka)
        self.rysik.hide()
        edytor.hide()

        uklad = QHBoxLayout(self)
        uklad.setContentsMargins(0, 1, 0, 1)
        uklad.setSpacing(6)
        uklad.addWidget(self.etykieta, 0, Qt.AlignTop)
        uklad.addWidget(self.wartosc, 1, Qt.AlignTop)
        uklad.addWidget(edytor, 1)
        uklad.addWidget(self.rysik, 0, Qt.AlignTop)

    def enterEvent(self, event) -> None:
        if not self.edytor.isVisible():
            self.rysik.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.rysik.hide()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._panel.edytuj(self.klucz)

    def pokaz(self, tekst: str, zmienione: bool) -> None:
        self.wartosc.setText(("◆ " if zmienione else "") + (tekst or "—"))

    def set_edycja(self, on: bool) -> None:
        self.edytor.setVisible(on)
        self.wartosc.setVisible(not on)
        if on:
            self.rysik.hide()


# Sekcja zwijana zyje teraz w InfoPanel (app/edit_panel.py): metadane sa
# chowanym dnem sekcji z danymi zdjecia, a nie osobnym blokiem z naglowkiem.
