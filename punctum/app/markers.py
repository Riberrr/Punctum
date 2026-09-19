"""Znaczniki stanu zdjecia - wspolne dla paska miniatur i listy w mapie.

Dwie listy w dwoch zakladkach pokazuja te same pliki, wiec musza mowic tym
samym jezykiem. Znaczniki sa dwa i sa niezalezne:

    kropka   praca nad zdjeciem jest zapisana (sa nastawy w sidecarze)
    pinezka  zdjecie ma wspolrzedne (nadane u nas albo z aparatu)

Rysujemy je, a nie wpisujemy w nazwe pliku. Znak w tekscie przesuwal nazwy
w kazdym wierszu inaczej, przez co lista stawala sie nieczytelna, a rombu
uzytego wczesniej i tak nikt nie czytal jako "lokalizacja". Rysunek stoi
w stalym miejscu i nie zalezy od czcionki ani od strony kodowej.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

# Role danych w pozycjach list - obie listy trzymaja stan tak samo.
EDIT_ROLE = Qt.UserRole + 1
GEO_ROLE = Qt.UserRole + 2

EDIT_COLOR = QColor("#c9c9d2")
GEO_COLOR = QColor("#d9634f")  # ten sam pomysl na kolor, co pinezki na mapie

# Miejsce na oba znaczniki w liscie z nazwami (szerokosc kolumny w pikselach).
MARK_COLUMN = 26
PIN_SIZE = (11, 15)

LEGEND = (
    "Kropka — zdjęcie ma zapisane poprawki\n"
    "Pinezka — zdjęcie ma współrzędne"
)


def paint_dot(painter: QPainter, centre: QPointF, radius: float = 3.0,
              color: QColor = EDIT_COLOR) -> None:
    """Kropka: zapisana praca."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(centre, radius, radius)
    painter.restore()


def paint_pin(painter: QPainter, rect: QRectF, color: QColor = GEO_COLOR) -> None:
    """Pinezka: zdjecie ma wspolrzedne.

    Rysowana krzywymi, a nie znakiem z czcionki - emoji wyglada inaczej
    w kazdym systemie, a romb czy gwiazdka nic nie mowia.
    """
    head = min(rect.width(), rect.height() * 0.72)
    centre = QPointF(rect.center().x(), rect.top() + head / 2.0)

    path = QPainterPath()
    path.addEllipse(centre, head / 2.0, head / 2.0)
    body = QPainterPath()
    body.moveTo(centre.x() - head * 0.42, centre.y() + head * 0.26)
    body.lineTo(rect.center().x(), rect.bottom())
    body.lineTo(centre.x() + head * 0.42, centre.y() + head * 0.26)
    body.closeSubpath()
    path.addPath(body)
    path.setFillRule(Qt.WindingFill)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPath(path.simplified())
    # Oczko pinezki. Poltransparentna czern zamiast koloru tla - ta sama
    # pinezka lezy i na tle listy, i na jasnej miniaturze.
    painter.setBrush(QColor(0, 0, 0, 120))
    painter.drawEllipse(centre, head * 0.19, head * 0.19)
    painter.restore()


def paint_marks(painter: QPainter, rect: QRectF, edited: bool, located: bool) -> None:
    """Oba znaczniki w kolumnie o stalej szerokosci, po lewej stronie nazwy."""
    centre_y = rect.center().y()
    if edited:
        paint_dot(painter, QPointF(rect.left() + 5.0, centre_y))
    if located:
        width, height = PIN_SIZE
        paint_pin(
            painter,
            QRectF(rect.left() + 12.0, centre_y - height / 2.0, width, height),
        )
