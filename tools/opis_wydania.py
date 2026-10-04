"""Opis wydania dla GitHub Releases z historii zmian (punkt 18, etap 3).

    python tools/opis_wydania.py X.Y.Z [plik_wyjsciowy]

Bierze sekcje `## X.Y.Z — data` z CHANGELOG.md (angielski - strona wydan
jest dla wszystkich) i dopisuje odsylacz do wersji polskiej. Brak sekcji =
blad: wydanie bez opisu zmian lamie zasade z punktu 36, wiec workflow ma sie
na tym zatrzymac, zanim cokolwiek opublikuje.
"""

from __future__ import annotations

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sekcja(wersja: str, nazwa: str = "CHANGELOG.md") -> str:
    with open(os.path.join(REPO, nazwa), encoding="utf-8") as f:
        tekst = f.read()
    wzor = re.compile(rf"^## {re.escape(wersja)} — \d{{4}}-\d{{2}}-\d{{2}}\s*$(.*?)(?=^## |\Z)",
                      re.M | re.S)
    trafienie = wzor.search(tekst)
    return trafienie.group(1).strip() if trafienie else ""


def opis(wersja: str) -> str:
    tresc = sekcja(wersja)
    if not tresc:
        raise SystemExit(f"CHANGELOG.md nie ma sekcji dla {wersja}")
    # Na stronie wydania odnosnik wzgledny nie dziala - adres repozytorium
    # podaje GitHub Actions (nazwa repo nie jest wpisana na sztywno).
    repo = os.environ.get("GITHUB_REPOSITORY")
    adres = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}"
             f"/blob/v{wersja}/CHANGELOG.pl.md") if repo else "CHANGELOG.pl.md"
    return (f"{tresc}\n\n"
            f"Polish changelog / historia zmian po polsku: [CHANGELOG.pl.md]({adres})\n\n"
            "Checksums: `SHA256SUMS.txt`. Windows may show a SmartScreen warning "
            "because the installer is not code-signed yet.\n")


if __name__ == "__main__":
    tekst = opis(sys.argv[1].lstrip("v"))
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(tekst)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(tekst)
