"""Podlaczanie Punctum do klientow AI na tym komputerze (konfigurator).

Kazdy klient to jeden wiersz tabeli `KLIENCI`: gdzie trzyma konfiguracje
serwerow MCP, w jakiej sekcji i jak go wykryc. Dodanie nowego klienta to
dopisanie wiersza. Formaty zmieniaja sie z wersjami klientow - stan
sprawdzony we wrzesniu 2026 (notatka punctum-mcp.md).

Zasady zapisu (plik nalezy do innego programu):
- zmieniamy tylko wpis "punctum", reszte pliku zostawiamy nietknieta,
- przed zapisem kopia `<plik>.punctum-kopia`,
- plik, ktorego nie umiemy przeczytac (blad skladni, komentarze w JSON),
  zostaje nietkniety - konfigurator pokaze wtedy wpis do wklejenia recznie.

Modul bez Qt: komunikaty dla uzytkownika sklada okno ustawien z kodu bledu
(`BladKonfiguracji.kod`), zeby przeszly przez przeklad.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable

NAZWA = "punctum"
KOPIA = ".punctum-kopia"

# Katalogi systemowe; testy podstawiaja katalog tymczasowy.
_KATALOGI: dict[str, str] = {}


def ustaw_katalogi(appdata: str, localappdata: str, home: str) -> None:
    _KATALOGI.update(APPDATA=appdata, LOCALAPPDATA=localappdata, HOME=home)


def _kat(nazwa: str) -> str:
    if nazwa in _KATALOGI:
        return _KATALOGI[nazwa]
    if nazwa == "HOME":
        return os.path.expanduser("~")
    return os.environ.get(nazwa, "")


class BladKonfiguracji(Exception):
    """kod: "zepsuty" (nie da sie przeczytac pliku), "zapis" (nie da sie
    zapisac), "polecenie" (program klienta zwrocil blad)."""

    def __init__(self, kod: str, sciezka: str = "", szczegoly: str = ""):
        super().__init__(f"{kod}: {sciezka} {szczegoly}".strip())
        self.kod, self.sciezka, self.szczegoly = kod, sciezka, szczegoly


# ------------------------------------------------------------ polecenie mostka

def polecenie_mostka() -> dict:
    """Jak klient AI ma uruchomic mostek: interpreter programu + modul.

    pythonw zamiast python: klient uruchamia mostek w tle, a python.exe
    otwieralby przy tym puste okno konsoli (Node na Windows domyslnie go
    nie ukrywa). Stdin/stdout mostka to potoki klienta, wiec pythonw je ma.
    Katalog nad pakietem idzie w PYTHONPATH - bez tego `-m punctum.mcp`
    nie znalazloby pakietu, bo klient startuje w swoim katalogu roboczym.
    Po kompilacji (punkt 18) mostek to PunctumMCP.exe obok Punctum.exe -
    bez interpretera i bez PYTHONPATH.
    """
    # Nuitka wstawia __compiled__ do kazdego skompilowanego modulu;
    # containing_dir to katalog z Punctum.exe.
    skompilowany = globals().get("__compiled__")
    if skompilowany is not None:
        mostek = os.path.join(skompilowany.containing_dir, "PunctumMCP.exe")
        return {"command": mostek, "args": [], "env": {}}
    # Najpierw Scripts venv: program startowany przez Punctum.exe (punkt 29)
    # ma sys.executable w .venv\Punctum, a mostek nie powinien udawac
    # w Menedzerze zadan drugiego Punctum. Wpis w konfiguracji klienta
    # zostaje przy tym taki sam jak przy starcie z pythonw.
    interpreter = sys.executable
    for katalog in (os.path.join(sys.prefix, "Scripts"), os.path.dirname(interpreter)):
        kandydaci = [os.path.join(katalog, n) for n in ("pythonw.exe", "python.exe")]
        znaleziony = next((k for k in kandydaci if os.path.isfile(k)), None)
        if znaleziony:
            interpreter = znaleziony
            break
    pakiet = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return {"command": interpreter, "args": ["-m", "punctum.mcp"],
            "env": {"PYTHONPATH": pakiet}}


def konfiguracja_do_wklejenia() -> str:
    """Blok JSON w najczestszym formacie ("mcpServers") - dla klientow spoza listy."""
    return json.dumps({"mcpServers": {NAZWA: polecenie_mostka()}}, indent=2, ensure_ascii=False)


# ------------------------------------------------------------ pliki JSON / TOML

def _czytaj_json(sciezka: str) -> dict:
    if not os.path.exists(sciezka):
        return {}
    try:
        with open(sciezka, encoding="utf-8-sig") as f:
            tresc = f.read()
        dane = json.loads(tresc) if tresc.strip() else {}
    except (OSError, ValueError) as exc:
        raise BladKonfiguracji("zepsuty", sciezka, str(exc)) from exc
    if not isinstance(dane, dict):
        raise BladKonfiguracji("zepsuty", sciezka)
    return dane


def _zapisz_tekst(sciezka: str, tekst: str) -> None:
    try:
        os.makedirs(os.path.dirname(sciezka), exist_ok=True)
        if os.path.exists(sciezka):
            shutil.copy2(sciezka, sciezka + KOPIA)
        tymczasowy = sciezka + ".punctum-tmp"
        with open(tymczasowy, "w", encoding="utf-8", newline="\n") as f:
            f.write(tekst)
        os.replace(tymczasowy, sciezka)
    except OSError as exc:
        raise BladKonfiguracji("zapis", sciezka, str(exc)) from exc


def _json_ma(sciezka: str, sekcja: str) -> bool:
    try:
        return NAZWA in (_czytaj_json(sciezka).get(sekcja) or {})
    except BladKonfiguracji:
        return False


def _json_wpisz(sciezka: str, sekcja: str, wpis: dict | None) -> None:
    dane = _czytaj_json(sciezka)
    serwery = dane.get(sekcja)
    if not isinstance(serwery, dict):
        if wpis is None:
            return
        serwery = dane[sekcja] = {}
    if wpis is None:
        if NAZWA not in serwery:
            return
        del serwery[NAZWA]
    else:
        serwery[NAZWA] = wpis
    _zapisz_tekst(sciezka, json.dumps(dane, indent=2, ensure_ascii=False) + "\n")


_NAGLOWEK_TOML = f"[mcp_servers.{NAZWA}"


def _toml_bez_wpisu(tekst: str) -> str:
    """Tekst TOML bez tabel [mcp_servers.punctum] i [mcp_servers.punctum.*].

    Na tekscie, nie przez parser: biblioteka standardowa TOML tylko czyta,
    a przepisanie calego pliku zgubiloby komentarze uzytkownika.
    """
    wynik, pomijamy = [], False
    for linia in tekst.splitlines(keepends=True):
        naglowek = linia.strip()
        if naglowek.startswith("["):
            pomijamy = (naglowek.startswith(_NAGLOWEK_TOML + "]")
                        or naglowek.startswith(_NAGLOWEK_TOML + "."))
        if not pomijamy:
            wynik.append(linia)
    return "".join(wynik).rstrip() + ("\n" if wynik else "")


def _czytaj_toml(sciezka: str) -> str:
    import tomllib

    if not os.path.exists(sciezka):
        return ""
    try:
        with open(sciezka, encoding="utf-8") as f:
            tekst = f.read()
        tomllib.loads(tekst)
    except (OSError, ValueError) as exc:  # TOMLDecodeError dziedziczy po ValueError
        raise BladKonfiguracji("zepsuty", sciezka, str(exc)) from exc
    return tekst


def _toml_ma(sciezka: str, sekcja: str) -> bool:
    import tomllib

    try:
        return NAZWA in tomllib.loads(_czytaj_toml(sciezka)).get(sekcja, {})
    except BladKonfiguracji:
        return False


def _toml_wpisz(sciezka: str, sekcja: str, wpis: dict | None) -> None:
    tekst = _czytaj_toml(sciezka)
    bez = _toml_bez_wpisu(tekst)
    if wpis is None:
        if bez != tekst:
            _zapisz_tekst(sciezka, bez)
        return
    # json.dumps daje napis poprawny takze w TOML (cudzyslowy, ukosniki).
    blok = [f"[{sekcja}.{NAZWA}]",
            f"command = {json.dumps(wpis['command'], ensure_ascii=False)}",
            f"args = {json.dumps(wpis['args'], ensure_ascii=False)}", "",
            f"[{sekcja}.{NAZWA}.env]"]
    blok += [f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in wpis["env"].items()]
    _zapisz_tekst(sciezka, (bez + "\n" if bez else "") + "\n".join(blok) + "\n")


# ------------------------------------------------------------------- klienci

@dataclass
class Klient:
    klucz: str
    nazwa: str  # nazwa wlasna programu - bez przekladu
    rodzaj: str  # json | toml | cli | reczny
    pliki: Callable[[], list[str]] = lambda: []
    sekcja: str = "mcpServers"
    wykryj: Callable[[], bool] = lambda: False
    typ_stdio: bool = False  # VS Code chce "type": "stdio" we wpisie
    uwaga: str = ""  # klucz uwagi pokazywanej w oknie (przeklad po stronie okna)
    polecenie: tuple[str, ...] = field(default_factory=tuple)  # dla rodzaj == "cli"


def _istnieje(*czesci: str) -> bool:
    return bool(czesci[0]) and os.path.isdir(os.path.join(*czesci))


def _claude_desktop_pliki() -> list[str]:
    # Wersja ze Sklepu Microsoft czyta plik z wirtualnego katalogu pakietu,
    # choc przycisk "Edit Config" w samej aplikacji otwiera %APPDATA%
    # (claude-code #26073). Zapisujemy do obu - ktory by nie byl czytany,
    # wpis tam jest.
    pliki = sorted(glob.glob(os.path.join(
        _kat("LOCALAPPDATA"), "Packages", "Claude_*", "LocalCache", "Roaming", "Claude",
        "claude_desktop_config.json")))
    pakiety = glob.glob(os.path.join(_kat("LOCALAPPDATA"), "Packages", "Claude_*",
                                     "LocalCache", "Roaming", "Claude"))
    pliki += [os.path.join(p, "claude_desktop_config.json") for p in pakiety
              if os.path.join(p, "claude_desktop_config.json") not in pliki]
    if _istnieje(_kat("APPDATA"), "Claude"):
        pliki.append(os.path.join(_kat("APPDATA"), "Claude", "claude_desktop_config.json"))
    return pliki


def _home(*czesci: str) -> Callable[[], list[str]]:
    return lambda: [os.path.join(_kat("HOME"), *czesci)]


def _appdata(*czesci: str) -> Callable[[], list[str]]:
    return lambda: [os.path.join(_kat("APPDATA"), *czesci)]


KLIENCI: tuple[Klient, ...] = (
    Klient("claude_desktop", "Claude Desktop", "json", _claude_desktop_pliki,
           wykryj=lambda: bool(_claude_desktop_pliki()), uwaga="restart"),
    Klient("claude_code", "Claude Code", "cli", _home(".claude.json"),
           wykryj=lambda: shutil.which("claude") is not None,
           polecenie=("claude", "mcp")),
    Klient("cursor", "Cursor", "json", _home(".cursor", "mcp.json"),
           wykryj=lambda: _istnieje(_kat("HOME"), ".cursor")),
    Klient("vscode", "VS Code (Copilot)", "json", _appdata("Code", "User", "mcp.json"),
           sekcja="servers", typ_stdio=True,
           wykryj=lambda: _istnieje(_kat("APPDATA"), "Code", "User")),
    Klient("windsurf", "Windsurf", "json", _home(".codeium", "windsurf", "mcp_config.json"),
           wykryj=lambda: _istnieje(_kat("HOME"), ".codeium", "windsurf")),
    Klient("lmstudio", "LM Studio", "json", _home(".lmstudio", "mcp.json"),
           wykryj=lambda: _istnieje(_kat("HOME"), ".lmstudio")),
    Klient("gemini", "Gemini CLI", "json", _home(".gemini", "settings.json"),
           wykryj=lambda: _istnieje(_kat("HOME"), ".gemini")),
    Klient("codex", "OpenAI Codex", "toml", _home(".codex", "config.toml"),
           sekcja="mcp_servers", wykryj=lambda: _istnieje(_kat("HOME"), ".codex")),
    Klient("cline", "Cline", "json", _appdata(
        "Code", "User", "globalStorage", "saoudrizwan.claude-dev", "settings",
        "cline_mcp_settings.json"),
        wykryj=lambda: _istnieje(_kat("APPDATA"), "Code", "User", "globalStorage",
                                 "saoudrizwan.claude-dev")),
    # Zed trzyma serwery w settings.json z komentarzami (JSONC), a JetBrains
    # w oknie ustawien IDE - tu tylko instrukcja i wpis do skopiowania.
    Klient("zed", "Zed", "reczny", uwaga="zed"),
    Klient("jetbrains", "JetBrains AI Assistant", "reczny", uwaga="jetbrains"),
    Klient("chatgpt", "ChatGPT", "reczny", uwaga="chatgpt"),
)
KLIENCI_PO_KLUCZU = {k.klucz: k for k in KLIENCI}

# Stany klienta
BRAK, NIEPOLACZONY, POLACZONY, RECZNY = "brak", "niepolaczony", "polaczony", "reczny"


def wpis_dla(klient: Klient) -> dict:
    wpis = polecenie_mostka()
    if klient.typ_stdio:
        wpis = {"type": "stdio", **wpis}
    return wpis


def stan(klient: Klient) -> str:
    if klient.rodzaj == "reczny":
        return RECZNY
    if not klient.wykryj():
        return BRAK
    sprawdz = _toml_ma if klient.rodzaj == "toml" else _json_ma
    return (POLACZONY if any(sprawdz(p, klient.sekcja) for p in klient.pliki())
            else NIEPOLACZONY)


def _uruchom(argumenty: list[str]) -> None:
    program = shutil.which(argumenty[0])
    if program is None:
        raise BladKonfiguracji("polecenie", argumenty[0], "not found")
    flagi = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    wynik = subprocess.run([program, *argumenty[1:]], capture_output=True, text=True,
                           timeout=60, creationflags=flagi)
    if wynik.returncode != 0:
        raise BladKonfiguracji("polecenie", " ".join(argumenty[:3]),
                               (wynik.stderr or wynik.stdout).strip()[:300])


def polacz(klient: Klient) -> list[str]:
    """Dopisuje Punctum do klienta. Zwraca zmienione pliki."""
    if klient.rodzaj == "cli":
        wpis = polecenie_mostka()
        env = [f"{k}={v}" for k, v in wpis["env"].items()]
        # Najpierw usuniecie: "add" na istniejacej nazwie konczy sie bledem.
        try:
            _uruchom([*klient.polecenie, "remove", "--scope", "user", NAZWA])
        except BladKonfiguracji:
            pass
        _uruchom([*klient.polecenie, "add", "--scope", "user",
                  *[x for e in env for x in ("-e", e)], NAZWA, "--",
                  wpis["command"], *wpis["args"]])
        return klient.pliki()
    zapis = _toml_wpisz if klient.rodzaj == "toml" else _json_wpisz
    pliki = klient.pliki()
    for sciezka in pliki:
        zapis(sciezka, klient.sekcja, wpis_dla(klient))
    return pliki


def odlacz(klient: Klient) -> list[str]:
    if klient.rodzaj == "cli":
        _uruchom([*klient.polecenie, "remove", "--scope", "user", NAZWA])
        return klient.pliki()
    zapis = _toml_wpisz if klient.rodzaj == "toml" else _json_wpisz
    pliki = [p for p in klient.pliki() if os.path.exists(p)]
    for sciezka in pliki:
        zapis(sciezka, klient.sekcja, None)
    return pliki
