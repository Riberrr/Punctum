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


def obraz_z(o: dict):
    obrazy = [c for c in o.get("content", []) if c.get("type") == "image"]
    return Image.open(io.BytesIO(base64.b64decode(obrazy[0]["data"]))) if obrazy else None


def stage_podglad() -> None:
    o = wolaj("set_adjustments", {"values": {"exposure": 1.0, "noise_luminance": 30}})
    przed = obraz_z(wolaj("get_preview", {"view": "before", "max_size": 400}))
    po = obraz_z(wolaj("get_preview", {"max_size": 400}))
    ok = przed is not None and po is not None
    if ok:
        jasnosc = lambda z: sum(z.convert("L").getdata()) / (z.width * z.height)  # noqa: E731
        ok = jasnosc(po) > jasnosc(przed) + 5
    check("przed jest ciemniejsze niz po (+1 EV)", ok, blad(o))
    obok = obraz_z(wolaj("get_preview", {"view": "side_by_side", "max_size": 400}))
    check("obok siebie: dwa obrazy w poziomie", obok is not None and obok.width > obok.height,
          str(obok and obok.size))
    o = wolaj("get_preview", {"crop_100": {"x": 0.5, "y": 0.5, "size": 300}})
    wycinek = obraz_z(o)
    check("wycinek 1:1 ma zadany rozmiar", wycinek is not None and wycinek.size == (300, 300),
          blad(o) or str(wycinek and wycinek.size))


def stage_metadane() -> None:
    p1 = os.path.basename(state["p1"])
    o = wolaj("set_metadata", {"fields": {"title": "Zachód słońca", "keywords": "góry;lato"}})
    meta = window.edits[state["p0"]].metadata
    check("set_metadata: tytul i slowa", meta.get("ImageDescription") == "Zachód słońca"
          and meta.get("XPKeywords") == "góry;lato", blad(o) or str(meta))
    check("...w panelu EXIF", window.exif_panel.path == state["p0"])
    o = wolaj("set_metadata", {"fields": {"keywords": "Tatry"}, "keywords_mode": "add"})
    check("dopisanie slowa", window.edits[state["p0"]].metadata.get("XPKeywords", "")
          .lower().count("tatry") == 1, blad(o))
    o = wolaj("set_metadata", {"fields": {"keywords": "lato"}, "keywords_mode": "remove"})
    check("usuniecie slowa", "lato" not in window.edits[state["p0"]].metadata
          .get("XPKeywords", ""), blad(o))
    o = wolaj("set_metadata", {"fields": {"date_taken": "jutro"}})
    check("zla data -> blad", o.get("isError") is True)
    o = wolaj("set_location", {"photos": [p1], "latitude": 49.2992, "longitude": 19.9496})
    loc = window.edits[state["p1"]]
    check("set_location na nieotwartym", loc.latitude == 49.2992 and loc.longitude == 19.9496,
          blad(o))
    check("...krok w historii Mapy", window.historia_mapy.mozna_cofnac())
    check("...znacznik na pasku", window._has_location(state["p1"]))
    zapisane = read_sidecar(state["p1"])
    check("...w sidecarze", zapisane is not None and zapisane.has_location)
    o = wolaj("remove_location", {"photos": [p1]})
    check("remove_location", window.edits[state["p1"]].latitude is None, blad(o))


def stage_eksport() -> None:
    cel = os.path.join(workspace, "wynik")
    o = wolaj("export_photos", {"target": "current", "folder": cel, "subfolder": "",
                                "format": "jpeg", "max_side": 500, "quality": 80},
              limit_ms=120000)
    wynik = json_z(o) if not o.get("isError") else {}
    pliki = os.listdir(cel) if os.path.isdir(cel) else []
    check("export_photos czeka i zapisuje", wynik.get("saved") == 1 and len(pliki) == 1,
          blad(o) or str(wynik)[:120])
    if pliki:
        z = Image.open(os.path.join(cel, pliki[0]))
        check("...rozmiar z polecenia", max(z.size) == 500, str(z.size))
    check("opcje z polecenia nie trafiaja do ustawien",
          window.settings.export_max_side != 500 or window.settings.export_folder != cel)
    o = wolaj("export_photos", {"target": "current", "folder": cel, "subfolder": "",
                                "max_side": 500, "on_existing": "skip"}, limit_ms=120000)
    check("on_existing skip", not o.get("isError") and json_z(o).get("skipped") == 1, blad(o))
    o = wolaj("get_export_status")
    check("get_export_status po eksporcie", not o.get("isError")
          and json_z(o).get("running") is False, blad(o))
    o = wolaj("export_photos", {"folder": "wzgledny"})
    check("sciezka wzgledna -> blad", o.get("isError") is True)


def stage_ustawienia() -> None:
    from punctum.app.pomoc import OknoPomocy
    from punctum.app.settings_dialog import PAGE_AI, SettingsDialog

    # Port 0 = wolny, wybrany przez system: ponowny start serwera nie moze
    # trafic na port uzywany przez prawdziwy Punctum uzytkownika.
    window.settings.mcp_port = 0
    dialog = SettingsDialog(window.settings, window.system, window)
    dialog.show_page(PAGE_AI)
    check("strona Asystent AI", dialog.current_page() == PAGE_AI)
    pol = protokol.wczytaj_polaczenie(polaczenie)
    check("stan serwera z adresem", pol["url"] in dialog.mcp_stan_label.text(),
          dialog.mcp_stan_label.text())
    check("token w polu, ukryty", dialog.mcp_token_edit.text() == pol["token"]
          and dialog.mcp_token_edit.echoMode() != dialog.mcp_token_edit.EchoMode.Normal)
    check("wszyscy klienci na liscie", len(dialog._mcp_wiersze) >= 10)
    stary = pol["token"]
    dialog.mcp_nowy_button.click()
    nowy = protokol.wczytaj_polaczenie(polaczenie)["token"]
    check("nowy token w pliku i w polu", nowy != stary and dialog.mcp_token_edit.text() == nowy)
    o = wolaj("get_status")
    check("serwer przyjmuje nowy token", not o.get("isError"), blad(o))

    wylaczone = window.settings.copy()
    wylaczone.mcp_enabled = False
    window._przyjmij_ustawienia(wylaczone)
    check("wylaczenie w ustawieniach zatrzymuje serwer", window.mcp is None)
    wlaczone = window.settings.copy()
    wlaczone.mcp_enabled = True
    window._przyjmij_ustawienia(wlaczone)
    check("wlaczenie uruchamia go od razu", window.mcp is not None)
    o = wolaj("get_status")
    check("...i odpowiada", not o.get("isError"), blad(o))
    dialog.close()

    pomoc = OknoPomocy("mcp", "MCP", window)
    check("okno pomocy ma tresc", "MCP" in pomoc.przegladarka.toPlainText())
    pomoc.close()
    akcje = [a.text() for m in window.menuBar().actions() if m.menu()
             for a in m.menu().actions()]
    check("pomoc MCP w menu Pomoc", any("MCP" in a for a in akcje))


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
              stage_podglad, stage_metadane, stage_eksport, stage_ustawienia,
              stage_nawigacja], report)
app.exec()
sys.exit(KOD)
