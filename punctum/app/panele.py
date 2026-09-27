"""Panele boczne okna Edycji zlozone z sekcji.

Sekcje mozna zwijac, ukrywac, przestawiac w obrebie panelu i przenosic
miedzy panelami (albo do schowka). Stan ukladu lezy w ustawieniach pod
stalymi kluczami sekcji - nie pod ich nazwami, bo nazwy sa przetlumaczone
i zmiana jezyka rozsypalaby zapisany uklad.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QMimeData, QObject, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QDrag, QIcon
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
    QSizePolicy,
    QSpacerItem,
    QStyle,
    QStyledItemDelegate,
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
# Grupy w panelu (punkt 30 C): przypiete u gory, przewijana reszta (None),
# przypiete u dolu. Lista sekcji panelu trzyma je zawsze w tej kolejnosci.
GORA, DOL = "gora", "dol"
GRUPY = (GORA, None, DOL)
# Tyle zostaje czesci przewijanej, nawet gdy przypiete chca wiecej - inaczej
# duza przypieta sekcja zjadlaby caly panel i reszta bylaby nieosiagalna.
MIN_PRZEWIJANEJ = 120

# Kolejnosc slownika = kolejnosc w ukladzie domyslnym i w oknie ukladu.
TYTULY = {
    "nawigator": N_("Nawigator"),
    # Klucz zostaje stary, zeby zapisane uklady dalej trafialy. Przyciski
    # przed/po mieszkaja tu od 19 - sekcja "przed_po" zniknela, a jej
    # klucz w starym zapisie po prostu odpada.
    "powiekszenie": N_("Powiększenie i porównanie"),
    "dane": N_("Dane zdjęcia"),
    "presety": N_("Presety"),
    "histogram": N_("Histogram"),
    "kadrowanie": N_("Kadrowanie i obrót"),
    "balans": N_("Balans bieli"),
    # Klucze "ton", "obecnosc" i "wyostrzanie" zostaja z zapisanych ukladow;
    # zmienily sie tylko nazwy na ekranie (wlasne, nie zapozyczone).
    "ton": N_("Światło"),
    "obecnosc": N_("Kolor"),
    "monochrom": N_("Monochrom"),
    "wyostrzanie": N_("Ostrość"),
    "szum": N_("Usuwanie szumu"),
}

UKLAD_DOMYSLNY = {
    LEWY: ["nawigator", "powiekszenie", "dane", "presety"],
    PRAWY: ["histogram", "kadrowanie", "balans", "ton", "obecnosc", "monochrom",
            "wyostrzanie", "szum"],
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
    # Przypiete tylko sekcje lezace w panelu; przypiecie sekcji ze schowka
    # nie ma znaczenia (odlozenie do schowka = odpiecie).
    w_panelach = set(wynik[LEWY]) | set(wynik[PRAWY])
    przypiete = stan.get("przypiete")
    wynik["przypiete"] = {
        k: v for k, v in sorted(przypiete.items())
        if k in w_panelach and v in (GORA, DOL)
    } if isinstance(przypiete, dict) else {}
    for miejsce in PANELE:
        wyrownaj(wynik, miejsce)
    return wynik


def grupa(stan: dict, klucz: str) -> str | None:
    return stan.get("przypiete", {}).get(klucz)


def wyrownaj(stan: dict, miejsce: str) -> None:
    """Przypiete u gory na poczatek, u dolu na koniec; kolejnosc w obrebie
    grupy zostaje. Dzieki temu kazda zmiana moze wstawic sekcje byle gdzie,
    a panel i tak dostaje trzy spojne grupy."""
    lista = stan[miejsce]
    lista[:] = [k for g in GRUPY for k in lista if grupa(stan, k) == g]


def przypnij(stan: dict, klucz: str, gdzie: str) -> None:
    """Przypina sekcje pod ostatnia przypieta w tej grupie."""
    miejsce = next((m for m in PANELE if klucz in stan[m]), None)
    if miejsce is not None:
        przenies(stan, klucz, miejsce, None, gdzie)


def odepnij(stan: dict, klucz: str) -> None:
    """Odpieta z gory staje sie pierwsza w czesci przewijanej, z dolu -
    ostatnia; w obu razach zostaje tuz przy miejscu, w ktorym byla."""
    miejsce = next((m for m in PANELE if klucz in stan[m]), None)
    stara = grupa(stan, klucz)
    if miejsce is None or stara is None:
        return
    przed = None
    if stara == GORA:
        przed = next((k for k in stan[miejsce] if k != klucz and grupa(stan, k) is None), None)
        if przed is None:
            przed = next((k for k in stan[miejsce] if grupa(stan, k) == DOL), None)
    przenies(stan, klucz, miejsce, przed, None)


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
    stan.get("przypiete", {}).pop(klucz, None)
    stan[miejsce].insert(pozycja, klucz)
    wyrownaj(stan, miejsce)


def przenies(stan: dict, klucz: str, cel: str, przed: str | None = None,
             gdzie: str | None = None) -> None:
    """Przenosi sekcje do `cel`, do grupy `gdzie` (None = czesc przewijana),
    przed sekcje `przed` (None = na koniec tej grupy). Przeniesienie zawsze
    ustala przypiecie na nowo - do schowka nic przypietego nie trafia."""
    for miejsce in MIEJSCA:
        if klucz in stan[miejsce]:
            stan[miejsce].remove(klucz)
    przypiete = stan.setdefault("przypiete", {})
    przypiete.pop(klucz, None)
    if cel in PANELE and gdzie in (GORA, DOL):
        przypiete[klucz] = gdzie
    else:
        gdzie = None
    lista = stan[cel]
    if przed in lista:
        pozycja = lista.index(przed)
    else:
        # koniec grupy = przed pierwsza sekcja ktorejs z dalszych grup
        dalsze = GRUPY[GRUPY.index(gdzie) + 1:]
        pozycja = next((i for i, k in enumerate(lista) if grupa(stan, k) in dalsze), len(lista))
    lista.insert(pozycja, klucz)
    if cel in PANELE:
        wyrownaj(stan, cel)


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

        # Przypinanie (punkt 30 C). "Przypnij" pokazuje sie dopiero po
        # najechaniu, zeby dwadziescia par ikon nie zasmiecalo paneli;
        # "odepnij" na przypietej widac zawsze - to jedyny slad, ze sekcja
        # nie przewija sie z reszta (decyzja uzytkownika).
        self._grupa: str | None = None
        self._najechany = False
        uklad = sekcja.uklad
        self.przypnij_gore = self._przycisk(
            "pin-top", lambda: uklad.przypnij(sekcja.klucz, GORA))
        podpowiedz(self.przypnij_gore, "panele.przypnij_gore")
        self.przypnij_dol = self._przycisk(
            "pin-bottom", lambda: uklad.przypnij(sekcja.klucz, DOL))
        podpowiedz(self.przypnij_dol, "panele.przypnij_dol")
        self.odepnij = self._przycisk("unpin", lambda: uklad.odepnij(sekcja.klucz))
        podpowiedz(self.odepnij, "panele.odepnij")
        # Miejsce na plywajaca klodke, gdy ta sekcja stoi w panelu pierwsza.
        self._zapas = QSpacerItem(0, 0, QSizePolicy.Fixed, QSizePolicy.Minimum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 2)
        layout.setSpacing(4)
        layout.addWidget(self.uchwyt)
        layout.addWidget(self.strzalka)
        layout.addWidget(self.tytul, 1)
        layout.addWidget(self.przypnij_gore)
        layout.addWidget(self.przypnij_dol)
        layout.addWidget(self.odepnij)
        layout.addItem(self._zapas)

    def _przycisk(self, nazwa: str, akcja) -> QToolButton:
        przycisk = QToolButton()
        przycisk.setObjectName("sectionPin")
        przycisk.setAutoRaise(True)
        # tyle co strzalka zwijania - pojawienie sie po najechaniu nie moze
        # zmieniac wysokosci belki, bo panel podskakiwalby pod kursorem
        przycisk.setFixedSize(16, 16)
        przycisk.setIconSize(QSize(12, 12))
        przycisk.setIcon(ikona(nazwa))
        przycisk.clicked.connect(akcja)
        przycisk.hide()
        return przycisk

    def set_grupa(self, grupa: str | None) -> None:
        self._grupa = grupa
        self._pokaz_przyciski()

    def set_zapas(self, szerokosc: int) -> None:
        if self._zapas.sizeHint().width() != szerokosc:
            self._zapas.changeSize(szerokosc, 0, QSizePolicy.Fixed, QSizePolicy.Minimum)
            self.layout().invalidate()

    def _pokaz_przyciski(self) -> None:
        wolna = self._grupa is None
        self.przypnij_gore.setVisible(wolna and self._najechany)
        self.przypnij_dol.setVisible(wolna and self._najechany)
        self.odepnij.setVisible(not wolna)

    def enterEvent(self, event) -> None:
        self._najechany = True
        self._pokaz_przyciski()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._najechany = False
        self._pokaz_przyciski()
        super().leaveEvent(event)

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

    def __init__(self, klucz: str, tresc: QWidget, uklad: "UkladPaneli"):
        super().__init__()
        self.setObjectName("panelSection")
        self.klucz = klucz
        self.tresc = tresc
        self.uklad = uklad
        self.zwinieta = False
        self.przesuwalna = False

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

    def set_przesuwalna(self, on: bool) -> None:
        self.przesuwalna = on
        self.naglowek.set_przesuwalny(on)


class _ListaSekcji(QWidget):
    """Wnetrze jednej grupy panelu (przypiete u gory, przewijana reszta,
    przypiete u dolu); przyjmuje upuszczane sekcje. Upuszczenie w grupie
    przypietej przypina - te same zasady co przyciski na belce."""

    def __init__(self, panel: "PanelSekcji", grupa: str | None):
        super().__init__()
        self._panel = panel
        self.grupa = grupa
        self.sekcje: list[Sekcja] = []
        self.setAcceptDrops(True)
        # Zwykly uklad, z wysokoscia zalezna od szerokosci: QScrollArea daje
        # wtedy tresci pelna wysokosc, a nie minimalna. Punkt 30 - sekcje
        # nie maja wlasnych paskow i nie sa sciskane, przewija sie caly panel
        # (dawniej sciskanie bylo celowe i rozwiniete metadane oraz lista
        # presetow dostawaly po kilka wierszy z wlasnym paskiem).
        self.uklad_pionowy = QVBoxLayout(self)
        self.uklad_pionowy.setContentsMargins(10, 0, 10, 4 if grupa is None else 0)
        self.uklad_pionowy.setSpacing(0)
        self.kreska = QFrame(self)
        self.kreska.setObjectName("dropLine")
        self.kreska.hide()

    def eventFilter(self, obiekt, event) -> bool:
        # Zmiana tresci sekcji (zwiniecie, rozwiniete metadane) przychodzi
        # do niej jako LayoutRequest - grupa przypieta musi wtedy zmienic
        # wysokosc. Po powrocie do petli, gdy sekcja zna juz nowy rozmiar.
        if event.type() == QEvent.LayoutRequest and self.grupa is not None:
            QTimer.singleShot(0, self._panel.dopasuj_przypiete)
        return False

    def uloz(self, sekcje: list[Sekcja]) -> None:
        """Wklada sekcje w podanej kolejnosci; widgetow nie niszczy."""
        uklad = self.uklad_pionowy
        while uklad.count():
            uklad.takeAt(0)
        self.sekcje = list(sekcje)
        for sekcja in sekcje:
            # setParent chowa widget, wiec widocznosc ustawiamy dopiero potem
            if sekcja.parentWidget() is not self:
                sekcja.setParent(self)
            # filtr zostaje po przeniesieniu do innej grupy, ale tam tylko
            # przelicza wysokosci przypietych - nic nie psuje
            if self.grupa is not None:
                sekcja.installEventFilter(self)
            uklad.addWidget(sekcja)
            sekcja.show()
        if self.grupa is None:
            uklad.addStretch(1)

    def _cel(self, y: int) -> tuple[str | None, int]:
        """Przed ktora sekcje wstawic i gdzie narysowac kreske."""
        widoczne = [s for s in self.sekcje if s.isVisible()]
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
            self._panel.uklad.przenies(klucz, self._panel.miejsce, przed, self.grupa)


class _Przypiete(QScrollArea):
    """Grupa przypieta: tak wysoka jak jej tresc. Wlasny pasek pojawia sie
    tylko wtedy, gdy przypiete nie mieszcza sie obok czesci przewijanej."""

    def __init__(self, lista: _ListaSekcji):
        super().__init__()
        self.lista = lista
        self.setObjectName("pinnedGroup")
        self.setWidget(lista)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._wysokosc = 0
        self.hide()

    def tresc(self) -> int:
        # Suma sekcji zamiast heightForWidth calej listy: ta druga bywa
        # nieaktualna po zwinieciu czegos wewnatrz sekcji (lista trzyma
        # stara wysokosc, dopoki sama nie dostanie nowego ukladu).
        marginesy = self.lista.uklad_pionowy.contentsMargins()
        szerokosc = self.viewport().width() - marginesy.left() - marginesy.right()
        suma = marginesy.top() + marginesy.bottom()
        for sekcja in self.lista.sekcje:
            if sekcja.isHidden():
                continue
            wysokosc = sekcja.heightForWidth(szerokosc) if sekcja.hasHeightForWidth() else -1
            suma += wysokosc if wysokosc > 0 else sekcja.sizeHint().height()
        return suma

    def dopasuj(self) -> None:
        wysokosc = self.tresc()
        if wysokosc != self._wysokosc:
            self._wysokosc = wysokosc
            self.setMaximumHeight(wysokosc)
            self.updateGeometry()

    def sizeHint(self) -> QSize:
        # QScrollArea sam z siebie przycina podpowiedz do kilkunastu wierszy
        return QSize(super().sizeHint().width(), self._wysokosc)

    def minimumSizeHint(self) -> QSize:
        # grupe mozna scisnac do samej belki pierwszej sekcji - reszta
        # dostaje wtedy pasek, ale panel nie wypycha okna poza ekran
        belka = self.lista.sekcje[0].naglowek.sizeHint().height() if self.lista.sekcje else 0
        return QSize(0, min(self._wysokosc, belka + 8))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.dopasuj()


class PanelSekcji(QWidget):
    """Jeden panel boczny: pasek z klodka, opcjonalny staly wiersz, sekcje
    przypiete u gory, lista przewijana we wlasnym obszarze i sekcje
    przypiete u dolu (punkt 30 C)."""

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

        self.lista = _ListaSekcji(self, None)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.lista)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(MIN_PRZEWIJANEJ)
        self.gora = _Przypiete(_ListaSekcji(self, GORA))
        self.dol = _Przypiete(_ListaSekcji(self, DOL))
        self.grupy = {GORA: self.gora.lista, None: self.lista, DOL: self.dol.lista}

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
        # Kreski oddzielaja przypiete od przewijanej reszty - bez nich nie
        # widac, gdzie konczy sie to, co stoi w miejscu.
        self.kreska_gora = self._kreska()
        self.kreska_dol = self._kreska()
        layout.addWidget(self.gora)
        layout.addWidget(self.kreska_gora)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.kreska_dol)
        layout.addWidget(self.dol)

    @staticmethod
    def _kreska() -> QFrame:
        kreska = QFrame()
        kreska.setObjectName("pinDivider")
        kreska.setFixedHeight(1)
        kreska.hide()
        return kreska

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._ustaw_klodke()

    def _ustaw_klodke(self, *_args) -> None:
        if not self._plywajaca:
            return
        rozmiar = self.klodka.sizeHint()
        # prawa krawedz tresci, a nie panelu - pasek przewijania ja przesuwa
        pierwsza = self.gora if self.gora.lista.sekcje else self.scroll
        prawo = pierwsza.viewport().width() - 10
        self.klodka.setGeometry(prawo - rozmiar.width(), 3, rozmiar.width(), rozmiar.height())
        self.klodka.raise_()

    def dopasuj_przypiete(self) -> None:
        self.gora.dopasuj()
        self.dol.dopasuj()

    def odblokowany(self) -> bool:
        return self.klodka.isChecked()

    def set_odblokowany(self, on: bool) -> None:
        self.klodka.blockSignals(True)
        self.klodka.setChecked(on)
        self.klodka.blockSignals(False)
        self.klodka.setIcon(ikona("unlock" if on else "lock"))

    def uloz(self, sekcje: list[Sekcja], grupy: dict | None = None) -> None:
        """Rozdziela sekcje na grupy wedlug `grupy` {klucz: gora|dol}."""
        grupy = grupy or {}
        self.sekcje = list(sekcje)
        for g, lista in self.grupy.items():
            lista.uloz([s for s in sekcje if grupy.get(s.klucz) == g])
        for przypiete, kreska in ((self.gora, self.kreska_gora), (self.dol, self.kreska_dol)):
            przypiete.setVisible(bool(przypiete.lista.sekcje))
            kreska.setVisible(bool(przypiete.lista.sekcje))
        # Plywajaca klodka zaslania prawy koniec belki pierwszej sekcji -
        # tam siedza przyciski przypinania, wiec ta belka robi jej miejsce.
        for i, sekcja in enumerate(sekcje):
            zapas = self.klodka.sizeHint().width() + 2 if self._plywajaca and i == 0 else 0
            sekcja.naglowek.set_zapas(zapas)
        self.dopasuj_przypiete()
        self._ustaw_klodke()


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
        return {k: dict(v) if isinstance(v, dict) else list(v) for k, v in self.stan.items()}

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

    def przenies(self, klucz: str, cel: str, przed: str | None = None,
                 gdzie: str | None = None) -> None:
        przenies(self.stan, klucz, cel, przed, gdzie)
        self._zmiana()

    def przypnij(self, klucz: str, gdzie: str) -> None:
        przypnij(self.stan, klucz, gdzie)
        self._zmiana()

    def odepnij(self, klucz: str) -> None:
        odepnij(self.stan, klucz)
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
                sekcja.naglowek.set_grupa(self.stan["przypiete"].get(sekcja.klucz))
            panel.uloz(sekcje, self.stan["przypiete"])
            panel.set_odblokowany(odblokowany)
        for klucz in self.stan[SCHOWEK]:
            sekcja = self.sekcje.get(klucz)
            if sekcja is not None and sekcja.parentWidget() is not self._magazyn:
                sekcja.setParent(self._magazyn)

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


ROLA_GRUPY = Qt.UserRole + 1


class _DelegatPrzypiec(QStyledItemDelegate):
    """Przyciski przypinania przy pozycjach kolumn paneli w oknie ukladu -
    te same co na belce sekcji: "przypnij" po najechaniu, na przypietej
    znak grupy i "odepnij" zawsze. Rysowane przez delegata, bo widzety
    wstawione w wiersze (setItemWidget) gubia sie przy przeciaganiu."""

    ROZMIAR = 16

    def __init__(self, okno: "OknoUkladu", miejsce: str):
        super().__init__(okno)
        self._okno = okno
        self._miejsce = miejsce

    def _przyciski(self, rect: QRect, grupa: str | None, najechany: bool):
        """[(prostokat, ikona, akcja albo None)] od lewej do prawej."""
        if grupa is None:
            if not najechany:
                return []
            nazwy = (("pin-top", GORA), ("pin-bottom", DOL))
        else:
            nazwy = (("pin-top" if grupa == GORA else "pin-bottom", None), ("unpin", "odepnij"))
        r, wynik = self.ROZMIAR, []
        x = rect.right() - 4 - len(nazwy) * (r + 2)
        for nazwa, akcja in nazwy:
            wynik.append((QRect(x, rect.center().y() - r // 2, r, r), nazwa, akcja))
            x += r + 2
        return wynik

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        najechany = bool(option.state & QStyle.State_MouseOver)
        for prostokat, nazwa, akcja in self._przyciski(
            option.rect, index.data(ROLA_GRUPY), najechany
        ):
            # znak grupy (bez akcji) przygaszony - to nie przycisk
            tryb = QIcon.Disabled if akcja is None else QIcon.Normal
            ikona(nazwa).paint(painter, prostokat.adjusted(2, 2, -2, -2), Qt.AlignCenter, tryb)

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            return super().editorEvent(event, model, option, index)
        pozycja = event.position().toPoint()
        for prostokat, _, akcja in self._przyciski(option.rect, index.data(ROLA_GRUPY), True):
            if akcja is not None and prostokat.contains(pozycja):
                # nacisk tez polykamy, zeby klik w przycisk nie zaczynal
                # przeciagania ani nie zaznaczal wiersza
                if event.type() == QEvent.MouseButtonRelease:
                    klucz = index.data(Qt.UserRole)
                    QTimer.singleShot(0, lambda: self._okno.przypnij(klucz, akcja))
                return True
        return super().editorEvent(event, model, option, index)


class OknoUkladu(QDialog):
    """Trzy kolumny: schowek | panel lewy | panel prawy. Pozycje przeciaga
    sie miedzy kolumnami i w ich obrebie. Wylaczenie sekcji = przeniesienie
    do schowka; pol wyboru celowo nie ma (decyzja uzytkownika). Przy
    pozycjach paneli przyciski przypinania (punkt 30 C)."""

    def __init__(self, stan: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Dostosuj układ paneli"))
        self.listy: dict[str, QListWidget] = {}
        self._wypelniam = False

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
            # w kolumnach paneli po prawej stronie wiersza stoja przyciski
            lista.setMinimumSize(190 if miejsce == SCHOWEK else 240, 300)
            if miejsce in PANELE:
                lista.setMouseTracking(True)
                lista.viewport().setAttribute(Qt.WA_Hover)
                lista.setItemDelegate(_DelegatPrzypiec(self, miejsce))
            # Upuszczona pozycja moze wpasc miedzy przypiete - po kazdym
            # upuszczeniu kolumny wyrownuja sie tak, jak zrobi to panel.
            lista.model().rowsInserted.connect(
                lambda *_: None if self._wypelniam else QTimer.singleShot(0, self._wyrownaj))
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
        przypiete = stan.get("przypiete", {})
        self._wypelniam = True
        try:
            for miejsce, lista in self.listy.items():
                lista.clear()
                for klucz in stan[miejsce]:
                    pozycja = QListWidgetItem(t(TYTULY[klucz]))
                    pozycja.setData(Qt.UserRole, klucz)
                    if miejsce in PANELE:
                        pozycja.setData(ROLA_GRUPY, przypiete.get(klucz))
                    # QListWidgetItem ma domyslnie flage "do zaznaczania"
                    pozycja.setFlags(pozycja.flags() & ~Qt.ItemIsUserCheckable)
                    lista.addItem(pozycja)
        finally:
            self._wypelniam = False

    def _wyrownaj(self) -> None:
        stan = self.wynik()
        schowek = self.listy[SCHOWEK]
        rozjechane = any(
            stan[m] != [k for g in GRUPY for k in stan[m] if stan["przypiete"].get(k) == g]
            for m in PANELE
        ) or any(schowek.item(i).data(ROLA_GRUPY) for i in range(schowek.count()))
        if rozjechane:
            for miejsce in PANELE:
                wyrownaj(stan, miejsce)
            self.wypelnij(stan)

    def przypnij(self, klucz: str, akcja: str) -> None:
        stan = self.wynik()
        if akcja == "odepnij":
            odepnij(stan, klucz)
        else:
            przypnij(stan, klucz, akcja)
        self.wypelnij(stan)

    def wynik(self) -> dict:
        stan: dict = {m: [] for m in MIEJSCA}
        stan["przypiete"] = {}
        for miejsce, lista in self.listy.items():
            for i in range(lista.count()):
                pozycja = lista.item(i)
                klucz = pozycja.data(Qt.UserRole)
                stan[miejsce].append(klucz)
                grupa_ = pozycja.data(ROLA_GRUPY)
                if miejsce in PANELE and grupa_ in (GORA, DOL):
                    stan["przypiete"][klucz] = grupa_
        return stan
