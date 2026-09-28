"""Protokol MCP (JSON-RPC 2.0) i serwer HTTP na 127.0.0.1.

Transport "Streamable HTTP" w najprostszej dozwolonej postaci: klient wysyla
POST z komunikatem JSON-RPC, odpowiedz wraca jako zwykly JSON (bez strumienia
SSE - narzedzia Punctum nie wysylaja powiadomien w trakcie pracy). Na GET
odpowiadamy 405, co specyfikacja przewiduje dla serwera bez strumienia.

Bezpieczenstwo: serwer slucha wylacznie na 127.0.0.1, wymaga tokenu
(`Authorization: Bearer ...`) i odrzuca zadania z obcym naglowkiem Origin -
inaczej dowolna strona otwarta w przegladarce moglaby sterowac edytorem
(atak "DNS rebinding").
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from . import narzedzia

WERSJE_PROTOKOLU = ("2025-06-18", "2025-03-26", "2024-11-05")
PORT_DOMYSLNY = 47823
SCIEZKA = "/mcp"
PLIK_POLACZENIA = "mcp.json"
MAKS_ROZMIAR = 4 * 1024 * 1024  # zadanie z tekstem polecen, nie z plikiem


class BladNarzedzia(Exception):
    """Blad, ktory model ma zobaczyc jako tresc odpowiedzi (isError), nie jako
    awarie protokolu - wtedy moze poprawic polecenie i sprobowac jeszcze raz."""


def wersja_programu() -> str:
    try:
        from importlib.metadata import version
        return version("punctum")
    except Exception:
        return "0.1.0"


# ------------------------------------------------------------- plik polaczenia

def plik_polaczenia(katalog: str | None = None) -> str:
    if katalog is None:
        from ..core.settings import config_directory
        katalog = config_directory()
    return os.path.join(katalog, PLIK_POLACZENIA)


def wczytaj_polaczenie(katalog: str | None = None) -> dict:
    try:
        with open(plik_polaczenia(katalog), encoding="utf-8") as f:
            dane = json.load(f)
        return dane if isinstance(dane, dict) else {}
    except (OSError, ValueError):
        return {}


def zapisz_polaczenie(port: int, token: str, katalog: str | None = None) -> None:
    """Port i token dla mostka stdio. Token lezy tylko tu (i w pamieci
    programu), a nie w plikach konfiguracji klientow AI - wygenerowanie
    nowego nie wymaga wiec ponownego podlaczania klientow."""
    sciezka = plik_polaczenia(katalog)
    os.makedirs(os.path.dirname(sciezka), exist_ok=True)
    tymczasowy = sciezka + ".tmp"
    with open(tymczasowy, "w", encoding="utf-8") as f:
        json.dump({"port": port, "token": token, "url": f"http://127.0.0.1:{port}{SCIEZKA}"},
                  f, indent=2)
    os.replace(tymczasowy, sciezka)


def token_z_pliku(katalog: str | None = None) -> str:
    """Token z poprzedniej sesji albo nowy - staly token pozwala klientom HTTP
    (wpisanym recznie) dzialac po ponownym uruchomieniu programu."""
    token = wczytaj_polaczenie(katalog).get("token")
    if isinstance(token, str) and len(token) >= 32:
        return token
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------- tresc wyniku

def tekst(napis: str) -> dict:
    return {"type": "text", "text": napis}


def dane(obiekt: Any) -> dict:
    """Wynik jako JSON w tresci tekstowej - kazdy klient go pokaze, a model
    czyta JSON bez klopotu."""
    return tekst(json.dumps(obiekt, ensure_ascii=False, indent=1, default=str))


def obraz(base64_jpeg: str) -> dict:
    return {"type": "image", "data": base64_jpeg, "mimeType": "image/jpeg"}


# ------------------------------------------------------------------- JSON-RPC

Wykonawca = Callable[[str, dict], list[dict]]


def _blad(id_: Any, kod: int, wiadomosc: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": kod, "message": wiadomosc}}


def _wynik(id_: Any, wynik: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": wynik}


def inicjalizacja(parametry: dict) -> dict:
    zadana = parametry.get("protocolVersion")
    return {
        # Wersja klienta, jesli ja znamy; inaczej nasza najnowsza - klient
        # sam zdecyduje, czy z nia pracuje.
        "protocolVersion": zadana if zadana in WERSJE_PROTOKOLU else WERSJE_PROTOKOLU[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "punctum", "title": "Punctum", "version": wersja_programu()},
        "instructions": narzedzia.INSTRUKCJA,
    }


def obsluz(komunikat: Any, wykonaj: Wykonawca) -> dict | None:
    """Jeden komunikat JSON-RPC -> odpowiedz albo None (powiadomienie)."""
    if not isinstance(komunikat, dict) or komunikat.get("jsonrpc") != "2.0":
        return _blad(None, -32600, "Invalid Request")
    metoda = komunikat.get("method")
    if "id" not in komunikat or metoda is None:
        return None  # powiadomienie albo odpowiedz klienta - nic nie odsylamy
    id_ = komunikat["id"]
    parametry = komunikat.get("params") or {}
    if metoda == "initialize":
        return _wynik(id_, inicjalizacja(parametry))
    if metoda == "ping":
        return _wynik(id_, {})
    if metoda == "tools/list":
        return _wynik(id_, {"tools": narzedzia.NARZEDZIA})
    if metoda == "tools/call":
        nazwa = parametry.get("name")
        if nazwa not in narzedzia.NAZWY:
            return _blad(id_, -32602, f"Unknown tool: {nazwa}")
        argumenty = parametry.get("arguments") or {}
        if not isinstance(argumenty, dict):
            return _blad(id_, -32602, "arguments must be an object")
        try:
            tresc = wykonaj(nazwa, argumenty)
            return _wynik(id_, {"content": tresc, "isError": False})
        except BladNarzedzia as exc:
            return _wynik(id_, {"content": [tekst(str(exc))], "isError": True})
        except Exception as exc:  # blad programu nie moze zerwac polaczenia
            return _wynik(id_, {"content": [tekst(f"{type(exc).__name__}: {exc}")],
                                "isError": True})
    return _blad(id_, -32601, f"Method not found: {metoda}")


def obsluz_tekst(tresc: bytes | str, wykonaj: Wykonawca) -> Any:
    """Tresc zadania -> odpowiedz do wyslania (dict, lista albo None)."""
    try:
        komunikat = json.loads(tresc)
    except ValueError:
        return _blad(None, -32700, "Parse error")
    if isinstance(komunikat, list):  # paczki ze starszych wersji protokolu
        odpowiedzi = [o for o in (obsluz(k, wykonaj) for k in komunikat) if o is not None]
        return odpowiedzi or None
    return obsluz(komunikat, wykonaj)


# ---------------------------------------------------------------- serwer HTTP

_DOZWOLONE_ORIGIN = ("http://127.0.0.1", "http://localhost", "https://127.0.0.1",
                     "https://localhost")


class _Obsluga(BaseHTTPRequestHandler):
    server: "SerwerMCP"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # bez zasmiecania konsoli programu
        pass

    def _odpowiedz(self, kod: int, cialo: Any = None) -> None:
        tresc = b"" if cialo is None else json.dumps(cialo, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        if tresc:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(tresc)))
        self.end_headers()
        if tresc:
            self.wfile.write(tresc)

    def _dozwolone(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and not any(origin == o or origin.startswith(o + ":")
                              for o in _DOZWOLONE_ORIGIN):
            self._odpowiedz(403, {"error": "origin not allowed"})
            return False
        if self.path.split("?")[0] != SCIEZKA:
            self._odpowiedz(404, {"error": "not found"})
            return False
        naglowek = self.headers.get("Authorization", "")
        if not secrets.compare_digest(naglowek, f"Bearer {self.server.token}"):
            self._odpowiedz(401, {"error": "missing or wrong token"})
            return False
        return True

    def do_POST(self) -> None:
        if not self._dozwolone():
            return
        dlugosc = int(self.headers.get("Content-Length") or 0)
        if dlugosc <= 0 or dlugosc > MAKS_ROZMIAR:
            self._odpowiedz(400, {"error": "bad length"})
            return
        odpowiedz = obsluz_tekst(self.rfile.read(dlugosc), self.server.wykonaj)
        self.server.ostatnie_polaczenie = self.headers.get("User-Agent", "")
        if odpowiedz is None:
            self._odpowiedz(202)
        else:
            self._odpowiedz(200, odpowiedz)

    def do_GET(self) -> None:
        if self._dozwolone():
            self._odpowiedz(405)

    def do_DELETE(self) -> None:  # koniec sesji - sesji nie prowadzimy
        if self._dozwolone():
            self._odpowiedz(405)


class SerwerMCP(ThreadingHTTPServer):
    """Serwer w osobnym watku. Kazde zadanie dostaje wlasny watek, wiec dlugie
    narzedzie (eksport, automat na 50 zdjeciach) nie blokuje `ping`."""

    daemon_threads = True

    def __init__(self, wykonaj: Wykonawca, token: str, port: int = PORT_DOMYSLNY):
        super().__init__(("127.0.0.1", port), _Obsluga)
        self.wykonaj, self.token = wykonaj, token
        self.ostatnie_polaczenie = ""
        self._watek: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.server_address[1]

    def uruchom(self) -> None:
        self._watek = threading.Thread(target=self.serve_forever, name="punctum-mcp",
                                       daemon=True)
        self._watek.start()

    def zatrzymaj(self) -> None:
        self.shutdown()
        self.server_close()
