"""Panele z sekcjami w dzialajacym oknie (punkt 23).

Zwijanie, ukrywanie z menu Widok, klodka, przenoszenie miedzy panelami
i do schowka, okno ukladu, powrot do ukladu domyslnego, rozciaganie
rozwinietych metadanych. Zdjec nie potrzebuje, ale przyjmuje je jak inne
testy z serii. Zrzut: %TEMP%/punctum-panele.png.

Uzycie:  python tools/test_panele_gui.py [zdjecia...] [--pelny]
"""

from __future__ import annotations

import os
import sys
import tempfile

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from wspolne import czekaj, lancuch, wypisz  # noqa: E402

from punctum.app import MainWindow  # noqa: E402
from punctum.app.panele import (  # noqa: E402
    LEWY, PRAWY, SCHOWEK, UKLAD_DOMYSLNY, OknoUkladu, uporzadkuj,
)
from punctum.core.settings import Settings, settings_path  # noqa: E402
from punctum.przeklad import t  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

window = MainWindow()
window.settings.save = lambda *a, **k: True  # zadnych sladow w ustawieniach
window.settings.store_edits = False
window.showMaximized()
u = window.panele


def klucze(miejsce: str) -> list[str]:
    return [s.klucz for s in u.panele[miejsce].sekcje]


def stage_start() -> None:
    czekaj(app, lambda: window.isVisible(), "pokazanie okna")
    u.zastosuj({})
    app.processEvents()
    check("lewy panel: uklad domyslny", klucze(LEWY) == UKLAD_DOMYSLNY[LEWY], str(klucze(LEWY)))
    check("prawy panel: uklad domyslny", klucze(PRAWY) == UKLAD_DOMYSLNY[PRAWY], str(klucze(PRAWY)))
    right = window.right_panel
    auto = window.edit_panel.auto_button
    check("Automatycznie na stale, poza przewijana lista",
          right.isAncestorOf(auto) and not right.scroll.isAncestorOf(auto) and auto.isVisible())
    check("nawigator i histogram widoczne",
          window.navigator.isVisible() and window.histogram_widget.isVisible())
    check("klodki zamkniete, uchwyty schowane",
          not right.klodka.isChecked()
          and not u.sekcje["ton"].naglowek.uchwyt.isVisible())
    for klucz, ile in (("balans", 2), ("ton", 6), ("obecnosc", 2), ("wyostrzanie", 4), ("szum", 2)):
        sekcja = u.sekcje[klucz]
        suwaki = [s for s in window.edit_panel.sliders.values() if sekcja.isAncestorOf(s)]
        check(f"sekcja {klucz}: {ile} suwaki", len(suwaki) == ile, str(len(suwaki)))
    for key in ("exposure", "contrast", "vibrance", "saturation", "temperature", "tint"):
        slider = window.edit_panel.sliders[key].slider
        check(f"kolorowy rowek: {key}", type(slider).__name__ == "GradientSlider")
    window.grab().save(os.path.join(tempfile.gettempdir(), "punctum-panele.png"))


def stage_zwijanie() -> None:
    ton = u.sekcje["ton"]
    QTest.mouseClick(ton.naglowek, Qt.LeftButton)
    app.processEvents()
    check("klik w naglowek zwija", ton.zwinieta and not ton.tresc.isVisible()
          and "ton" in window.settings.panel_layout.get("zwiniete", []))
    check("zwinieta sekcja ma strzalke w bok", ton.naglowek.strzalka.text() == "▸")
    ton.naglowek.strzalka.click()
    app.processEvents()
    check("strzalka rozwija", not ton.zwinieta and ton.tresc.isVisible())
    u.przelacz_zwiniecie("balans")
    check("zwiniecie jednej nie rusza innych",
          u.sekcje["balans"].zwinieta and not u.sekcje["ton"].zwinieta)
    u.przelacz_zwiniecie("balans")


def stage_menu() -> None:
    menu = window.panels_menu
    menu.aboutToShow.emit()
    akcje = {a.text(): a for a in menu.actions()}
    check("menu Panele: sekcje obu paneli i polecenia",
          all(t(x) in akcje for x in ("Histogram", "Nawigator", "Dostosuj układ…",
                                      "Przywróć układ domyślny")), str(list(akcje)))
    akcje[t("Histogram")].trigger()
    app.processEvents()
    check("odhaczenie odklada sekcje do schowka", not window.histogram_widget.isVisible()
          and window.settings.panel_layout[SCHOWEK] == ["histogram"])
    menu.aboutToShow.emit()
    akcje = {a.text(): a for a in menu.actions()}
    akcja = akcje[t("Histogram")]
    check("menu pokazuje schowek i stan", t("Nieużywane") in akcje
          and akcja.isCheckable() and not akcja.isChecked())
    akcja.trigger()
    app.processEvents()
    check("ponowne zaznaczenie wraca na domyslne miejsce",
          window.histogram_widget.isVisible() and klucze(PRAWY)[0] == "histogram")


def stage_klodka() -> None:
    right = window.right_panel
    right.klodka.click()
    app.processEvents()
    check("klodka odblokowuje panel", PRAWY in window.settings.panel_layout["odblokowane"]
          and u.sekcje["ton"].przesuwalna and u.sekcje["ton"].naglowek.uchwyt.isVisible())
    check("drugi panel zostaje zablokowany", not u.sekcje["nawigator"].przesuwalna)
    right.klodka.click()
    app.processEvents()
    check("i blokuje z powrotem", not u.sekcje["ton"].przesuwalna)


def stage_przenoszenie() -> None:
    u.przenies("obecnosc", LEWY, "dane")
    app.processEvents()
    obecnosc = u.sekcje["obecnosc"]
    check("sekcja przeniesiona do lewego panelu",
          window.left_panel.isAncestorOf(obecnosc)
          and klucze(LEWY)[klucze(LEWY).index("obecnosc") + 1] == "dane",
          str(klucze(LEWY)))
    check("suwaki jada razem z sekcja",
          obecnosc.isVisible() and window.edit_panel.sliders["vibrance"].isVisible())
    zmiany = []
    window.edit_panel.params_changed.connect(lambda: zmiany.append(1))
    window.edit_panel.sliders["vibrance"].slider.setValue(15)
    check("suwak w nowym miejscu dalej dziala", zmiany != [])
    window.edit_panel.sliders["vibrance"].set_value(0)
    u.przenies("szum", SCHOWEK)
    app.processEvents()
    check("sekcja w schowku znika z paneli", not u.sekcje["szum"].isVisible()
          and "szum" not in klucze(PRAWY) and u.sekcje["szum"].window() is not window)


def stage_okno() -> None:
    dialog = OknoUkladu(u.stan, window)
    listy = dialog.listy
    check("okno: schowek z jedna sekcja", listy[SCHOWEK].count() == 1)
    check("okno: bez pol wyboru",
          all(not (lista.item(i).flags() & Qt.ItemIsUserCheckable)
              for lista in listy.values() for i in range(lista.count())))
    listy[PRAWY].insertItem(0, listy[SCHOWEK].takeItem(0))
    listy[SCHOWEK].addItem(listy[LEWY].takeItem(0))  # nawigator do schowka
    wynik = dialog.wynik()
    check("okno: przeniesienia w wyniku",
          wynik[PRAWY][0] == "szum" and wynik[SCHOWEK] == ["nawigator"] and "ukryte" not in wynik,
          str(wynik))
    dialog.deleteLater()
    u.przyjmij(wynik)
    app.processEvents()
    check("przyjety uklad z okna widac w oknie",
          klucze(PRAWY)[0] == "szum" and not window.navigator.isVisible()
          and window.edit_panel.sliders["vibrance"].isVisible())
    check("uklad sie nie gubi (komplet sekcji)",
          sorted(klucze(LEWY) + klucze(PRAWY) + u.stan[SCHOWEK]) == sorted(u.sekcje))


def stage_domyslny() -> None:
    u.przelacz_zwiniecie("ton")
    u.ustaw_blokade(LEWY, True)
    u.przywroc_domyslny()
    app.processEvents()
    check("przywrocenie: uklad domyslny i wszystko widoczne",
          klucze(LEWY) == UKLAD_DOMYSLNY[LEWY] and klucze(PRAWY) == UKLAD_DOMYSLNY[PRAWY]
          and window.navigator.isVisible() and u.stan["zwiniete"] == [])
    check("przywrocenie nie rusza klodki", u.stan["odblokowane"] == [LEWY])
    u.ustaw_blokade(LEWY, False)

    path = os.path.join(tempfile.gettempdir(), "punctum-panele-ustawienia.json")
    u.przenies("histogram", LEWY, "nawigator")
    Settings(panel_layout=u.do_zapisu()).save(path)
    wczytany = Settings.load(path).panel_layout
    os.remove(path)
    check("uklad przechodzi przez plik ustawien", uporzadkuj(wczytany) == u.stan, str(wczytany))
    u.przywroc_domyslny()


def stage_metadane() -> None:
    dane = u.sekcje["dane"]
    lista = window.left_panel.lista.uklad_pionowy
    i = klucze(LEWY).index("dane")
    window.info_panel.set_details_visible(True)
    app.processEvents()
    check("rozwiniete metadane biora wolne miejsce", lista.stretch(i) == 1)
    u.przelacz_zwiniecie("dane")
    app.processEvents()
    check("zwinieta sekcja danych nie rozpycha panelu", lista.stretch(i) == 0
          and lista.stretch(lista.count() - 1) == 1)
    u.przelacz_zwiniecie("dane")
    window.info_panel.set_details_visible(False)
    check("sekcja danych znow na swoim miejscu", dane.isVisible())


def finish() -> None:
    try:
        failures = wypisz(results)
    finally:
        window.hide()
        if BACKUP is not None:
            with open(SETTINGS_FILE, "wb") as handle:
                handle.write(BACKUP)
    app.exit(failures)


lancuch(app, [stage_start, stage_zwijanie, stage_menu, stage_klodka, stage_przenoszenie,
              stage_okno, stage_domyslny, stage_metadane], finish)
sys.exit(app.exec())
