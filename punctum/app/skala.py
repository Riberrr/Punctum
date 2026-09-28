"""Skala interfejsu (punkt 30 A) - zmieniana na zywo, bez ponownego uruchomienia.

Wbudowana skala Qt (QT_SCALE_FACTOR) dziala tylko przy starcie programu,
dlatego skalujemy sami, w trzech miejscach:

- arkusz stylow (`style.stylesheet()` przelicza w nim kazde "px"),
- metryki stylu - domyslne marginesy ukladow, odstepy, znaczniki pol wyboru
  (`metryka()`, wolana z nakladki na styl w podpowiedzi.py),
- wymiary wpisane w kod: funkcje `stala`, `minimum`, `ikony`, `marginesy`,
  `odstep` i ogolna `zarejestruj`. Kazda pamieta wartosc BAZOWA (przy 100 %)
  i przy zmianie skali liczy ja od nowa - wielokrotna zmiana nie kumuluje
  bledow zaokraglen, a wymiar ustawiony przed zmiana nie zostaje w starej skali.

Rysowanie wlasnych widzetow bierze wymiary przez `px()`/`pxf()` w chwili
rysowania, wiec samo przerysowanie wystarcza.

Podglad zdjecia skali nie podlega: 100 % to dalej piksel zdjecia na piksel
ekranu (ImageView liczy przez devicePixelRatio, ktorego ta skala nie rusza).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QSize, Signal
from PySide6.QtWidgets import QApplication, QStyle

try:
    from shiboken6 import isValid as _zywy
except ImportError:  # pragma: no cover - shiboken6 jest zawsze z PySide6
    def _zywy(_obiekt) -> bool:
        return True

_skala = 1.0
# Silne odwolania + sprawdzenie, czy obiekt C++ jeszcze zyje: slabe odwolanie
# do opakowania PySide potrafi zniknac, choc sam widzet dalej istnieje.
_rejestr: list[tuple[object, Callable]] = []
_PORZADKI_CO = 500  # co tyle rejestracji wyrzucamy martwe wpisy

# Metryki stylu, ktore rosna razem z interfejsem. Grubosci ramek i linii
# zostaja: jednopikselowa kreska przy 150 % ma dalej byc cienka.
_METRYKI = {
    getattr(QStyle.PixelMetric, nazwa)
    for nazwa in (
        "PM_LayoutLeftMargin", "PM_LayoutTopMargin", "PM_LayoutRightMargin",
        "PM_LayoutBottomMargin", "PM_LayoutHorizontalSpacing", "PM_LayoutVerticalSpacing",
        "PM_IndicatorWidth", "PM_IndicatorHeight",
        "PM_ExclusiveIndicatorWidth", "PM_ExclusiveIndicatorHeight",
        "PM_SmallIconSize", "PM_ButtonIconSize", "PM_ListViewIconSize",
        "PM_TabBarIconSize", "PM_ToolBarIconSize",
        "PM_ScrollBarExtent", "PM_ScrollBarSliderMin",
        "PM_SliderThickness", "PM_SliderLength", "PM_SliderControlThickness",
        "PM_MenuButtonIndicator", "PM_CheckBoxLabelSpacing",
        "PM_RadioButtonLabelSpacing", "PM_ButtonMargin",
    )
    if hasattr(QStyle.PixelMetric, nazwa)  # czesc nazw z Qt 5 w Qt 6 zniknela
}


class _Sygnaly(QObject):
    # Dla miejsc, ktore licza wymiary z czcionki albo z ustawien (np. szerokosci
    # paneli) - przeliczaja sie same po zmianie skali.
    zmieniona = Signal(float)


sygnaly = _Sygnaly()


def skala() -> float:
    return _skala


def px(n: float) -> int:
    """Wymiar bazowy (przy 100 %) w pikselach przy biezacej skali.

    Dodatni wymiar nie spada do zera - kreska 1 px przy 75 % ma zostac kreska.
    """
    if n <= 0:
        return int(n)
    return max(1, round(n * _skala))


def pxf(n: float) -> float:
    """Jak px(), ale bez zaokraglenia - do rysowania."""
    return n * _skala


def rozmiar(szer: float, wys: float) -> QSize:
    return QSize(px(szer), px(wys))


def metryka(metric, wartosc: int) -> int:
    if metric in _METRYKI and wartosc > 0:
        return px(wartosc)
    return wartosc


def zarejestruj(obiekt, funkcja: Callable) -> None:
    """`funkcja(obiekt)` ustawia wymiary obiektu wedlug biezacej skali.

    Wolana od razu i ponownie przy kazdej zmianie skali; obiekty usuniete
    przez Qt wypadaja z rejestru same.
    """
    funkcja(obiekt)
    _rejestr.append((obiekt, funkcja))
    if len(_rejestr) % _PORZADKI_CO == 0:
        _rejestr[:] = [(o, f) for o, f in _rejestr if _zywy(o)]


def stala(widget, szer: float | None = None, wys: float | None = None) -> None:
    """setFixedWidth/Height/Size z wymiarem bazowym."""
    def nastaw(w) -> None:
        if szer is not None:
            w.setFixedWidth(px(szer))
        if wys is not None:
            w.setFixedHeight(px(wys))
    zarejestruj(widget, nastaw)


def minimum(widget, szer: float | None = None, wys: float | None = None) -> None:
    def nastaw(w) -> None:
        if szer is not None:
            w.setMinimumWidth(px(szer))
        if wys is not None:
            w.setMinimumHeight(px(wys))
    zarejestruj(widget, nastaw)


def maksimum(widget, szer: float | None = None, wys: float | None = None) -> None:
    def nastaw(w) -> None:
        if szer is not None:
            w.setMaximumWidth(px(szer))
        if wys is not None:
            w.setMaximumHeight(px(wys))
    zarejestruj(widget, nastaw)


def ikony(widget, szer: float, wys: float | None = None) -> None:
    """setIconSize(QSize(...)) z wymiarem bazowym."""
    zarejestruj(widget, lambda w: w.setIconSize(rozmiar(szer, szer if wys is None else wys)))


def marginesy(uklad, lewy: float, gora: float, prawy: float, dol: float) -> None:
    zarejestruj(uklad, lambda u: u.setContentsMargins(px(lewy), px(gora), px(prawy), px(dol)))


def odstep(obiekt, n: float, kierunek: str = "") -> None:
    """setSpacing (uklad albo lista); kierunek "poziomo"/"pionowo" dla siatek i formularzy."""
    metoda = {"": "setSpacing", "poziomo": "setHorizontalSpacing",
              "pionowo": "setVerticalSpacing"}[kierunek]
    zarejestruj(obiekt, lambda o: getattr(o, metoda)(px(n)))


def zmien(nowa: float) -> None:
    """Zmienia skale i przelicza caly zarejestrowany interfejs."""
    global _skala
    nowa = float(nowa)
    if abs(nowa - _skala) < 1e-6:
        return
    _skala = nowa
    zywe = []
    for obiekt, funkcja in _rejestr:
        if _zywy(obiekt):
            funkcja(obiekt)
            zywe.append((obiekt, funkcja))
    _rejestr[:] = zywe
    sygnaly.zmieniona.emit(_skala)
    # Metryki stylu (domyslne marginesy i odstepy) uklady czytaja przy
    # przeliczaniu, a to po zmianie skali nie nastepuje samo z siebie.
    app = QApplication.instance()
    if app is not None:
        for widget in app.allWidgets():
            uklad = widget.layout()
            if uklad is not None:
                uklad.invalidate()
            widget.updateGeometry()
            widget.update()
