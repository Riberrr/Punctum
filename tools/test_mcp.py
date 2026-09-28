"""Serwer MCP bez okna: opisy narzedzi, protokol, HTTP, mostek stdio.

Pilnuje zasady 16 briefu: kazde pole `EditParams` ustawiane suwakiem ma
zakres i opis w `mcp/narzedzia.py` - nowe pole bez obslugi w MCP wywraca
ten test. Do tego bezpieczenstwo serwera (token, Origin, tylko 127.0.0.1)
i zachowanie mostka przy zamknietym programie.

Uzycie:  python tools/test_mcp.py [--pelny]
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from wspolne import wypisz  # noqa: E402

import numpy as np  # noqa: E402

from punctum.core import EditParams  # noqa: E402
from punctum.core import presety  # noqa: E402
from punctum.mcp import most, narzedzia, protokol  # noqa: E402
from punctum.app.mcp_polecenia import kadr_o_proporcji, statystyki  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# --- opisy narzedzi ----------------------------------------------------------

POZA_SUWAKAMI = {"orientation", "crop", "latitude", "longitude", "metadata", "mono"}
pola = {f.name for f in dataclasses.fields(EditParams)} - POZA_SUWAKAMI
brak = sorted(pola - set(narzedzia.ZAKRESY))
check("kazde pole suwaka ma zakres w MCP", not brak, ", ".join(brak))
check("kazde pole ma opis dla modelu", set(narzedzia.ZAKRESY) == set(narzedzia.OPISY_POL))
check("zadnych zakresow dla nieistniejacych pol", set(narzedzia.ZAKRESY) <= pola)
rozne = [k for k, z in presety._ZAKRESY.items() if narzedzia.ZAKRESY.get(k) != z]
check("zakresy zgodne z presetami", not rozne, ", ".join(rozne))
check("grupy jak w presetach", set(narzedzia.GRUPY) == set(presety.GRUPY))
check("filtry jak w presetach", set(narzedzia.FILTRY) - {"brak"} == set(presety.FILTRY))
nazwy = [n["name"] for n in narzedzia.NARZEDZIA]
check("nazwy narzedzi bez powtorzen", len(nazwy) == len(set(nazwy)))
check("schematy to obiekty JSON", all(n["inputSchema"]["type"] == "object"
                                      for n in narzedzia.NARZEDZIA))
check("opisy po angielsku (bez ogonkow)", all(
    all(ord(c) < 128 for c in json.dumps(n, ensure_ascii=False)) for n in narzedzia.NARZEDZIA))
wymagane_z_grup = {"get_status", "list_photos", "get_preview", "open_photo",
                   "select_photos", "set_adjustments", "auto_adjust", "apply_preset",
                   "undo"}
check("narzedzia grup 1-3 sa na liscie", wymagane_z_grup <= set(nazwy))

from punctum.app.mcp_polecenia import PoleceniaMCP  # noqa: E402
bez_kodu = [n for n in nazwy if not hasattr(PoleceniaMCP, "n_" + n)]
check("kazde narzedzie ma wykonanie w oknie", not bez_kodu, ", ".join(bez_kodu))


# --- protokol ----------------------------------------------------------------

def wykonaj(nazwa: str, argumenty: dict) -> list[dict]:
    if nazwa == "undo":
        raise protokol.BladNarzedzia("nic do cofniecia")
    if nazwa == "redo":
        raise RuntimeError("awaria")
    return [protokol.dane({"nazwa": nazwa, "argumenty": argumenty})]


def rpc(metoda: str, parametry: dict | None = None, id_: int | None = 1) -> dict:
    k = {"jsonrpc": "2.0", "method": metoda}
    if parametry is not None:
        k["params"] = parametry
    if id_ is not None:
        k["id"] = id_
    return k


o = protokol.obsluz(rpc("initialize", {"protocolVersion": "2025-03-26"}), wykonaj)
check("initialize oddaje wersje klienta", o["result"]["protocolVersion"] == "2025-03-26")
check("initialize: narzedzia i nazwa", o["result"]["capabilities"].get("tools") is not None
      and o["result"]["serverInfo"]["name"] == "punctum")
o = protokol.obsluz(rpc("initialize", {"protocolVersion": "1999-01-01"}), wykonaj)
check("nieznana wersja -> nasza najnowsza",
      o["result"]["protocolVersion"] == protokol.WERSJE_PROTOKOLU[0])
check("powiadomienie bez odpowiedzi",
      protokol.obsluz(rpc("notifications/initialized", id_=None), wykonaj) is None)
o = protokol.obsluz(rpc("tools/list"), wykonaj)
check("tools/list", len(o["result"]["tools"]) == len(narzedzia.NARZEDZIA))
o = protokol.obsluz(rpc("tools/call", {"name": "get_status", "arguments": {}}), wykonaj)
check("tools/call", o["result"]["isError"] is False
      and "get_status" in o["result"]["content"][0]["text"])
o = protokol.obsluz(rpc("tools/call", {"name": "undo"}), wykonaj)
check("blad narzedzia jako isError", o["result"]["isError"]
      and "cofniecia" in o["result"]["content"][0]["text"])
o = protokol.obsluz(rpc("tools/call", {"name": "redo"}), wykonaj)
check("wyjatek programu nie zrywa polaczenia", o["result"]["isError"])
o = protokol.obsluz(rpc("tools/call", {"name": "format_c"}), wykonaj)
check("nieznane narzedzie -> -32602", o["error"]["code"] == -32602)
o = protokol.obsluz(rpc("resources/list"), wykonaj)
check("nieznana metoda -> -32601", o["error"]["code"] == -32601)
check("zly JSON -> -32700", protokol.obsluz_tekst(b"{nie json", wykonaj)["error"]["code"] == -32700)


# --- serwer HTTP i mostek ------------------------------------------------------

def post(url: str, cialo: bytes, naglowki: dict) -> tuple[int, bytes]:
    otwieracz = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    zadanie = urllib.request.Request(url, data=cialo, method="POST", headers=naglowki)
    try:
        with otwieracz.open(zadanie, timeout=10) as odp:
            return odp.status, odp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


with tempfile.TemporaryDirectory() as katalog:
    token = protokol.token_z_pliku(katalog)
    check("nowy token jest dlugi", len(token) >= 32)
    serwer = protokol.SerwerMCP(wykonaj, token, port=0)  # port wolny, wybrany przez system
    serwer.uruchom()
    try:
        check("serwer slucha tylko na 127.0.0.1", serwer.server_address[0] == "127.0.0.1")
        protokol.zapisz_polaczenie(serwer.port, token, katalog)
        check("token trwa miedzy uruchomieniami", protokol.token_z_pliku(katalog) == token)
        url = f"http://127.0.0.1:{serwer.port}/mcp"
        cialo = json.dumps(rpc("tools/list")).encode()
        dobre = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        kod, _ = post(url, cialo, {"Content-Type": "application/json"})
        check("bez tokenu -> 401", kod == 401, str(kod))
        kod, _ = post(url, cialo, {**dobre, "Authorization": "Bearer zly"})
        check("zly token -> 401", kod == 401, str(kod))
        kod, _ = post(url, cialo, {**dobre, "Origin": "https://zla-strona.example"})
        check("obcy Origin -> 403", kod == 403, str(kod))
        kod, tresc = post(url, cialo, {**dobre, "Origin": "http://localhost:3000"})
        check("Origin localhost przepuszczony", kod == 200, str(kod))
        kod, tresc = post(url, cialo, dobre)
        check("tools/list przez HTTP", kod == 200 and len(json.loads(tresc)["result"]["tools"])
              == len(narzedzia.NARZEDZIA))
        kod, tresc = post(url, json.dumps(rpc("notifications/initialized", id_=None)).encode(),
                          dobre)
        check("powiadomienie -> 202 bez tresci", kod == 202 and not tresc, str(kod))
        kod, _ = post(f"http://127.0.0.1:{serwer.port}/inne", cialo, dobre)
        check("inna sciezka -> 404", kod == 404, str(kod))

        most.KATALOG_POLACZENIA = katalog
        linia = json.dumps(rpc("tools/call", {"name": "get_status"}, id_=7)).encode()
        o = json.loads(most.przetworz_linie(linia))
        check("mostek przekazuje wywolanie", o["id"] == 7 and not o["result"]["isError"])
        check("mostek: powiadomienie bez odpowiedzi", most.przetworz_linie(
            json.dumps(rpc("notifications/initialized", id_=None)).encode()) is None)
        check("mostek: pusta linia", most.przetworz_linie(b"\n") is None)
    finally:
        serwer.zatrzymaj()

    # Program zamkniety: plik polaczenia zostal, ale nikt nie slucha.
    o = json.loads(most.przetworz_linie(json.dumps(rpc("initialize", {})).encode()))
    check("mostek bez programu: initialize", o["result"]["serverInfo"]["name"] == "punctum")
    o = json.loads(most.przetworz_linie(json.dumps(rpc("tools/list", id_=2)).encode()))
    check("mostek bez programu: lista narzedzi", len(o["result"]["tools"])
          == len(narzedzia.NARZEDZIA))
    o = json.loads(most.przetworz_linie(
        json.dumps(rpc("tools/call", {"name": "get_status"}, id_=3)).encode()))
    check("mostek bez programu: prosba o uruchomienie", o["result"]["isError"]
          and "not running" in o["result"]["content"][0]["text"])

with tempfile.TemporaryDirectory() as pusty:
    most.KATALOG_POLACZENIA = pusty
    o = json.loads(most.przetworz_linie(json.dumps(rpc("ping", id_=4)).encode()))
    check("mostek bez pliku polaczenia: ping", o.get("result") == {})
most.KATALOG_POLACZENIA = None


# --- kadr i statystyki ---------------------------------------------------------

def blisko(a, b) -> bool:
    return all(abs(x - y) < 1e-6 for x, y in zip(a, b))


check("3:2 na zdjeciu 3:2 = caly kadr", blisko(kadr_o_proporcji(6000, 4000, 1.5),
                                               (0, 0, 1, 1)))
check("1:1 na poziomym", blisko(kadr_o_proporcji(6000, 4000, 1.0), (1 / 6, 0, 5 / 6, 1)))
check("3:2 na pionowym zostaje pionem", blisko(kadr_o_proporcji(4000, 6000, 1.5),
                                               (0, 0, 1, 1)))
check("16:9 na poziomym 3:2 tnie gore i dol",
      blisko(kadr_o_proporcji(6000, 4000, 16 / 9), (0, (1 - 0.84375) / 2, 1, (1 + 0.84375) / 2)))

obraz = np.zeros((100, 200, 3), dtype=np.uint8)
obraz[:, 100:] = 255
s = statystyki(obraz)
check("statystyki: polowa w czerni, polowa w bieli",
      abs(s["clipped_shadows_percent"] - 50) < 0.1 and abs(s["clipped_highlights_percent"] - 50) < 0.1)
check("statystyki: 16 przedzialow po 100 %", abs(sum(s["histogram_16_bins_percent"]) - 100) < 0.5)

sys.exit(wypisz(results))
