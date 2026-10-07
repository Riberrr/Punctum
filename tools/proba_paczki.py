"""Proba startu skompilowanego programu (punkt 31 D), w CI po kompilacji.

    python tools/proba_paczki.py [katalog_kompilacji]
    python tools/proba_paczki.py --zrodla   # ten sam start programu ze zrodel

Sprawdza to, czego testy ze zrodel nie widza: ze mostek MCP (ten sam plik
pod druga nazwa) wybiera swoje wejscie i odpowiada na initialize i
tools/list, oraz ze program z oknem wstaje i nie pada w pierwszych
sekundach (Qt offscreen - maszyna CI nie ma ekranu ani prawdziwego GPU,
wiec wygladu i shadera to nie sprawdza). Kod wyjscia = liczba bledow.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CZAS_OKNA_S = 30


def programy(kompilacja: str) -> tuple[str, str]:
    if sys.platform == "darwin":
        katalog = os.path.join(kompilacja, "Punctum.app", "Contents", "MacOS")
        return os.path.join(katalog, "PunctumApp"), os.path.join(katalog, "PunctumMCP")
    katalog = os.path.join(kompilacja, "Punctum")
    return os.path.join(katalog, "Punctum.exe"), os.path.join(katalog, "PunctumMCP.exe")


def proba_mostka(mostek: str) -> bool:
    zapytania = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "proba", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    wejscie = "".join(json.dumps(z) + "\n" for z in zapytania)
    proces = subprocess.Popen([mostek], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        wyjscie, bledy = proces.communicate(wejscie, timeout=90)
    except subprocess.TimeoutExpired:
        # Odpowiedzi mogly juz przyjsc, a mostek tylko nie zauwazyl konca
        # wejscia - ocena po tym, co wypisal.
        proces.kill()
        wyjscie, bledy = proces.communicate()
    odpowiedzi = {}
    for linia in wyjscie.splitlines():
        try:
            o = json.loads(linia)
        except ValueError:
            continue
        if isinstance(o, dict) and "id" in o:
            odpowiedzi[o["id"]] = o
    narzedzia = odpowiedzi.get(2, {}).get("result", {}).get("tools", [])
    ok = "result" in odpowiedzi.get(1, {}) and len(narzedzia) > 0
    print(f"mostek: {'OK' if ok else 'BLAD'}, narzedzi {len(narzedzia)}", flush=True)
    if not ok:
        print(wyjscie[-3000:], bledy[-3000:], sep="\n")
    return ok


def _raport_awarii(nazwa: str, od: float) -> None:
    """Stos watku, ktory padl, z raportu awarii macOS (.ips).

    Sygnal (np. -11) z kodu natywnego nie zostawia Pythonowego sladu;
    system zapisuje wtedy raport z nazwami funkcji bibliotek - jedyny
    sposob, zeby zobaczyc winowajce bez Maca pod reka.
    """
    katalog = os.path.expanduser("~/Library/Logs/DiagnosticReports")
    try:
        pliki = [os.path.join(katalog, n) for n in os.listdir(katalog)
                 if n.startswith(nazwa) and n.endswith(".ips")]
    except OSError:
        return
    pliki = [p for p in pliki if os.path.getmtime(p) >= od - 5]
    if not pliki:
        print("brak raportu awarii")
        return
    tekst = open(max(pliki, key=os.path.getmtime), encoding="utf-8", errors="replace").read()
    try:
        dane = json.loads(tekst.split("\n", 1)[1])
    except (ValueError, IndexError):
        print(tekst[:4000])
        return
    print("wyjatek:", dane.get("exception"), dane.get("termination", {}).get("indicator"))
    obrazy = dane.get("usedImages", [])
    for watek in dane.get("threads", []):
        if not watek.get("triggered"):
            continue
        print("watek:", watek.get("name") or watek.get("queue") or watek.get("id"))
        for ramka in watek.get("frames", [])[:45]:
            i = ramka.get("imageIndex")
            obraz = obrazy[i].get("name", "?") if isinstance(i, int) and i < len(obrazy) else "?"
            print(f"  {obraz}  {ramka.get('symbol', hex(ramka.get('imageOffset', 0)))}")


def proba_okna(program: str | list[str]) -> bool:
    srodowisko = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    polecenie = program if isinstance(program, list) else [program]
    start = time.time()
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as dziennik:
        proces = subprocess.Popen(polecenie, stdout=dziennik, stderr=subprocess.STDOUT, env=srodowisko,
                                  cwd=REPO)
        koniec = time.monotonic() + CZAS_OKNA_S
        while time.monotonic() < koniec and proces.poll() is None:
            time.sleep(1)
        zyje = proces.poll() is None
        if zyje:
            proces.terminate()
            try:
                proces.wait(15)
            except subprocess.TimeoutExpired:
                proces.kill()
        dziennik.seek(0)
        tresc = dziennik.read()
    print(f"program: {'OK' if zyje else f'BLAD - zakonczyl sie z kodem {proces.returncode}'}"
          f" po {CZAS_OKNA_S} s", flush=True)
    if not zyje or "Traceback" in tresc:
        print(tresc[-5000:])
    if not zyje and sys.platform == "darwin":
        time.sleep(5)  # raport awarii powstaje chwile po smierci procesu
        _raport_awarii(os.path.basename(polecenie[0]), start)
    return zyje and "Traceback" not in tresc


def main() -> int:
    if "--zrodla" in sys.argv:
        return int(not proba_okna([sys.executable, "-m", "punctum"]))
    argumenty = [a for a in sys.argv[1:] if not a.startswith("--")]
    kompilacja = os.path.abspath(argumenty[0] if argumenty else os.path.join(REPO, "..", "kompilacja"))
    program, mostek = programy(kompilacja)
    for plik in (program, mostek):
        if not os.path.isfile(plik):
            print(f"brak {plik}")
            return 1
    return (not proba_mostka(mostek)) + (not proba_okna(program))


if __name__ == "__main__":
    raise SystemExit(main())
