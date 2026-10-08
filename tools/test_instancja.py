"""Jedna instancja (punkt 34) i ponowne uruchomienie po zmianie jezyka (33).

Drugie uruchomienie gra tu osobny proces Pythona - tak jak dwuklik zdjecia
w Eksploratorze. Gniazdo ma nazwe z numerem procesu testu, zeby nie
podsylac plikow programowi, ktory uzytkownik ma wlasnie otwarty. Okno
ustawien na platformie offscreen - nic nie pokazuje sie na ekranie.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, REPO)
sys.path.insert(0, TOOLS)

from wspolne import wypisz  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from punctum.app import jedna_instancja as ji  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


app = ji.Aplikacja(sys.argv)

# --- argumenty
check("argumenty: zdjecie i flaga",
      ji.rozbierz_argumenty(["a.jpg", "--ustawienia=jezyk"]) == ("a.jpg", "jezyk"))
check("argumenty: flaga przed sciezka",
      ji.rozbierz_argumenty(["--ustawienia=jezyk", "kat"]) == ("kat", "jezyk"))
check("argumenty: puste", ji.rozbierz_argumenty([]) == ("", ""))
check("argumenty: nieznana flaga pomijana",
      ji.rozbierz_argumenty(["--cos", "b.nef"]) == ("b.nef", ""))
bezw = ji.bezwzgledne(["a.jpg", "--ustawienia=jezyk"])
check("sciezka wzgledna -> bezwzgledna",
      os.path.isabs(bezw[0]) and bezw[1] == "--ustawienia=jezyk", str(bezw))
check("nazwa gniazda bez znakow specjalnych",
      all(c.isalnum() or c in "_.-" for c in ji.nazwa_serwera()))

# --- plik od systemu zdarzeniem (macOS: Finder, Dock; punkt 31 D)
from PySide6.QtGui import QFileOpenEvent  # noqa: E402

plikowy = ji.SerwerInstancji(f"punctum-test-plik-{os.getpid()}")
plikowy.sluchaj_otwierania(app)
ZDARZENIE = os.path.join(REPO, "a.jpg")
QApplication.sendEvent(app, QFileOpenEvent(ZDARZENIE))
check("zdarzenie otwarcia czeka przed oknem", plikowy.przejmij_czekajace() == [ZDARZENIE])
check("kolejka po przejeciu pusta", plikowy.przejmij_czekajace() == [])
odebrane = []
plikowy.ustaw_odbiorce(odebrane.append)
QApplication.sendEvent(app, QFileOpenEvent(ZDARZENIE))
check("zdarzenie otwarcia do gotowego okna", odebrane == [[ZDARZENIE]], str(odebrane))
app.odbiorca_plikow = None

# --- polecenie restartu ze zrodel
program, args, katalog = ji.polecenie_restartu(["x.jpg", "--ustawienia=jezyk"])
check("restart: -m punctum z argumentami", args == ["-m", "punctum", "x.jpg", "--ustawienia=jezyk"], str(args))
check("restart: katalog z pakietem", os.path.isfile(os.path.join(katalog, "punctum", "__main__.py")), katalog)
check("restart: bez okna konsoli", os.path.basename(program).lower() != "python.exe", program)

# --- przekazanie do dzialajacego programu
NAZWA = f"punctum-test-{os.getpid()}"
start = time.monotonic()
check("bez serwera: przekazanie odrzucone", not ji.przekaz_dzialajacemu(["a"], NAZWA))
check("bez serwera: szybko", time.monotonic() - start < 3.0, f"{time.monotonic() - start:.2f} s")

serwer = ji.SerwerInstancji(NAZWA)
check("serwer slucha", serwer.uruchom())
# Na Windows listen() pod zajeta nazwa sie udaje - pierwszenstwo daje zamek.
drugi = ji.SerwerInstancji(NAZWA)
check("drugi proces nie dostaje zamka", not drugi.uruchom() and not drugi.serwer.isListening())
wolny = ji.zglos_sie(["a"], NAZWA + "-wolna", czekaj_s=0.3)
check("wolna nazwa: od razu zostaje programem",
      wolny is not None and wolny.serwer.isListening() and wolny.zamek.isLocked())
wolny.zamknij()
# Zamek bez serwera = ktos startuje w tej chwili: czekamy, potem i tak sami.
zajety = ji.SerwerInstancji(NAZWA + "-zamek")
zajety.zamek.tryLock(0)
start = time.monotonic()
inny = ji.zglos_sie(["a"], NAZWA + "-zamek", czekaj_s=0.3)
check("zamek u kogos innego: czeka, potem startuje bez gniazda",
      inny is not None and time.monotonic() - start >= 0.3 and not inny.serwer.isListening())
zajety.zamknij()

# Drugi proces wola to samo, co __main__: przekaz albo zostan programem.
# "True" = argumenty przejal dzialajacy program.
SKRYPT = (
    "import sys; sys.path.insert(0, sys.argv[1]);"
    "from PySide6.QtCore import QCoreApplication; app = QCoreApplication([]);"
    "from punctum.app.jedna_instancja import zglos_sie;"
    "print(zglos_sie(sys.argv[3:], sys.argv[2], czekaj_s=1) is None)"
)


def drugie_uruchomienie(argumenty: list[str]) -> str:
    proces = subprocess.Popen([sys.executable, "-c", SKRYPT, REPO, NAZWA, *argumenty],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    koniec = time.monotonic() + 20
    # Petla zdarzen musi chodzic, bo to ona obsluguje gniazdo serwera.
    while proces.poll() is None and time.monotonic() < koniec:
        app.processEvents()
        time.sleep(0.01)
    if proces.poll() is None:
        proces.kill()
    for _ in range(20):
        app.processEvents()
    return (proces.stdout.read() or "").strip()


PLIK = os.path.join(REPO, "zdjęcie ąę.jpg")  # ogonki: przez JSON w UTF-8
wynik = drugie_uruchomienie([PLIK, "--ustawienia=jezyk"])
check("drugi proces: przyjete", wynik.endswith("True"), wynik[-200:])
check("przed gotowoscia okna: czeka w kolejce", serwer._czekajace == [[PLIK, "--ustawienia=jezyk"]],
      str(serwer._czekajace))
odebrane: list[list[str]] = []
serwer.ustaw_odbiorce(odebrane.append)
check("kolejka oddana odbiorcy", odebrane == [[PLIK, "--ustawienia=jezyk"]] and not serwer._czekajace)
wynik = drugie_uruchomienie([])
check("uruchomienie bez argumentow tez przekazane",
      wynik.endswith("True") and odebrane[-1:] == [[]], f"{wynik[-80:]} {odebrane}")

serwer.zamknij()
check("po zamknieciu: drugi proces zostaje programem", drugie_uruchomienie(["a"]).endswith("False"))
check("po zamknieciu: nazwa znowu wolna", serwer.uruchom())
serwer.zamknij()

# --- okno ustawien: ostrzezenie i "Zapisz i uruchom ponownie" (33)
from punctum.app.settings_dialog import PAGE_GENERAL, SettingsDialog  # noqa: E402
from punctum.core.hardware import detect_system  # noqa: E402
from punctum.core.settings import Settings  # noqa: E402
from punctum.przeklad import jezyk, jezyki  # noqa: E402

dialog = SettingsDialog(Settings(), detect_system())
dialog.show()
app.processEvents()
check("ostrzezenie ukryte bez zmiany jezyka", not dialog.jezyk_ostrzezenie.isVisible())
inne = [k for k in jezyki() if k != jezyk()]
check("jest drugi jezyk do proby", bool(inne), str(jezyki()))
if inne:
    dialog.language_box.setCurrentIndex(dialog.language_box.findData(inne[0]))
    app.processEvents()
    check("po zmianie jezyka: ostrzezenie i przycisk",
          dialog.jezyk_ostrzezenie.isVisible() and dialog.restart_button.isVisible())
    dialog.language_box.setCurrentIndex(dialog.language_box.findData(jezyk()))
    app.processEvents()
    check("powrot do jezyka: ostrzezenie znika", not dialog.jezyk_ostrzezenie.isVisible())
    dialog.language_box.setCurrentIndex(dialog.language_box.findData(inne[0]))
    dialog.restart_button.click()
    check("przycisk: zapis z flaga restartu",
          dialog.result() == SettingsDialog.Accepted and dialog.uruchom_ponownie
          and dialog.result_settings().language == inne[0])
dialog.close()

po_restarcie = SettingsDialog(Settings(), detect_system())
po_restarcie.show_page("o_programie" if "o_programie" in po_restarcie._page_keys else po_restarcie._page_keys[-1])
po_restarcie.pokaz_pole("jezyk")
po_restarcie.show()
app.processEvents()
check("po restarcie: strona Ogolne", po_restarcie.current_page() == PAGE_GENERAL, po_restarcie.current_page())
check("po restarcie: fokus na polu jezyka", po_restarcie.focusWidget() is po_restarcie.language_box,
      str(po_restarcie.focusWidget()))
check("po restarcie: bez flagi restartu", not po_restarcie.uruchom_ponownie)
po_restarcie.close()

sys.exit(wypisz(results))
