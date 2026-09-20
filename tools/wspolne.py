"""Wspolne czesci testow: raport, czekanie na warunek, lancuch etapow.

Trzy rzeczy, ktore kazdy test mial dotad u siebie, a ktore musza dzialac
wszedzie tak samo.

**Raport.** Domyslnie wypisujemy tylko to, co NIE przeszlo, plus jedna linia
podsumowania; pelna tabela po fladze `--pelny`. Wydruk kazdego uruchomienia
wraca do rozmowy z Claude i kosztuje - a interesuja nas bledy, nie sto linii
"OK". Kod wyjscia to liczba bledow, wiec seria moze przerwac po pierwszej
przegranej zamiast mielic reszte przez pol minuty.

**Czekanie na warunek.** Nigdy na ustalona liczbe sekund: obciazona maszyna
wywracala kiedys testy przy zupelnie poprawnym kodzie.

**Lancuch etapow.** Kolejny etap rusza, gdy poprzedni wroci. Wczesniej etapy
odpalal sztywny budzik (5 s, 9 s, 11 s, 17 s...), wiec test, ktory mial
roboty na dziewiec sekund, i tak siedzial trzydziesci.
"""

from __future__ import annotations

import sys
import time
import traceback

# Konsola Windows chodzi w cp1250 i potrafi wywrocic test na jego wlasnym
# wydruku (ogonki, strzalki, romby). Raport idzie wiec w UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 - strumien przekierowany do pliku
    pass

PELNY = "--pelny" in sys.argv


def zdjecia() -> list[str]:
    """Sciezki zdjec podane w wierszu polecen, bez flag."""
    return [arg for arg in sys.argv[1:] if not arg.startswith("--")]


def wypisz(wyniki: list[tuple[str, bool, str]], szerokosc: int = 52) -> int:
    """Raport z serii sprawdzen. Zwraca liczbe bledow (0 = wszystko gra)."""
    bledy = [(nazwa, detal) for nazwa, ok, detal in wyniki if not ok]
    if PELNY:
        print(f"\n{'test':<{szerokosc}}{'wynik':>8}   szczegoly", flush=True)
        print("-" * (szerokosc + 48), flush=True)
        for nazwa, ok, detal in wyniki:
            print(f"{nazwa:<{szerokosc}}{'OK' if ok else 'BLAD':>8}   {detal}",
                  flush=True)
    else:
        for nazwa, detal in bledy:
            print(f"BLAD  {nazwa}   {detal}", flush=True)
    print(f"{len(wyniki) - len(bledy)} / {len(wyniki)} testow przeszlo",
          flush=True)
    return len(bledy)


def czekaj(app, warunek, etykieta: str, timeout_ms: int = 25000) -> bool:
    """Czeka na warunek, mielac zdarzenia Qt. False, gdy sie nie doczekal."""
    koniec = time.perf_counter() + timeout_ms / 1000.0
    while time.perf_counter() < koniec:
        app.processEvents()
        if warunek():
            return True
        time.sleep(0.02)
    print(f"[czekanie] nie doczekano: {etykieta}", flush=True)
    return False


def lancuch(app, etapy: list, koniec) -> None:
    """Uruchamia etapy jeden po drugim: nastepny rusza, gdy poprzedni wroci.

    Etap sam czeka na to, czego potrzebuje (patrz `czekaj`), wiec test trwa
    tyle, ile naprawde trwa praca, a nie tyle, ile ustawiono na budziku.
    Wyjatek w etapie konczy test - ale przez `koniec`, zeby raport sie
    wydrukowal, a katalog testowy i ustawienia zostaly posprzatane.
    """
    from PySide6.QtCore import QTimer

    def krok(numer: int = 0) -> None:
        if numer >= len(etapy):
            koniec()
            return
        etap = etapy[numer]
        try:
            etap()
        except Exception:  # noqa: BLE001 - raport wazniejszy niz traceback w gore
            print(f"\nWYJATEK w {getattr(etap, '__name__', etap)}:", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            koniec()
            return
        QTimer.singleShot(0, lambda: krok(numer + 1))

    QTimer.singleShot(0, lambda: krok(0))
