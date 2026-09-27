"""Panele boczne okna Edycji zlozone z sekcji.

Sekcje mozna zwijac, ukrywac, przestawiac w obrebie panelu i przenosic
miedzy panelami (albo do schowka). Stan ukladu lezy w ustawieniach pod
stalymi kluczami sekcji - nie pod ich nazwami, bo nazwy sa przetlumaczone
i zmiana jezyka rozsypalaby zapisany uklad.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QObject, QSize, Qt, Signal
from PySide6.QtGui import QAction, QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..przeklad import N_, t
from .podpowiedzi import podpowiedz
from .style import ikona

LEWY, PRAWY, SCHOWEK = "lewy", "prawy", "schowek"
PANELE = (LEWY, PRAWY)
MIEJSCA = (LEWY, PRAWY, SCHOWEK)

# Kolejnosc slownika = kolejnosc w ukladzie domyslnym i w oknie ukladu.
TYTULY = {
    "nawigator": N_("Nawigator"),
    "powiekszenie": N_("Powiększenie"),
    "przed_po": N_("Przed / po"),
    "dane": N_("Dane zdjęcia"),
    "histogram": N_("Histogram"),
    "kadrowanie": N_("Kadrowanie i obrót"),
    "balans": N_("Balans bieli"),
    "ton": N_("Odcień"),
    "obecnosc": N_("Obecność"),
    "wyostrzanie": N_("Wyostrzanie"),
    "szum": N_("Usuwanie szumu"),
}

UKLAD_DOMYSLNY = {
    LEWY: ["nawigator", "powiekszenie", "przed_po", "dane"],
    PRAWY: ["histogram", "kadrowanie", "balans", "ton", "obecnosc", "wyostrzanie", "szum"],
}

TYTULY_MIEJSC = {
    SCHOWEK: N_("Nieużywane"),
    LEWY: N_("Panel lewy"),
    PRAWY: N_("Panel prawy"),
}

MIME = "application/x-punctum-sekcja"


def uporzadkuj(stan) -> dict:
    """Zapisany uklad -> uklad pewny: kazda znana sekcja dokladnie raz.

    Plik ustawien moze pochodzic ze starszej wersji albo byc poprawiany
    recznie. Nieznane klucze i powtorki odpadaja. Sekcja, ktorej w zapisie
    nie ma (dodana w nowszej wersji), trafia do swojego domyslnego panelu
    zaraz za sekcja, za ktora stoi w ukladzie domyslnym - reszta ukladu
    uzytkownika zostaje nietknieta.
    """
    stan = stan if isinstance(stan, dict) else {}
    wynik: dict[str, list] = {m: [] for m in MIEJSCA}
    widziane: set[str] = set()
    for miejsce in MIEJSCA:
        lista = stan.get(miejsce)
        if not isinstance(lista, list):
            continue
        for klucz in lista:
            if klucz in TYTULY and klucz not in widziane:
                widziane.add(klucz)
                wynik[miejsce].append(klucz)

    for klucz in TYTULY:
        if klucz not in widziane:
            widziane.add(klucz)
            wstaw_domyslnie(wynik, klucz)

    # Pierwsza wersja punktu 23 znala sekcje "ukryte w miejscu". Uzytkownik
    # zdecydowal, ze wylaczenie sekcji to odlozenie jej do schowka - stary
    # zapis przenosimy tam, zamiast gubic. Dopiero po uzupelnieniu brakow,
    # bo ukryta mogla byc tez sekcja, ktorej w zapisie nie ma w zadnym panelu.
    stare_ukryte = stan.get("ukryte")
    if isinstance(stare_ukryte, list):
        for klucz in stare_ukryte:
            if klucz in TYTULY and klucz not in wynik[SCHOWEK]:
                przenies(wynik, klucz, SCHOWEK)

    def zbior(nazwa: str, dozwolone) -> list[str]:
        wartosc = stan.get(nazwa)
        if not isinstance(wartosc, list):
            return []
        return sorted({k for k in wartosc if isinstance(k, str) and k in dozwolone})

    wynik["zwiniete"] = zbior("zwiniete", TYTULY)
    wynik["odblokowane"] = zbior("odblokowane", PANELE)
    return wynik


def wstaw_domyslnie(stan: dict, klucz: str) -> None:
    """Stawia sekcje w jej domyslnym panelu, zaraz za najblizszym poprzednikiem
    z ukladu domyslnego, ktory tam lezy (brak poprzednika = na poczatek).

    Tak wraca sekcja wlaczona z menu i tak laduje sekcja dodana w nowej
    wersji - reszta ukladu uzytkownika zostaje nietknieta.
    """
    for miejsce in MIEJSCA:
        if klucz in stan[miejsce]:
            stan[miejsce].remove(klucz)
    miejsce = next(m for m in PANELE if klucz in UKLAD_DOMYSLNY[m])
    domyslne = UKLAD_DOMYSLNY[miejsce]
    pozycja = 0
    for poprzedni in reversed(domyslne[: domyslne.index(klucz)]):
        if poprzedni in stan[miejsce]:
            pozycja = stan[miejsce].index(poprzedni) + 1
            break
    stan[miejsce].insert(pozycja, klucz)


def przenies(stan: dict, klucz: str, cel: str, przed: str | None = None) -> None:
    """Przenosi sekcje do `cel`, przed sekcje `przed` (None = na koniec)."""
    for miejsce in MIEJSCA:
        if klucz in stan[miejsce]:
            stan[miejsce].remove(klucz)
    lista = stan[cel]
    lista.insert(lista.index(przed) if przed in lista else len(lista), klucz)


# ------------------------------------------------------------------ widzety


class _NaglowekSekcji(QWidget):
    """Klik zwija sekcje; w odblokowanym panelu naglowek jest tez uchwytem."""

    def __init__(self, sekcja: "Sekcja"):
        super().__init__()
        self._sekcja = sekcja
        self._nacisk = None
        self.setObjectName("sectionHeader")
        self.setCursor(Qt.PointingHandCursor)

        self.uchwyt = QLabel("⋮⋮")
        self.uchwyt.setObjectName("sectionGrip")
        self.uchwyt.hide()
        self.strzalka = QToolButton()
        self.strzalka.setObjectName("sectionChevron")
        self.strzalka.setAutoRaise(True)
        self.strzalka.setFixedSize(16, 16)
        self.strzalka.setText("▾")
        podpowiedz(self.strzalka, "panele.sekcja")
        self.strzalka.clicked.connect(sekcja.przelacz)
        self.tytul = QLabel(t(TYTULY[sekcja.klucz]).upper())
        self.tytul.setObjectName("sectionTitle")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 2)
        layout.setSpacing(4)
        layout.addWidget(self.uchwyt)
        layout.addWidget(self.strzalka)
        layout.addWidget(self.tytul, 1)

    def set_przesuwalny(self, on: bool) -> None:
        self.uchwyt.setVisible(on)
        self.setCursor(Qt.OpenHandCursor if on else Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._nacisk = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._nacisk is not None
            and self._sekcja.przesuwalna
            and (event.position().toPoint() - self._nacisk).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            poczatek, self._nacisk = self._nacisk, None
            self._ciagnij(poczatek)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        # Klik bez przeciagania zwija; przeciagniecie konczy sie w _ciagnij
        # i tu juz nie dociera z ustawionym `_nacisk`.
        if event.button() == Qt.LeftButton and self._nacisk is not None:
            self._nacisk = None
            self._sekcja.przelacz()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        self._sekcja.uklad.pokaz_menu(event.globalPos(), self.window())

    def _ciagnij(self, poczatek) -> None:
        mime = QMimeData()
        mime.setData(MIME, self._sekcja.klucz.encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(poczatek)
        drag.exec(Qt.MoveAction)


class Sekcja(QFrame):
    """Naglowek z nazwa plus tresc, ktora zwija sie pod naglowek."""

    rozciaganie_zmienione = Signal()

    def __init__(self, klucz: str, tresc: QWidget, uklad: "UkladPaneli"):
        super().__init__()
        self.setObjectName("panelSection")
        self.klucz = klucz
        self.tresc = tresc
        self.uklad = uklad
        self.zwinieta = False
        self.przesuwalna = False
        self._rozciagliwa = False

        self.naglowek = _NaglowekSekcji(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 5)
        layout.setSpacing(2)
        layout.addWidget(self.naglowek)
        layout.addWidget(tresc, 1)

    def przelacz(self) -> None:
        self.uklad.przelacz_zwiniecie(self.klucz)

    def set_zwinieta(self, on: bool) -> None:
        if on == self.zwinieta:
            return
        self.zwinieta = on
        self.tresc.setVisible(not on)
        self.naglowek.strzalka.setText("▸" if on else "▾")
        self.rozciaganie_zmienione.emit()

    def set_przesuwalna(self, on: bool) -> None:
        self.przesuwalna = on
        self.naglowek.set_przesuwalny(on)

    def ustaw_rozciaganie(self, on: bool) -> None:
        """Sekcja z wlasnym przewijaniem (rozwiniete metadane) bierze wolne
        miejsce panelu; zwinieta nie moze rozdmuchac ramki na pol okna."""
        self._rozciagliwa = bool(on)
        self.rozciaganie_zmienione.emit()

    def chce_miejsca(self) -> bool:
        return self._rozciagliwa and not self.zwinieta


class _UkladListy(QVBoxLayout):
    """Pionowy uklad listy sekcji, ktory nie zglasza wysokosci zaleznej od
    szerokosci.

    Etykiety z zawijaniem (dane zdjecia) wlaczaja w ukladzie tryb
    "wysokosc zalezy od szerokosci". QScrollArea rozciaga wtedy tresc do
    wysokosci PREFEROWANEJ (zmierzone: 944 px przy 687 px miejsca), zamiast
    scisnac ja do minimalnej - rozwiniete metadane wypychaly swoje przyciski
    pod krawedz panelu, choc z wlasnym przewijaniem zmiescilyby sie w nim.
    """

    def hasHeightForWidth(self) -> bool:
        return False


class _ListaSekcji(QWidget):
    """Wnetrze przewijanego panelu; przyjmuje upuszczane sekcje."""

    def __init__(self, panel: "PanelSekcji"):
        super().__init__()
        self._panel = panel
        self.setAcceptDrops(True)
        self.uklad_pionowy = _UkladListy(self)
        self.uklad_pionowy.setContentsMargins(10, 0, 10, 4)
        self.uklad_pionowy.setSpacing(0)
        self.kreska = QFrame(self)
        self.kreska.setObjectName("dropLine")
        self.kreska.hide()

    def _cel(self, y: int) -> tuple[str | None, int]:
        """Przed ktora sekcje wstawic i gdzie narysowac kreske."""
        widoczne = [s for s in self._panel.sekcje if s.isVisible()]
        for sekcja in widoczne:
            g = sekcja.geometry()
            if y < g.center().y():
                return sekcja.klucz, g.top()
        return None, (widoczne[-1].geometry().bottom() + 1) if widoczne else 0

    def _przyjmie(self, event) -> bool:
        return event.mimeData().hasFormat(MIME) and self._panel.odblokowany()

    def dragEnterEvent(self, event) -> None:
        if self._przyjmie(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if not self._przyjmie(event):
            return
        _, y = self._cel(event.position().toPoint().y())
        self.kreska.setGeometry(6, max(0, y - 1), self.width() - 12, 2)
        self.kreska.raise_()
        self.kreska.show()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self.kreska.hide()

    def dropEvent(self, event) -> None:
        self.kreska.hide()
        if not self._przyjmie(event):
            return
        klucz = bytes(event.mimeData().data(MIME)).decode("ascii")
        przed, _ = self._cel(event.position().toPoint().y())
        event.acceptProposedAction()
        if przed != klucz:
            self._panel.uklad.przenies(klucz, self._panel.miejsce, przed)


class PanelSekcji(QWidget):
    """Jeden panel boczny: pasek z klodka, opcjonalny staly wiersz i lista
    sekcji, ktora przewija sie we wlasnym obszarze."""

    def __init__(self, miejsce: str, uklad: "UkladPaneli", staly: QWidget | None = None):
        super().__init__()
        self.miejsce = miejsce
        self.uklad = uklad
        self.sekcje: list[Sekcja] = []

        self.klodka = QToolButton()
        self.klodka.setObjectName("panelLock")
        self.klodka.setCheckable(True)
        self.klodka.setIconSize(QSize(16, 16))
        self.klodka.setIcon(ikona("lock"))
        podpowiedz(self.klodka, "panele.klodka")
        self.klodka.toggled.connect(lambda on: uklad.ustaw_blokade(miejsce, on))

        self.lista = _ListaSekcji(self)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.lista)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Staly wiersz (Automatycznie | Wyzeruj) dzieli pasek z klodka. Panel
        # bez takiego wiersza nie dostaje paska wcale: klodka unosi sie w rogu,
        # na wysokosci naglowka pierwszej sekcji. Osobny wiersz na sama klodke
        # kosztowal 36 px i przy 1080p wypychal przyciski rozwinietych
        # metadanych pod krawedz lewego panelu.
        self._plywajaca = staly is None
        if staly is not None:
            gora = QHBoxLayout()
            gora.setContentsMargins(10, 8, 10, 2)
            gora.setSpacing(6)
            gora.addWidget(staly, 1)
            gora.addWidget(self.klodka)
            layout.addLayout(gora)
        else:
            self.klodka.setParent(self)
            self.scroll.verticalScrollBar().rangeChanged.connect(self._ustaw_klodke)
        layout.addWidget(self.scroll, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._ustaw_klodke()

    def _ustaw_klodke(self, *_args) -> None:
        if not self._plywajaca:
            return
        rozmiar = self.klodka.sizeHint()
        # prawa krawedz tresci, a nie panelu - pasek przewijania ja przesuwa
        prawo = self.scroll.viewport().width() - 10
        self.klodka.setGeometry(prawo - rozmiar.width(), 3, rozmiar.width(), rozmiar.height())
        self.klodka.raise_()

    def odblokowany(self) -> bool:
        return self.klodka.isChecked()

    def set_odblokowany(self, on: bool) -> None:
        self.klodka.blockSignals(True)
        self.klodka.setChecked(on)
        self.klodka.blockSignals(False)
        self.klodka.setIcon(ikona("unlock" if on else "lock"))

    def uloz(self, sekcje: list[Sekcja]) -> None:
        """Wklada sekcje w podanej kolejnosci; widgetow nie niszczy."""
        uklad = self.lista.uklad_pionowy
        while uklad.count():
            uklad.takeAt(0)
        self.sekcje = list(sekcje)
        for sekcja in sekcje:
            # setParent chowa widget, wiec widocznosc ustawiamy dopiero potem
            if sekcja.parentWidget() is not self.lista:
                sekcja.setParent(self.lista)
            uklad.addWidget(sekcja)
            sekcja.show()
        uklad.addStretch(1)
        self.rozloz_miejsce()

    def rozloz_miejsce(self) -> None:
        uklad = self.lista.uklad_pionowy
        ktos_chce = False
        for i, sekcja in enumerate(self.sekcje):
            chce = sekcja.chce_miejsca() and not sekcja.isHidden()
            ktos_chce |= chce
            uklad.setStretch(i, 1 if chce else 0)
        uklad.setStretch(len(self.sekcje), 0 if ktos_chce else 1)


class UkladPaneli(QObject):
    """Wlasciciel stanu ukladu: kto lezy w ktorym panelu (albo w schowku),
    co zwiniete, ktory panel odblokowany. Widzety tylko go pokazuja."""

    zmieniony = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sekcje: dict[str, Sekcja] = {}
        self.panele: dict[str, PanelSekcji] = {}
        # Sekcje ze schowka musza miec rodzica - bez niego Qt zrobilby
        # z nich osobne okna.
        self._magazyn = QWidget()
        self._magazyn.hide()
        self.stan = uporzadkuj({})

    # --- budowa -------------------------------------------------------

    def dodaj_sekcje(self, klucz: str, tresc: QWidget) -> Sekcja:
        sekcja = Sekcja(klucz, tresc, self)
        sekcja.setParent(self._magazyn)
        sekcja.rozciaganie_zmienione.connect(self._rozloz)
        self.sekcje[klucz] = sekcja
        return sekcja

    def utworz_panel(self, miejsce: str, staly: QWidget | None = None) -> PanelSekcji:
        panel = PanelSekcji(miejsce, self, staly)
        self.panele[miejsce] = panel
        return panel

    def zastosuj(self, stan) -> None:
        self.stan = uporzadkuj(stan)
        self._odswiez()

    def do_zapisu(self) -> dict:
        return {k: list(v) for k, v in self.stan.items()}

    # --- zmiany -------------------------------------------------------

    def przelacz_zwiniecie(self, klucz: str) -> None:
        self._przelacz("zwiniete", klucz)

    def przelacz_widocznosc(self, klucz: str) -> None:
        """Wylaczenie = odlozenie do schowka; wlaczenie = powrot na domyslne
        miejsce. Jedna zasada dla menu i okna ukladu - bez osobnego stanu
        "ukryta, ale w panelu", ktory w oknie wymagal pol wyboru."""
        if klucz in self.stan[SCHOWEK]:
            wstaw_domyslnie(self.stan, klucz)
        else:
            przenies(self.stan, klucz, SCHOWEK)
        self._zmiana()

    def ustaw_blokade(self, miejsce: str, odblokowany: bool) -> None:
        zbior = set(self.stan["odblokowane"])
        zbior.add(miejsce) if odblokowany else zbior.discard(miejsce)
        self.stan["odblokowane"] = sorted(zbior)
        self._zmiana()

    def przenies(self, klucz: str, cel: str, przed: str | None = None) -> None:
        przenies(self.stan, klucz, cel, przed)
        self._zmiana()

    def przywroc_domyslny(self) -> None:
        # Blokada to stan pracy, nie ukladu - zostaje, jak byla.
        odblokowane = self.stan["odblokowane"]
        self.stan = uporzadkuj({"odblokowane": odblokowane})
        self._zmiana()

    def _przelacz(self, nazwa: str, klucz: str) -> None:
        zbior = set(self.stan[nazwa])
        zbior.symmetric_difference_update({klucz})
        self.stan[nazwa] = sorted(zbior)
        self._zmiana()

    def _zmiana(self) -> None:
        self._odswiez()
        self.zmieniony.emit()

    def _odswiez(self) -> None:
        zwiniete = set(self.stan["zwiniete"])
        for miejsce, panel in self.panele.items():
            odblokowany = miejsce in self.stan["odblokowane"]
            sekcje = [self.sekcje[k] for k in self.stan[miejsce] if k in self.sekcje]
            for sekcja in sekcje:
                sekcja.set_zwinieta(sekcja.klucz in zwiniete)
                sekcja.set_przesuwalna(odblokowany)
            panel.uloz(sekcje)
            panel.set_odblokowany(odblokowany)
        for klucz in self.stan[SCHOWEK]:
            sekcja = self.sekcje.get(klucz)
            if sekcja is not None and sekcja.parentWidget() is not self._magazyn:
                sekcja.setParent(self._magazyn)

    def _rozloz(self) -> None:
        for panel in self.panele.values():
            panel.rozloz_miejsce()

    # --- menu i okno --------------------------------------------------

    def wypelnij_menu(self, menu: QMenu, okno: QWidget | None = None) -> None:
        """Widok > Panele: codzienne pokaz/ukryj jednym kliknieciem."""
        menu.clear()
        for miejsce in MIEJSCA:
            if not self.stan[miejsce]:
                continue
            naglowek = QAction(t(TYTULY_MIEJSC[miejsce]), menu)
            naglowek.setEnabled(False)
            menu.addAction(naglowek)
            for klucz in self.stan[miejsce]:
                akcja = QAction(t(TYTULY[klucz]), menu)
                akcja.setCheckable(True)
                akcja.setChecked(miejsce != SCHOWEK)
                akcja.triggered.connect(lambda _=False, k=klucz: self.przelacz_widocznosc(k))
                menu.addAction(akcja)
            menu.addSeparator()
        dostosuj = QAction(t("Dostosuj układ…"), menu)
        dostosuj.triggered.connect(lambda: self.otworz_okno(okno))
        menu.addAction(dostosuj)
        domyslny = QAction(t("Przywróć układ domyślny"), menu)
        domyslny.triggered.connect(self.przywroc_domyslny)
        menu.addAction(domyslny)

    def pokaz_menu(self, pozycja, okno: QWidget | None = None) -> None:
        menu = QMenu(okno)
        self.wypelnij_menu(menu, okno)
        menu.exec(pozycja)

    def otworz_okno(self, okno: QWidget | None = None) -> bool:
        dialog = OknoUkladu(self.stan, okno)
        if dialog.exec() != QDialog.Accepted:
            return False
        self.przyjmij(dialog.wynik())
        return True

    def przyjmij(self, nowy: dict) -> None:
        """Uklad z okna; zwiniecie i blokada zostaja z biezacego stanu."""
        nowy = dict(nowy)
        nowy["zwiniete"] = self.stan["zwiniete"]
        nowy["odblokowane"] = self.stan["odblokowane"]
        self.stan = uporzadkuj(nowy)
        self._zmiana()


class OknoUkladu(QDialog):
    """Trzy kolumny: schowek | panel lewy | panel prawy. Pozycje przeciaga
    sie miedzy kolumnami i w ich obrebie. Wylaczenie sekcji = przeniesienie
    do schowka; pol wyboru celowo nie ma (decyzja uzytkownika)."""

    def __init__(self, stan: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Dostosuj układ paneli"))
        self.listy: dict[str, QListWidget] = {}

        siatka = QGridLayout()
        siatka.setHorizontalSpacing(10)
        for kolumna, (miejsce, dymek) in enumerate((
            (SCHOWEK, "panele.okno_schowek"),
            (LEWY, "panele.okno_lewy"),
            (PRAWY, "panele.okno_prawy"),
        )):
            tytul = QLabel(t(TYTULY_MIEJSC[miejsce]).upper())
            tytul.setObjectName("sectionTitle")
            lista = QListWidget()
            lista.setObjectName("layoutColumn")
            lista.setDragDropMode(QAbstractItemView.DragDrop)
            lista.setDefaultDropAction(Qt.MoveAction)
            lista.setSelectionMode(QAbstractItemView.SingleSelection)
            lista.setMinimumSize(190, 300)
            podpowiedz(lista, dymek)
            self.listy[miejsce] = lista
            siatka.addWidget(tytul, 0, kolumna)
            siatka.addWidget(lista, 1, kolumna)

        przyciski = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        przyciski.button(QDialogButtonBox.Ok).setText(t("OK"))
        przyciski.button(QDialogButtonBox.Cancel).setText(t("Anuluj"))
        domyslny = przyciski.button(QDialogButtonBox.RestoreDefaults)
        domyslny.setText(t("Przywróć układ domyślny"))
        podpowiedz(domyslny, "panele.okno_domyslny")
        domyslny.clicked.connect(lambda: self.wypelnij(uporzadkuj({})))
        przyciski.accepted.connect(self.accept)
        przyciski.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(siatka)
        layout.addWidget(przyciski)
        self.wypelnij(stan)

    def wypelnij(self, stan: dict) -> None:
        for miejsce, lista in self.listy.items():
            lista.clear()
            for klucz in stan[miejsce]:
                pozycja = QListWidgetItem(t(TYTULY[klucz]))
                pozycja.setData(Qt.UserRole, klucz)
                # QListWidgetItem ma domyslnie flage "do zaznaczania"
                pozycja.setFlags(pozycja.flags() & ~Qt.ItemIsUserCheckable)
                lista.addItem(pozycja)

    def wynik(self) -> dict:
        stan: dict[str, list[str]] = {m: [] for m in MIEJSCA}
        for miejsce, lista in self.listy.items():
            for i in range(lista.count()):
                stan[miejsce].append(lista.item(i).data(Qt.UserRole))
        return stan
