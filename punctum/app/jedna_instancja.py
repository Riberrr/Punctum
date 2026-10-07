"""Jedna instancja programu (punkt 34) i ponowne uruchomienie (punkt 33).

Dwuklik zdjecia w Eksploratorze przy otwartym Punctum ma przekazac plik
dzialajacemu oknu, a nie budowac drugie okno z drugim serwerem MCP na
zajetym porcie. Drugi proces laczy sie z lokalnym gniazdem pierwszego,
wysyla mu swoje argumenty i konczy sie jeszcze przed ekranem startowym.

Modul jest lekki (tylko QtCore/QtNetwork) - laduje sie przed ekranem
startowym, wiec nie moze ciagnac rawpy ani OpenCV.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import sys
import time

from PySide6.QtCore import QDir, QEvent, QLockFile, QObject, QProcess, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .. import APP_ID
from ..core import platforma

CZAS_MS = 1500
# Flaga ponownego uruchomienia: po starcie otworz ustawienia na tej stronie
# i tym polu (punkt 33). Osobna flaga, bo pierwszy argument bywa zdjeciem.
FLAGA_USTAWIEN = "--ustawienia="


def nazwa_serwera() -> str:
    # Nazwa uzytkownika w nazwie: potok nazwany na Windows jest wspolny dla
    # calego komputera, a dwie osoby zalogowane naraz maja miec osobne programy.
    try:
        uzytkownik = getpass.getuser()
    except Exception:
        uzytkownik = ""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", f"{APP_ID}-{uzytkownik}")


def rozbierz_argumenty(argumenty: list[str]) -> tuple[str, str]:
    """(sciezka, pole ustawien) z argumentow programu (bez nazwy programu)."""
    sciezka = pole = ""
    for arg in argumenty:
        if arg.startswith(FLAGA_USTAWIEN):
            pole = arg[len(FLAGA_USTAWIEN):]
        elif not arg.startswith("--") and not sciezka:
            sciezka = arg
    return sciezka, pole


def bezwzgledne(argumenty: list[str]) -> list[str]:
    # Dzialajacy program ma inny katalog biezacy niz ten, ktory go wola -
    # sciezka wzgledna wskazalaby u niego cos innego.
    return [a if a.startswith("--") or not a else os.path.abspath(a) for a in argumenty]


def _pozwol_na_wierzch() -> None:
    # Windows nie pozwala procesowi w tle wyciagnac okna na wierzch. Prawo do
    # tego ma proces, ktory uruchomil uzytkownik (my) - oddajemy je dalej.
    if platforma.WINDOWS:
        try:
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:
            pass


def przekaz_dzialajacemu(argumenty: list[str], nazwa: str | None = None) -> bool:
    """True, gdy dzialajacy program przyjal argumenty - wtedy ten proces
    konczy sie bez budowania okna."""
    gniazdo = QLocalSocket()
    gniazdo.connectToServer(nazwa or nazwa_serwera())
    if not gniazdo.waitForConnected(CZAS_MS):
        return False
    _pozwol_na_wierzch()
    gniazdo.write(json.dumps({"argumenty": argumenty}).encode("utf-8") + b"\n")
    przyjete = gniazdo.waitForBytesWritten(CZAS_MS)
    # Czekamy na potwierdzenie: gdyby tamten program wlasnie sie zamykal,
    # lepiej wystartowac samemu niz zgubic plik, ktory kliknal uzytkownik.
    odpowiedz = b""
    while przyjete and b"\n" not in odpowiedz:
        if not gniazdo.waitForReadyRead(CZAS_MS):
            break
        odpowiedz += gniazdo.readAll().data()
    gniazdo.abort()
    return odpowiedz.startswith(b"ok")


class SerwerInstancji(QObject):
    """Gniazdo pierwszego programu. Argumenty, ktore przyjda, zanim okno
    bedzie gotowe (ekran startowy przepuszcza zdarzenia), czekaja na odbiorce."""

    def __init__(self, nazwa: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.nazwa = nazwa or nazwa_serwera()
        self.serwer = QLocalServer(self)
        # Tylko biezacy uzytkownik moze nam podsylac pliki.
        self.serwer.setSocketOptions(QLocalServer.UserAccessOption)
        self.serwer.newConnection.connect(self._polaczenie)
        self.zamek = QLockFile(os.path.join(QDir.tempPath(), self.nazwa + ".lock"))
        self.zamek.setStaleLockTime(0)  # porzucony = proces nie zyje, nie "stary"
        self._odbiorca = None
        self._czekajace: list[list[str]] = []

    def uruchom(self) -> bool:
        """True, gdy ten proces jest pierwszy (trzyma zamek)."""
        # Sam listen() nie wystarczy: na Windows dwa procesy moga sluchac pod
        # ta sama nazwa, a Eksplorator przy kilku zaznaczonych zdjeciach
        # uruchamia program kilka razy naraz. Zamek rozstrzyga, kto jest
        # pierwszy; po awarii procesu QLockFile sam uznaje go za porzucony.
        if not self.zamek.isLocked() and not self.zamek.tryLock(0):
            return False
        if not self.serwer.isListening() and not self.serwer.listen(self.nazwa):
            # Po awarii na Linuksie/macOS zostaje plik gniazda i blokuje
            # nazwe - trzymamy zamek, wiec nikt inny pod nia nie slucha.
            QLocalServer.removeServer(self.nazwa)
            self.serwer.listen(self.nazwa)
        return True

    def zamknij(self) -> None:
        self.serwer.close()
        if self.zamek.isLocked():
            self.zamek.unlock()

    def ustaw_odbiorce(self, odbiorca) -> None:
        self._odbiorca = odbiorca
        czekajace, self._czekajace = self._czekajace, []
        for argumenty in czekajace:
            odbiorca(argumenty)

    def _polaczenie(self) -> None:
        while self.serwer.hasPendingConnections():
            gniazdo = self.serwer.nextPendingConnection()
            bufor = bytearray()
            gniazdo.readyRead.connect(lambda g=gniazdo, b=bufor: self._czytaj(g, b))
            gniazdo.disconnected.connect(gniazdo.deleteLater)

    def _czytaj(self, gniazdo: QLocalSocket, bufor: bytearray) -> None:
        bufor += gniazdo.readAll().data()
        if b"\n" not in bufor:
            return
        linia = bytes(bufor).split(b"\n", 1)[0]
        bufor.clear()
        try:
            argumenty = json.loads(linia.decode("utf-8"))["argumenty"]
            if not all(isinstance(a, str) for a in argumenty):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            gniazdo.abort()
            return
        gniazdo.write(b"ok\n")
        gniazdo.flush()
        # Wczytanie katalogu trwa - odpowiedz ma wyjsc najpierw, zeby drugi
        # proces nie czekal na nie i nie uznal nas za zawieszonych.
        QTimer.singleShot(0, lambda: self._dostarcz(argumenty))

    def sluchaj_otwierania(self, app: "Aplikacja") -> None:
        """Pliki otwierane z systemu zdarzeniem (Aplikacja) ida ta sama
        droga co pliki od drugiego uruchomienia (punkt 31 D)."""
        app.odbiorca_plikow = lambda plik: self._dostarcz([plik])

    def przejmij_czekajace(self) -> list[str]:
        """Pierwsze czekajace argumenty (albo pusta lista), wyjete z kolejki.
        Program uruchomiony dwuklikiem na macOS dostaje plik zdarzeniem
        jeszcze w trakcie ekranu startowego - wtedy otwiera od razu jego
        katalog zamiast ostatniego, zamiast wczytywac oba po kolei."""
        return self._czekajace.pop(0) if self._czekajace else []

    def _dostarcz(self, argumenty: list[str]) -> None:
        if self._odbiorca is None:
            self._czekajace.append(argumenty)
        else:
            self._odbiorca(argumenty)


class Aplikacja(QApplication):
    """QApplication, ktora oddaje pliki otwierane z systemu zdarzeniem.

    Na macOS plik z Findera, z Docku albo z "Otworz za pomoca" nie
    przychodzi w argv, tylko jako QFileOpenEvent do obiektu aplikacji
    (punkt 31 D). Nadpisane event() zamiast filtra zdarzen na calej
    aplikacji: filtr w Pythonie dostaje tez zdarzenia obiektow w trakcie
    konstrukcji (np. zadan sieciowych przegladarki mapy) i PySide padal
    na nich w skompilowanym programie (SIGSEGV w getWrapperForQObject).
    """

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.odbiorca_plikow = None

    def event(self, zdarzenie: QEvent) -> bool:
        if (zdarzenie.type() == QEvent.FileOpen and self.odbiorca_plikow is not None
                and zdarzenie.file()):
            self.odbiorca_plikow(zdarzenie.file())
            return True
        return super().event(zdarzenie)


def zglos_sie(argumenty: list[str], nazwa: str | None = None,
              czekaj_s: float = 5.0) -> SerwerInstancji | None:
    """Serwer, gdy ten proces ma zostac programem; None, gdy argumenty
    przejal juz dzialajacy program i ten proces ma sie zakonczyc."""
    serwer = SerwerInstancji(nazwa)
    koniec = time.monotonic() + czekaj_s
    while True:
        if przekaz_dzialajacemu(argumenty, serwer.nazwa):
            return None
        if serwer.uruchom():
            return serwer
        # Zamek ma ktos, kto jeszcze nie slucha (startuje w tej samej chwili).
        # Po czasie i tak startujemy sami - lepiej drugie okno niz zadne.
        if time.monotonic() > koniec:
            return serwer
        time.sleep(0.05)


def polecenie_restartu(argumenty: list[str]) -> tuple[str, list[str], str]:
    """(program, argumenty, katalog roboczy) nowego procesu tego programu."""
    if globals().get("__compiled__") is not None:
        # Skompilowany Punctum.exe: sys.executable to on sam.
        return sys.executable, list(argumenty), os.getcwd()
    program = sys.executable
    # Z python.exe nowy proces dostalby wlasne okno konsoli - bierzemy
    # pythonw obok (kopia Punctum.exe z punktu 29 jest juz bez konsoli).
    if os.path.basename(program).lower() == "python.exe":
        okienkowy = os.path.join(os.path.dirname(program), "pythonw.exe")
        if os.path.isfile(okienkowy):
            program = okienkowy
    # -m punctum szuka pakietu w katalogu roboczym - stad katalog repozytorium.
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return program, ["-m", "punctum", *argumenty], repo


def uruchom_ponownie(argumenty: list[str]) -> bool:
    program, args, katalog = polecenie_restartu(argumenty)
    wynik = QProcess.startDetached(program, args, katalog)
    # PySide6 oddaje (ok, pid), starsze wiazania samo ok
    return bool(wynik[0] if isinstance(wynik, tuple) else wynik)
