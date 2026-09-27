"""Sekcja presetow: lista wbudowanych i wlasnych, zapis, import, eksport.

Klikniecie presetu go naklada - bez osobnego "Zastosuj", bo nalozenie jest
jednym krokiem historii i cofa sie je Ctrl+Z. Tresc presetu i pliki
obsluguje core/presety.py; tu jest tylko interfejs.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import presety
from ..core.params import EditParams
from ..przeklad import N_, mnoga, t
from .podpowiedzi import podpowiedz

ROLA = Qt.UserRole + 1
FILTR_PLIKOW = N_("Preset Punctum (*.json)")


class PresetyPanel(QWidget):
    """Tresc sekcji "presety"."""

    zastosuj = Signal(object)  # presety.Preset
    komunikat = Signal(str)  # tekst do paska stanu

    def __init__(self, biezace: Callable[[], EditParams | None], parent=None,
                 baza: str | None = None):
        super().__init__(parent)
        self._biezace = biezace
        self._baza = baza  # katalog ustawien; testy podaja wlasny
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.lista = QListWidget()
        self.lista.setObjectName("listaPresetow")
        self.lista.setMinimumHeight(90)
        self.lista.setMaximumHeight(200)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu_kontekstowe)
        self.lista.itemClicked.connect(self._on_klik)
        self.lista.currentItemChanged.connect(lambda *_: self._odswiez_przyciski())
        podpowiedz(self.lista, "presety.lista")
        layout.addWidget(self.lista)

        wiersz = QHBoxLayout()
        wiersz.setSpacing(4)
        self.zapisz_button = QPushButton(t("Zapisz…"))
        podpowiedz(self.zapisz_button, "presety.zapisz")
        self.zapisz_button.clicked.connect(self.zapisz_biezace)
        self.usun_button = QPushButton(t("Usuń"))
        podpowiedz(self.usun_button, "presety.usun")
        self.usun_button.clicked.connect(self.usun_zaznaczony)
        wiersz.addWidget(self.zapisz_button, 1)
        wiersz.addWidget(self.usun_button, 1)
        layout.addLayout(wiersz)

        self.odswiez()

    # --- lista ----------------------------------------------------------

    def odswiez(self, zaznacz: str | None = None) -> None:
        """Buduje liste od nowa: wbudowane, potem wlasne pod naglowkiem."""
        self.lista.clear()
        wlasne = presety.wlasne(self._baza)
        for naglowek, grupa in ((t("Wbudowane"), presety.WBUDOWANE), (t("Własne"), wlasne)):
            if not grupa:
                continue
            item = QListWidgetItem(naglowek.upper())
            item.setFlags(Qt.NoItemFlags)  # naglowek, nie do klikniecia
            item.setForeground(QColor(128, 128, 134))
            self.lista.addItem(item)
            for preset in grupa:
                item = QListWidgetItem("  " + preset.etykieta())
                item.setData(ROLA, preset)
                self.lista.addItem(item)
                if zaznacz is not None and not preset.wbudowany and preset.nazwa == zaznacz:
                    self.lista.setCurrentItem(item)
        self._odswiez_przyciski()

    def zaznaczony(self) -> presety.Preset | None:
        item = self.lista.currentItem()
        return item.data(ROLA) if item is not None else None

    def _odswiez_przyciski(self) -> None:
        preset = self.zaznaczony()
        self.usun_button.setEnabled(preset is not None and not preset.wbudowany)

    def _on_klik(self, item: QListWidgetItem) -> None:
        preset = item.data(ROLA)
        if preset is not None:
            self.zastosuj.emit(preset)

    def _menu_kontekstowe(self, pozycja) -> None:
        item = self.lista.itemAt(pozycja)
        preset = item.data(ROLA) if item is not None else None
        if preset is not None:
            self.lista.setCurrentItem(item)
        menu = QMenu(self)
        if preset is not None:
            menu.addAction(t("Zastosuj"), lambda: self.zastosuj.emit(preset))
            menu.addAction(t("Eksportuj…"), self.eksportuj_zaznaczony)
            usun = menu.addAction(t("Usuń"), self.usun_zaznaczony)
            usun.setEnabled(not preset.wbudowany)
            menu.addSeparator()
        menu.addAction(t("Zapisz bieżące jako preset…"), self.zapisz_biezace)
        menu.addAction(t("Importuj preset…"), self.importuj)
        menu.exec(self.lista.viewport().mapToGlobal(pozycja))

    # --- akcje ----------------------------------------------------------

    def zapisz_biezace(self) -> None:
        params = self._biezace()
        if params is None:
            self.komunikat.emit(t("Najpierw otwórz zdjęcie."))
            return
        okno = ZapiszPresetDialog(self)
        if okno.exec() != QDialog.Accepted:
            return
        nazwa, grupy = okno.nazwa(), okno.grupy()
        if presety.istnieje(nazwa, self._baza) and QMessageBox.question(
            self, t("Zapisz preset"),
            t("Preset „{nazwa}” już istnieje. Zastąpić go?", nazwa=nazwa),
        ) != QMessageBox.Yes:
            return
        preset = presety.zapisz_wlasny(nazwa, presety.wartosci_z_grup(params, grupy), self._baza)
        if preset is None:
            QMessageBox.warning(self, t("Zapisz preset"), t("Nie udało się zapisać presetu."))
            return
        self.odswiez(zaznacz=preset.nazwa)
        self.komunikat.emit(t("Zapisano preset „{nazwa}”.", nazwa=preset.nazwa))

    def usun_zaznaczony(self) -> None:
        preset = self.zaznaczony()
        if preset is None or preset.wbudowany:
            return
        if QMessageBox.question(
            self, t("Usuń preset"), t("Usunąć preset „{nazwa}”?", nazwa=preset.nazwa)
        ) != QMessageBox.Yes:
            return
        if presety.usun(preset):
            self.odswiez()
            self.komunikat.emit(t("Usunięto preset „{nazwa}”.", nazwa=preset.nazwa))

    def importuj(self) -> None:
        sciezki, _ = QFileDialog.getOpenFileNames(self, t("Importuj preset"), "", t(FILTR_PLIKOW))
        if not sciezki:
            return
        udane = [p for p in (presety.importuj(s, self._baza) for s in sciezki) if p is not None]
        if len(udane) < len(sciezki):
            QMessageBox.warning(self, t("Importuj preset"),
                                t("Część plików nie jest presetem Punctum i została pominięta."))
        if udane:
            self.odswiez(zaznacz=udane[-1].nazwa)
            self.komunikat.emit(mnoga(
                len(udane), "Zaimportowano {n} preset|Zaimportowano {n} presety|Zaimportowano {n} presetów"
            ))

    def eksportuj_zaznaczony(self) -> None:
        preset = self.zaznaczony()
        if preset is None:
            self.komunikat.emit(t("Zaznacz preset na liście."))
            return
        nazwa = presety.nazwa_pliku(preset.etykieta())
        sciezka, _ = QFileDialog.getSaveFileName(self, t("Eksportuj preset"), nazwa, t(FILTR_PLIKOW))
        if not sciezka:
            return
        kopia = presety.Preset(preset.etykieta(), dict(preset.wartosci))
        if presety.zapisz_plik(kopia, sciezka):
            self.komunikat.emit(t("Wyeksportowano preset do {plik}.", plik=sciezka))
        else:
            QMessageBox.warning(self, t("Eksportuj preset"), t("Nie udało się zapisać pliku."))


class ZapiszPresetDialog(QDialog):
    """Nazwa presetu i grupy nastaw, ktore ma zapamietac."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from .panele import TYTULY  # nazwy grup = nazwy sekcji nad suwakami

        self.setWindowTitle(t("Zapisz preset"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("Nazwa:")))
        self.pole_nazwy = QLineEdit()
        podpowiedz(self.pole_nazwy, "presety.nazwa")
        self.pole_nazwy.textChanged.connect(lambda _: self._odswiez())
        layout.addWidget(self.pole_nazwy)
        layout.addSpacing(6)
        layout.addWidget(QLabel(t("Zapamiętaj:")))
        self.pola: dict[str, QCheckBox] = {}
        for grupa in presety.GRUPY:
            pole = QCheckBox(t(TYTULY[grupa]))
            pole.setChecked(grupa in presety.GRUPY_DOMYSLNE)
            podpowiedz(pole, "presety.grupa")
            pole.toggled.connect(lambda _: self._odswiez())
            self.pola[grupa] = pole
            layout.addWidget(pole)
        uwaga = QLabel(t("Kadr, lokalizacja i metadane nie trafiają do presetu."))
        uwaga.setObjectName("metaLabel")
        uwaga.setWordWrap(True)
        layout.addWidget(uwaga)
        self.przyciski = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.przyciski.button(QDialogButtonBox.Ok).setText(t("Zapisz"))
        self.przyciski.button(QDialogButtonBox.Cancel).setText(t("Anuluj"))
        self.przyciski.accepted.connect(self.accept)
        self.przyciski.rejected.connect(self.reject)
        layout.addWidget(self.przyciski)
        self.setMinimumWidth(300)
        self._odswiez()

    def _odswiez(self) -> None:
        self.przyciski.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.nazwa()) and bool(self.grupy())
        )

    def nazwa(self) -> str:
        return self.pole_nazwy.text().strip()

    def grupy(self) -> list[str]:
        return [grupa for grupa, pole in self.pola.items() if pole.isChecked()]
