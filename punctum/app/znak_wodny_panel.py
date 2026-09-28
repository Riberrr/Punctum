"""Edytor wzoru znaku wodnego (punkt 11) - w ustawieniach i w oknie eksportu.

Podglad liczy ta sama funkcja, ktora naklada znak przy eksporcie
(`core.znak_wodny.naloz`), wiec pokazuje dokladnie to, co trafi do pliku -
tylko w mniejszej skali, bo rozmiar i margines sa wzgledne.
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image
from PySide6.QtCore import Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.znak_wodny import POZYCJE, RODZAJ_OBRAZ, RODZAJ_TEKST, ZAKRESY, ZnakWodny, naloz
from ..przeklad import N_, t
from .podpowiedzi import podpowiedz, podpowiedz_wiersza
from .skala import marginesy, odstep, px, stala, sygnaly

KOLORY_ETYKIETY = {"bialy": N_("Biały"), "czarny": N_("Czarny")}

# Wymiary podgladu przy skali 100 % (3:2, jak wiekszosc aparatow).
PODGLAD = (300, 200)


def _probka_zastepcza() -> Image.Image:
    """Tlo podgladu, gdy nie ma otwartego zdjecia: przejscie od ciemnego do
    jasnego, zeby bylo widac, jak znak wypada na obu."""
    szer, wys = 600, 400
    rampa = np.linspace(40, 215, szer, dtype=np.float32)
    kolumny = np.stack([rampa * 0.9, rampa * 0.95, rampa], axis=-1)
    obraz = np.broadcast_to(kolumny, (wys, szer, 3)).astype(np.uint8)
    return Image.fromarray(np.ascontiguousarray(obraz), "RGB")


def pixmapa_podgladu(znak: ZnakWodny | None, probka: np.ndarray | None,
                     szer: int, wys: int, dpr: float = 1.0) -> QPixmap:
    """Probka zmniejszona do ramki szer x wys, ze znakiem nalozonym po zmniejszeniu.

    Liczymy w pikselach ekranu (dpr), inaczej przy 150 % w systemie cienki
    napis podgladu bylby rozmyty i wygladal gorzej niz w pliku.
    """
    obraz = (Image.fromarray(np.ascontiguousarray(probka), "RGB") if probka is not None
             else _probka_zastepcza())
    obraz.thumbnail((max(1, round(szer * dpr)), max(1, round(wys * dpr))), Image.LANCZOS)
    obraz = naloz(obraz, znak)
    dane = obraz.tobytes()
    qimg = QImage(dane, obraz.width, obraz.height, 3 * obraz.width, QImage.Format_RGB888)
    pixmapa = QPixmap.fromImage(qimg.copy())
    pixmapa.setDevicePixelRatio(dpr)
    return pixmapa


class EdytorZnaku(QWidget):
    """Formularz wzoru z podgladem obok."""

    zmieniono = Signal()

    def __init__(self, znak: ZnakWodny, probka: np.ndarray | None = None, parent=None):
        super().__init__(parent)
        # Podglad liczy sie przy kazdej zmianie pola - zmniejszamy probke raz,
        # zamiast przy kazdym znaku wpisanym w tekst.
        if probka is not None:
            maly = Image.fromarray(np.ascontiguousarray(probka), "RGB")
            maly.thumbnail((PODGLAD[0] * 4, PODGLAD[1] * 4), Image.LANCZOS)
            probka = np.asarray(maly)
        self.probka = probka
        self._domyslny_tekst = ""
        uklad = QHBoxLayout(self)
        marginesy(uklad, 0, 0, 0, 0)
        odstep(uklad, 12)

        form = QFormLayout()
        uklad.addLayout(form, 1)

        rodzaj = QWidget()
        rodzaj_uklad = QHBoxLayout(rodzaj)
        marginesy(rodzaj_uklad, 0, 0, 0, 0)
        self.tekst_radio = QRadioButton(t("Tekst"))
        self.obraz_radio = QRadioButton(t("Obraz"))
        self._rodzaj = QButtonGroup(self)
        for przycisk in (self.tekst_radio, self.obraz_radio):
            self._rodzaj.addButton(przycisk)
            rodzaj_uklad.addWidget(przycisk)
        rodzaj_uklad.addStretch(1)
        podpowiedz(self.tekst_radio, "znak.rodzaj_tekst")
        podpowiedz(self.obraz_radio, "znak.rodzaj_obraz")
        form.addRow(t("Rodzaj:"), rodzaj)

        self.tekst_edit = QLineEdit()
        form.addRow(t("Tekst:"), self.tekst_edit)
        podpowiedz_wiersza(form, self.tekst_edit, "znak.tekst")

        self.kolor_box = QComboBox()
        for klucz, etykieta in KOLORY_ETYKIETY.items():
            self.kolor_box.addItem(t(etykieta), klucz)
        form.addRow(t("Kolor:"), self.kolor_box)
        podpowiedz_wiersza(form, self.kolor_box, "znak.kolor")

        self.obraz_wiersz = QWidget()
        obraz_uklad = QHBoxLayout(self.obraz_wiersz)
        marginesy(obraz_uklad, 0, 0, 0, 0)
        self.obraz_edit = QLineEdit()
        self.obraz_edit.setPlaceholderText(t("plik PNG z przezroczystością"))
        self.obraz_przycisk = QPushButton(t("Wybierz…"))
        self.obraz_przycisk.clicked.connect(self._wybierz_obraz)
        obraz_uklad.addWidget(self.obraz_edit, 1)
        obraz_uklad.addWidget(self.obraz_przycisk)
        form.addRow(t("Obraz:"), self.obraz_wiersz)
        podpowiedz(self.obraz_edit, "znak.obraz", etykieta=form.labelForField(self.obraz_wiersz))
        podpowiedz(self.obraz_przycisk, "znak.wybierz_obraz")

        polozenie = QWidget()
        polozenie_uklad = QHBoxLayout(polozenie)
        marginesy(polozenie_uklad, 0, 0, 0, 0)
        odstep(polozenie_uklad, 10)
        siatka = QGridLayout()
        odstep(siatka, 2)
        self._pozycje = QButtonGroup(self)
        self.przyciski_pozycji: dict[str, QToolButton] = {}
        for i, pozycja in enumerate(POZYCJE):
            przycisk = QToolButton()
            przycisk.setCheckable(True)
            przycisk.setObjectName("pozycjaZnaku")
            stala(przycisk, 22, 16)
            podpowiedz(przycisk, "znak.pozycja")
            self._pozycje.addButton(przycisk)
            self.przyciski_pozycji[pozycja] = przycisk
            siatka.addWidget(przycisk, i // 3, i % 3)
        polozenie_uklad.addLayout(siatka)
        self.kafelki_box = QCheckBox(t("Powtarzaj na całym zdjęciu"))
        podpowiedz(self.kafelki_box, "znak.kafelki")
        polozenie_uklad.addWidget(self.kafelki_box)
        polozenie_uklad.addStretch(1)
        form.addRow(t("Położenie:"), polozenie)

        self.rozmiar_box = self._procenty("rozmiar")
        form.addRow(t("Rozmiar:"), self.rozmiar_box)
        podpowiedz_wiersza(form, self.rozmiar_box, "znak.rozmiar")
        self.krycie_box = self._procenty("krycie")
        form.addRow(t("Krycie:"), self.krycie_box)
        podpowiedz_wiersza(form, self.krycie_box, "znak.krycie")
        self.margines_box = self._procenty("margines")
        form.addRow(t("Margines:"), self.margines_box)
        podpowiedz_wiersza(form, self.margines_box, "znak.margines")

        self.podglad = QLabel()
        self.podglad.setObjectName("podgladZnaku")
        stala(self.podglad, *PODGLAD)
        podpowiedz(self.podglad, "znak.podglad")
        uklad.addWidget(self.podglad)

        self.ustaw(znak)
        for przycisk in (self.tekst_radio, self.obraz_radio, self.kafelki_box):
            przycisk.toggled.connect(self._po_zmianie)
        self._pozycje.buttonToggled.connect(self._po_zmianie)
        self.tekst_edit.textChanged.connect(self._po_zmianie)
        self.obraz_edit.textChanged.connect(self._po_zmianie)
        self.kolor_box.currentIndexChanged.connect(self._po_zmianie)
        for pole in (self.rozmiar_box, self.krycie_box, self.margines_box):
            pole.valueChanged.connect(self._po_zmianie)
        sygnaly.zmieniona.connect(self._odswiez_podglad)

    def _procenty(self, nazwa: str) -> QSpinBox:
        pole = QSpinBox()
        pole.setRange(*ZAKRESY[nazwa])
        pole.setSuffix(" %")
        return pole

    # ------------------------------------------------------------- stan

    def ustaw(self, znak: ZnakWodny) -> None:
        (self.obraz_radio if znak.rodzaj == RODZAJ_OBRAZ else self.tekst_radio).setChecked(True)
        self.tekst_edit.setText(znak.tekst)
        self.obraz_edit.setText(znak.obraz)
        self.kolor_box.setCurrentIndex(max(0, self.kolor_box.findData(znak.kolor)))
        self.przyciski_pozycji[znak.pozycja].setChecked(True)
        self.kafelki_box.setChecked(znak.kafelki)
        self.rozmiar_box.setValue(znak.rozmiar)
        self.krycie_box.setValue(znak.krycie)
        self.margines_box.setValue(znak.margines)
        self._uaktualnij_dostepnosc()
        self._odswiez_podglad()

    def znak(self) -> ZnakWodny:
        pozycja = next((p for p, b in self.przyciski_pozycji.items() if b.isChecked()), "pd")
        return ZnakWodny(
            rodzaj=RODZAJ_OBRAZ if self.obraz_radio.isChecked() else RODZAJ_TEKST,
            tekst=self.tekst_edit.text().strip(),
            obraz=self.obraz_edit.text().strip(),
            kolor=self.kolor_box.currentData(),
            pozycja=pozycja,
            kafelki=self.kafelki_box.isChecked(),
            rozmiar=self.rozmiar_box.value(),
            krycie=self.krycie_box.value(),
            margines=self.margines_box.value(),
        )

    def ustaw_domyslny_tekst(self, tekst: str) -> None:
        """Tekst uzywany, gdy pole zostanie puste (prawa autorskie / autor)."""
        self._domyslny_tekst = tekst
        self.tekst_edit.setPlaceholderText(
            tekst or t("np. © 2026 Imię Nazwisko")
        )
        self._odswiez_podglad()

    def znak_do_podgladu(self) -> ZnakWodny:
        znak = self.znak()
        if znak.rodzaj == RODZAJ_TEKST and not znak.tekst:
            znak.tekst = self._domyslny_tekst
        return znak

    # ---------------------------------------------------------- reakcje

    def _po_zmianie(self, *_) -> None:
        self._uaktualnij_dostepnosc()
        self._odswiez_podglad()
        self.zmieniono.emit()

    def _uaktualnij_dostepnosc(self) -> None:
        obraz = self.obraz_radio.isChecked()
        self.tekst_edit.setEnabled(not obraz)
        self.kolor_box.setEnabled(not obraz)
        self.obraz_wiersz.setEnabled(obraz)
        # Kafelki ida przez caly kadr - polozenie i margines nic wtedy nie znacza.
        kafelki = self.kafelki_box.isChecked()
        for przycisk in self.przyciski_pozycji.values():
            przycisk.setEnabled(not kafelki)
        self.margines_box.setEnabled(not kafelki)

    def _odswiez_podglad(self) -> None:
        self.podglad.setPixmap(pixmapa_podgladu(
            self.znak_do_podgladu(), self.probka, px(PODGLAD[0]), px(PODGLAD[1]),
            self.devicePixelRatioF(),
        ))

    def _wybierz_obraz(self) -> None:
        start = os.path.dirname(self.obraz_edit.text()) if self.obraz_edit.text() else ""
        plik, _ = QFileDialog.getOpenFileName(
            self, t("Obraz znaku wodnego"), start, t("Obrazy PNG (*.png)")
        )
        if plik:
            self.obraz_edit.setText(os.path.normpath(plik))


class OknoZnaku(QDialog):
    """Wzor znaku otwierany z okna eksportu - ta sama tresc co w ustawieniach."""

    def __init__(self, znak: ZnakWodny, probka: np.ndarray | None, domyslny_tekst: str,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Znak wodny"))
        uklad = QVBoxLayout(self)
        marginesy(uklad, 12, 12, 12, 12)
        odstep(uklad, 10)
        self.edytor = EdytorZnaku(znak, probka, self)
        self.edytor.ustaw_domyslny_tekst(domyslny_tekst)
        uklad.addWidget(self.edytor)
        przyciski = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        przyciski.button(QDialogButtonBox.Ok).setText(t("Zapisz"))
        przyciski.button(QDialogButtonBox.Cancel).setText(t("Anuluj"))
        przyciski.accepted.connect(self.accept)
        przyciski.rejected.connect(self.reject)
        uklad.addWidget(przyciski)
