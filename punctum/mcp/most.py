"""Mostek stdio <-> HTTP: `python -m punctum.mcp`.

Wiekszosc klientow AI na komputerze (Claude Desktop, Cursor, VS Code,
LM Studio, Gemini CLI, Codex) uruchamia serwer MCP jako proces i rozmawia
z nim przez stdin/stdout, po jednym komunikacie JSON w linii. Punctum jest
jednak programem z oknem, uruchamianym przez uzytkownika, nie przez klienta.
Mostek laczy oba swiaty: kazda linie ze stdin wysyla do serwera HTTP
dzialajacego w oknie Punctum i odpisuje odpowiedz na stdout.

Port i token czyta z pliku polaczenia w katalogu ustawien przy kazdym
komunikacie - Punctum uruchomiony po kliencie AI (albo ponownie) dziala
bez restartu klienta.

Mostek nie importuje Qt ani bibliotek obrazu: startuje w ulamku sekundy,
a gdy Punctum jest zamkniety, sam odpowiada na `initialize` i `tools/list`
(lista narzedzi jest wtedy od razu widoczna), a na wywolanie narzedzia
- prosba o uruchomienie programu.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from . import protokol

# Eksport kilkuset zdjec trwa minuty; klient i tak pokazuje postep po swojej
# stronie, a zerwanie polaczenia w polowie zostawiloby model bez wyniku.
LIMIT_CZASU_S = 900

# None = katalog ustawien Punctum; testy podstawiaja katalog tymczasowy.
KATALOG_POLACZENIA: str | None = None

_BEZ_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _PunctumNieDziala(Exception):
    pass


def _wyslij(tresc: bytes) -> bytes | None:
    polaczenie = protokol.wczytaj_polaczenie(KATALOG_POLACZENIA)
    url, token = polaczenie.get("url"), polaczenie.get("token")
    if not url or not token:
        raise _PunctumNieDziala
    zadanie = urllib.request.Request(
        url, data=tresc, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "Authorization": f"Bearer {token}",
                 "User-Agent": "punctum-mcp-most"},
    )
    try:
        # Bez posrednika: proxy z ustawien systemu (firmowe, VPN) nie ma
        # dostepu do 127.0.0.1 na tym komputerze i zwrocilby blad.
        with _BEZ_PROXY.open(zadanie, timeout=LIMIT_CZASU_S) as odp:
            cialo = odp.read()
            return cialo or None
    except urllib.error.HTTPError as exc:
        if exc.code == 401:  # stary token w pliku - Punctum juz nie dziala
            raise _PunctumNieDziala from exc
        raise
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError) or isinstance(exc, TimeoutError):
            raise
        raise _PunctumNieDziala from exc


def _bez_programu(nazwa: str, argumenty: dict) -> list[dict]:
    raise protokol.BladNarzedzia(
        "Punctum is not running. Ask the user to start Punctum (and open a folder "
        "with photos), then try again."
    )


def przetworz_linie(linia: bytes) -> bytes | None:
    linia = linia.strip()
    if not linia:
        return None
    try:
        return _wyslij(linia)
    except _PunctumNieDziala:
        odpowiedz = protokol.obsluz_tekst(linia, _bez_programu)
    except Exception as exc:
        try:
            id_ = json.loads(linia).get("id")
        except Exception:
            id_ = None
        if id_ is None:
            return None
        odpowiedz = {"jsonrpc": "2.0", "id": id_,
                     "result": {"content": [protokol.tekst(f"Punctum did not answer: {exc}")],
                                "isError": True}}
    if odpowiedz is None:
        return None
    return json.dumps(odpowiedz, ensure_ascii=False).encode("utf-8")


def main() -> int:
    wejscie, wyjscie = sys.stdin.buffer, sys.stdout.buffer
    for linia in wejscie:
        odpowiedz = przetworz_linie(linia)
        if odpowiedz:
            # Protokol stdio: jeden komunikat w linii, bez znakow nowej linii
            # w srodku - json.dumps ich nie wstawia.
            wyjscie.write(odpowiedz.strip() + b"\n")
            wyjscie.flush()
    return 0
