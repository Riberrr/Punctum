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
KATALOG_GLOWNY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def plik_zmian(kod: str | None = None) -> str | None:
    """Historia zmian w jezyku interfejsu; angielska dla pozostalych jezykow.

    Pliki leza w katalogu glownym repozytorium (widac je na GitHubie), a w
    kompilacji obok Punctum.exe - w obu przypadkach trzy poziomy nad tym
    modulem, wiec jedna sciezka wystarcza.
    """
    nazwy = ["CHANGELOG.pl.md"] if (kod or jezyk()) == "pl" else []
    for nazwa in nazwy + ["CHANGELOG.md"]:
        sciezka = os.path.join(KATALOG_GLOWNY, nazwa)
        if os.path.isfile(sciezka):
            return sciezka
    return None


def tekst_zmian(kod: str | None = None) -> str:
    sciezka = plik_zmian(kod)
    if sciezka is None:
        return ""
    with open(sciezka, encoding="utf-8") as f:
        return f.read()


class OknoPomocy(QDialog):
    def __init__(self, temat: str, tytul: str, parent=None, markdown: str | None = None,
                 zwykly: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(tytul)
        minimum(self, szer=620, wys=560)
        self.przegladarka = QTextBrowser()
        self.przegladarka.setOpenExternalLinks(True)
        if zwykly is not None:
            # Teksty licencji maja wciecia i tabelki ze spacji - pismo
            # o stalej szerokosci i bez interpretacji znacznikow.
            from PySide6.QtGui import QFontDatabase

            self.przegladarka.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
            self.przegladarka.setPlainText(zwykly)
        elif markdown is None:
            self.przegladarka.setHtml(tekst_pomocy(temat))
        else:
            # Odnosnik do wersji w drugim jezyku jest dla czytajacych na
            # GitHubie; w oknie wczytalby surowy plik zamiast strony.
            self.przegladarka.setOpenLinks(False)
            self.przegladarka.setMarkdown(markdown)
        przyciski = QDialogButtonBox(QDialogButtonBox.Close)
        przyciski.button(QDialogButtonBox.Close).setText(t("Zamknij"))
        przyciski.rejected.connect(self.reject)
        uklad = QVBoxLayout(self)
        marginesy(uklad, 12, 12, 12, 12)
        uklad.addWidget(self.przegladarka, 1)
        uklad.addWidget(przyciski)


def pokaz_pomoc_mcp(parent=None) -> None:
    OknoPomocy(TEMAT_MCP, t("Sterowanie przez AI (MCP)"), parent).exec()


def pokaz_co_nowego(parent=None) -> None:
    OknoPomocy("", t("Co nowego"), parent, markdown=tekst_zmian()).exec()


def pokaz_licencje(parent=None) -> None:
    """Licencje bibliotek dolaczonych do programu (punkt 18, etap 3)."""
    from ..core import licencje

    okno = OknoPomocy("", t("Licencje zewnętrzne"), parent, zwykly=licencje.tekst())
    minimum(okno, szer=760, wys=600)
    okno.exec()


def co_nowego_po_aktualizacji(okno) -> None:
    """Pokazuje historie zmian raz, przy pierwszym starcie nowej wersji.

    Pusta zapamietana wersja = pierwsze uruchomienie (albo ustawienia sprzed
    tej funkcji): tylko zapamietujemy, bo nowemu uzytkownikowi lista zmian
    nic nie mowi. `open()` zamiast `exec()` - start nie czeka na zamkniecie.
    """
    from .. import __version__

    s = okno.settings
    if s.last_seen_version == __version__:
        return
    poprzednia = s.last_seen_version
    s.last_seen_version = __version__
    s.save()
    if poprzednia and tekst_zmian():
        okno._okno_zmian = OknoPomocy("", t("Co nowego"), okno, markdown=tekst_zmian())
        okno._okno_zmian.open()
