"""Sterowanie przez AI (MCP) na dzialajacym oknie - prawdziwe wywolania HTTP.

Udaje klienta AI: laczy sie z serwerem okna po HTTP (z innego watku, jak
prawdziwy klient), czyta stan, oglada podglad, zmienia suwaki biezacego
i niebiezacego zdjecia, naklada preset, obraca, kadruje, cofa. Sprawdza, ze
kazda zmiana jest widoczna w oknie, trafia do sidecara i do historii.

Zdjecia sa kopiowane do katalogu tymczasowego (narzedzia zapisuja sidecary),
a plik polaczenia MCP idzie do osobnego katalogu tymczasowego.

Uzycie:  python tools/test_mcp_gui.py <plik.rw2> <plik.jpg> [wiecej...] [--pelny]
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from wspolne import czekaj, lancuch, wypisz, zdjecia  # noqa: E402

from PIL import Image  # noqa: E402

from punctum.app import MainWindow  # noqa: E402
from punctum.core.settings import settings_path  # noqa: E402
from punctum.core.sidecar import read_sidecar  # noqa: E402
from punctum.mcp import protokol  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


SETTINGS_FILE = settings_path()
BACKUP = None
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "rb") as handle:
        BACKUP = handle.read()

workspace = tempfile.mkdtemp(prefix="punctum-mcp-")
polaczenie = tempfile.mkdtemp(prefix="punctum-mcp-pol-")
for source in zdjecia():
    shutil.copy2(source, os.path.join(workspace, os.path.basename(source)))

window = MainWindow()
window.settings.save = lambda *a, **k: True  # zadnych sladow w ustawieniach
window.settings.store_edits = True
window.resize(1500, 950)
window.show()
window.format_combo.setCurrentIndex(window.format_combo.findData("all"))
window.load_folder(workspace)
panel = window.edit_panel
state: dict = {}
_otwieracz = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_numer = [0]


def wolaj(nazwa: str, argumenty: dict | None = None, limit_ms: int = 60000) -> dict:
    """Wywolanie narzedzia z osobnego watku; petla Qt kreci sie w tym czasie,
    bo serwer wykonuje narzedzia w watku okna."""
    dane = protokol.wczytaj_polaczenie(polaczenie)
    _numer[0] += 1
    cialo = json.dumps({"jsonrpc": "2.0", "id": _numer[0], "method": "tools/call",
                        "params": {"name": nazwa, "arguments": argumenty or {}}}).encode()
    wynik: dict = {}

    def watek() -> None:
        zadanie = urllib.request.Request(
            dane["url"], data=cialo, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {dane['token']}"})
        try:
            with _otwieracz.open(zadanie, timeout=limit_ms / 1000) as odp:
                wynik["o"] = json.loads(odp.read())["result"]
        except Exception as exc:  # noqa: BLE001 - test ma zobaczyc kazdy blad
            wynik["o"] = {"isError": True, "content": [{"type": "text", "text": repr(exc)}]}

    threading.Thread(target=watek, daemon=True).start()
    czekaj(app, lambda: "o" in wynik, nazwa, timeout_ms=limit_ms + 2000)
    return wynik.get("o", {"isError": True, "content": [{"type": "text", "text": "brak"}]})


def json_z(o: dict) -> dict:
    return json.loads(o["content"][0]["text"])


def blad(o: dict) -> str:
    return "" if not o.get("isError") else o["content"][0]["text"][:120]


def stage_start() -> None:
    czekaj(app, lambda: window.filmstrip.count() == len(zdjecia()), "lista zdjec")
    czekaj(app, lambda: window.full_raw is not None, "pierwsze zdjecie")
    window.uruchom_mcp(port=0, katalog=polaczenie)
    check("serwer MCP wystartowal", window.mcp is not None and window.mcp.serwer is not None)
    check("plik polaczenia z tokenem", bool(protokol.wczytaj_polaczenie(polaczenie).get("token")))
    state["nazwy"] = [os.path.basename(p) for p in window.paths]
    state["p0"] = window.current_path


def stage_odczyt() -> None:
    o = wolaj("get_status")
    s = json_z(o) if not o.get("isError") else {}
    check("get_status: katalog i zdjecie",
          s.get("folder") == workspace and s.get("open_photo") == os.path.basename(state["p0"]),
          blad(o) or str(s)[:120])
    o = wolaj("list_photos")
    lista = json_z(o) if not o.get("isError") else {}
    check("list_photos: wszystkie zdjecia", lista.get("total") == len(zdjecia()), blad(o))
    o = wolaj("get_photo_info")
    info = json_z(o) if not o.get("isError") else {}
    check("get_photo_info: nastawy", "adjustments" in info, blad(o))
    o = wolaj("get_preview", {"max_size": 800})
    obrazy = [c for c in o.get("content", []) if c.get("type") == "image"]
    ok = False
    if obrazy:
        zdjecie = Image.open(io.BytesIO(base64.b64decode(obrazy[0]["data"])))
        ok = max(zdjecie.size) <= 800 and zdjecie.format == "JPEG"
    check("get_preview: obraz JPEG do 800 px", ok, blad(o))
    o = wolaj("get_image_stats")
    check("get_image_stats", not o.get("isError") and "brightness_0_255" in json_z(o), blad(o))


def stage_edycja() -> None:
    o = wolaj("set_adjustments", {"values": {"exposure": 0.5}})
    check("wartosc bezwzgledna na suwaku", panel.sliders["exposure"].value() == 0.5,
          blad(o) or str(panel.sliders["exposure"].value()))
    o = wolaj("set_adjustments", {"deltas": {"exposure": 0.25, "contrast": 12}})
    check("zmiana wzgledna", panel.sliders["exposure"].value() == 0.75
          and panel.sliders["contrast"].value() == 12, blad(o))
    zapisane = read_sidecar(state["p0"])
    check("zmiana trafila do sidecara", zapisane is not None and zapisane.exposure == 0.75,
          str(zapisane and zapisane.exposure))
    check("zmiana jest krokiem historii", panel.undo_button.isEnabled())
    o = wolaj("set_adjustments", {"values": {"exposure": 99}})
    check("wartosc przycieta do suwaka", panel.sliders["exposure"].value() == 5.0, blad(o))
    o = wolaj("undo")
    check("undo cofa zmiane AI", panel.sliders["exposure"].value() == 0.75, blad(o))
    o = wolaj("set_adjustments", {"values": {"brightness": 3}})
    check("nieznane pole -> blad dla modelu", o.get("isError") is True)
    o = wolaj("open_photo", {"photo": "nie-ma-takiego.jpg"})
    check("nieznane zdjecie -> blad dla modelu", o.get("isError") is True)


def stage_wiele() -> None:
    inne = [p for p in window.paths if p != state["p0"]]
    state["p1"] = inne[0]
    o = wolaj("select_photos", {"all": True})
    check("select_photos all", len(window.filmstrip.selected_paths()) == len(window.paths),
          blad(o))
    o = wolaj("set_adjustments", {"target": "selected", "deltas": {"vibrance": 20}})
    obce = window.edits.get(state["p1"])
    check("zmiana na zdjeciu nieotwartym", obce is not None and obce.vibrance == 20,
          blad(o) or str(obce and obce.vibrance))
    check("...zapisana w jego sidecarze",
          (read_sidecar(state["p1"]) or window.edits[state["p1"]]).vibrance == 20)
    check("...i w jego historii", window.historia.mozna_cofnac(state["p1"]))
    check("biezace tez zmienione", panel.sliders["vibrance"].value() == 20)
    o = wolaj("copy_adjustments", {"source": os.path.basename(state["p0"]),
                                   "photos": [os.path.basename(state["p1"])],
                                   "groups": ["ton"]})
    check("copy_adjustments", window.edits[state["p1"]].exposure == 0.75, blad(o))
    o = wolaj("select_photos", {"format": "jpeg"})
    jpegi = sum(1 for p in window.paths if p.lower().endswith((".jpg", ".jpeg")))
    check("select_photos po formacie", len(window.filmstrip.selected_paths()) == jpegi, blad(o))


def stage_wyglad() -> None:
    o = wolaj("apply_preset", {"name": "Monochrom"})
    check("preset Monochrom wlacza czern i biel", panel.mono_check.isChecked(), blad(o))
    o = wolaj("set_monochrome", {"enabled": False})
    check("set_monochrome wylacza", not panel.mono_check.isChecked(), blad(o))
    o = wolaj("apply_preset", {"name": "nie-ma"})
    check("nieznany preset -> lista dostepnych", o.get("isError") and "Available" in blad(o))
    o = wolaj("rotate", {"direction": "right"})
    check("rotate right", window.orientation == 90, blad(o) or str(window.orientation))
    o = wolaj("set_crop", {"aspect": "1:1"})
    l, g, p, d = window.crop
    from punctum.core import EditParams, geometry_size
    szer, wys = geometry_size(window.full_raw, EditParams(orientation=window.orientation))
    check("set_crop 1:1 daje kwadrat", abs((p - l) * szer - (d - g) * wys) < 3,
          blad(o) or f"{(p - l) * szer:.0f} x {(d - g) * wys:.0f}")
    o = wolaj("auto_adjust")
    check("auto_adjust", not o.get("isError"), blad(o))
    o = wolaj("reset_adjustments")
    check("reset_adjustments", window.orientation == 0 and panel.sliders["contrast"].value() == 0,
          blad(o))


def stage_nawigacja() -> None:
    o = wolaj("open_photo", {"photo": os.path.basename(state["p1"])})
    check("open_photo czeka na wczytanie", window.current_path == state["p1"]
          and window.current_image is not None, blad(o))
    check("pasek miniatur pokazuje to samo zdjecie",
          window.filmstrip.current_path() == state["p1"])
    check("po otwarciu widac zmiane AI", panel.sliders["vibrance"].value() == 20)
    check("i mozna ja cofnac", panel.undo_button.isEnabled())
    window.zatrzymaj_mcp()
    check("zatrzymanie serwera", window.mcp is None)


KOD = 0


def report() -> None:
    global KOD
    try:
        KOD = wypisz(results, szerokosc=56)
    finally:
        window.zatrzymaj_mcp()
        window.close()
        window.pool.waitForDone(5000)
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(polaczenie, ignore_errors=True)
        if BACKUP is not None:
            with open(SETTINGS_FILE, "wb") as handle:
                handle.write(BACKUP)
        app.quit()


lancuch(app, [stage_start, stage_odczyt, stage_edycja, stage_wiele, stage_wyglad,
              stage_nawigacja], report)
app.exec()
sys.exit(KOD)
