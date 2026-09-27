"""Okno dopasowania zdjec do sladu GPX.

Najczestszy powod, dla ktorego nic sie nie dopasowuje, to czas: aparat nie zna
strefy, a jego zegar sie spieszy albo spoznia. Dlatego wynik liczy sie na
zywo przy kazdej zmianie przesuniecia - uzytkownik widzi od razu, czy trafil,
zamiast zgadywac i cofac.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ..core.slad import Slad, dopasuj, strefa_systemu
from ..przeklad import mnoga, t
from .podpowiedzi import podpowiedz


def _opis(tekst: str) -> QLabel:
    label = QLabel(tekst)
    label.setObjectName("metaLabel")
    label.setWordWrap(True)
    return label


def _czas(czas: datetime) -> str:
    return czas.strftime("%Y-%m-%d %H:%M:%S")


class SladDialog(QDialog):
    """Zwraca w `wynik` wspolrzedne dla zdjec, ktore trafily w slad."""

    def __init__(self, slad: Slad, plik: str, czasy: dict[str, datetime | None],
                 polozone: set[str], zaznaczone: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Dopasuj do śladu GPX"))
        self.setMinimumWidth(460)
        self.slad = slad
        self.czasy = czasy
        self.polozone = polozone
        self.wynik: dict[str, tuple[float, float]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        naglowek = QLabel(mnoga(len(slad), "Ślad {plik}: {n} punkt|Ślad {plik}: {n} punkty|"
                                "Ślad {plik}: {n} punktów", plik=os.path.basename(plik)))
        naglowek.setObjectName("cameraLabel")
        layout.addWidget(naglowek)
        if slad.poczatek is not None:
            layout.addWidget(_opis(t("Ślad od {od} do {do} (czas UTC)",
                                     od=_czas(slad.poczatek), do=_czas(slad.koniec))))
        znane = sorted(c for c in czasy.values() if c is not None)
        if znane:
            layout.addWidget(_opis(t("Zdjęcia od {od} do {do} (czas aparatu)",
                                     od=_czas(znane[0]), do=_czas(znane[-1]))))
        ktore = (t("Zdjęcia: zaznaczone ({n})", n=len(czasy)) if zaznaczone
                 else t("Zdjęcia: wszystkie na liście ({n})", n=len(czasy)))
        layout.addWidget(_opis(ktore))

        form = QFormLayout()
        self.strefa = QDoubleSpinBox()
        self.strefa.setRange(-12.0, 14.0)
        self.strefa.setSingleStep(0.25)
        self.strefa.setDecimals(2)
        self.strefa.setPrefix("UTC ")
        self.strefa.setSuffix(" h")
        # Podpowiedz strefy z dnia pierwszego zdjecia - latem i zima w Polsce
        # to rozne godziny, a zdjecia z wakacji ogladamy czesto w listopadzie.
        domyslna = strefa_systemu(znane[0] if znane else None)
        self.strefa.setValue(domyslna.total_seconds() / 3600.0)
        form.addRow(t("Strefa czasowa aparatu:"), self.strefa)
        podpowiedz(self.strefa, "slad.strefa", etykieta=form.labelForField(self.strefa))

        self.zegar = QSpinBox()
        self.zegar.setRange(-86399, 86399)
        self.zegar.setSuffix(" s")
        form.addRow(t("Zegar aparatu spieszy się o:"), self.zegar)
        podpowiedz(self.zegar, "slad.zegar", etykieta=form.labelForField(self.zegar))

        self.tolerancja = QSpinBox()
        self.tolerancja.setRange(1, 240)
        self.tolerancja.setValue(10)
        self.tolerancja.setSuffix(t(" min"))
        form.addRow(t("Najdalej od punktu śladu:"), self.tolerancja)
        podpowiedz(self.tolerancja, "slad.tolerancja", etykieta=form.labelForField(self.tolerancja))
        layout.addLayout(form)

        self.tylko_bez = QCheckBox(t("Tylko zdjęcia bez lokalizacji"))
        self.tylko_bez.setChecked(True)
        podpowiedz(self.tylko_bez, "slad.tylko_bez")
        layout.addWidget(self.tylko_bez)

        self.podsumowanie = QLabel()
        self.podsumowanie.setObjectName("settingsLabel")
        self.podsumowanie.setWordWrap(True)
        layout.addWidget(self.podsumowanie)

        przyciski = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.nadaj = przyciski.button(QDialogButtonBox.Ok)
        self.nadaj.setText(t("Nadaj lokalizację"))
        podpowiedz(self.nadaj, "slad.nadaj")
        przyciski.button(QDialogButtonBox.Cancel).setText(t("Anuluj"))
        przyciski.accepted.connect(self.accept)
        przyciski.rejected.connect(self.reject)
        layout.addWidget(przyciski)

        for pole in (self.strefa, self.zegar, self.tolerancja):
            pole.valueChanged.connect(self._przelicz)
        self.tylko_bez.toggled.connect(self._przelicz)
        self._przelicz()

    def przesuniecie(self) -> timedelta:
        """O ile czas aparatu wyprzedza UTC."""
        return timedelta(hours=self.strefa.value(), seconds=self.zegar.value())

    def _przelicz(self) -> None:
        brane = {
            sciezka: czas for sciezka, czas in self.czasy.items()
            if not (self.tylko_bez.isChecked() and sciezka in self.polozone)
        }
        self.wynik = dopasuj(self.slad, brane, self.przesuniecie(),
                             timedelta(minutes=self.tolerancja.value()))
        linie = [t("Dopasowane: {m} z {n}", m=len(self.wynik), n=len(brane))]
        bez_daty = sum(1 for czas in brane.values() if czas is None)
        if bez_daty:
            linie.append(mnoga(bez_daty, "{n} zdjęcie nie ma daty wykonania|"
                               "{n} zdjęcia nie mają daty wykonania|"
                               "{n} zdjęć nie ma daty wykonania"))
        if brane and not self.wynik:
            linie.append(t("Żadne zdjęcie nie trafia w czas śladu — sprawdź strefę "
                           "i zegar aparatu."))
        self.podsumowanie.setText("\n".join(linie))
        self.nadaj.setEnabled(bool(self.wynik))
