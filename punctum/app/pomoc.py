"""Okno pomocy z tekstem w HTML, w jezyku interfejsu.

Dluzsze teksty pomocy leza w plikach `lang/pomoc_<temat>.<jezyk>.html`,
a nie w katalogu przekladu: to cale strony z naglowkami i listami, ktorych
nie da sie sensownie pociac na zdania-klucze. Brak pliku w jezyku
interfejsu = wersja angielska, potem polska.
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from .skala import marginesy, minimum
from ..przeklad import jezyk, t

KATALOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lang")
TEMAT_MCP = "mcp"


def plik_pomocy(temat: str, kod: str | None = None) -> str | None:
    for kandydat in (kod or jezyk(), "en", "pl"):
        sciezka = os.path.join(KATALOG, f"pomoc_{temat}.{kandydat}.html")
        if os.path.isfile(sciezka):
            return sciezka
    return None


def tekst_pomocy(temat: str, kod: str | None = None) -> str:
    sciezka = plik_pomocy(temat, kod)
    if sciezka is None:
        return ""
    with open(sciezka, encoding="utf-8") as f:
        return f.read()


class OknoPomocy(QDialog):
    def __init__(self, temat: str, tytul: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tytul)
        minimum(self, szer=620, wys=560)
        self.przegladarka = QTextBrowser()
        self.przegladarka.setOpenExternalLinks(True)
        self.przegladarka.setHtml(tekst_pomocy(temat))
        przyciski = QDialogButtonBox(QDialogButtonBox.Close)
        przyciski.button(QDialogButtonBox.Close).setText(t("Zamknij"))
        przyciski.rejected.connect(self.reject)
        uklad = QVBoxLayout(self)
        marginesy(uklad, 12, 12, 12, 12)
        uklad.addWidget(self.przegladarka, 1)
        uklad.addWidget(przyciski)


def pokaz_pomoc_mcp(parent=None) -> None:
    OknoPomocy(TEMAT_MCP, t("Sterowanie przez AI (MCP)"), parent).exec()
