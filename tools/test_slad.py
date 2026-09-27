"""Slad GPX bez interfejsu: wczytanie, interpolacja, dziury, przesuniecie czasu.

Uzycie:  python tools/test_slad.py [--pelny]
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from wspolne import wypisz  # noqa: E402

from punctum.core.slad import Punkt, Slad, dopasuj, strefa_systemu, wczytaj_gpx  # noqa: E402
from punctum.core.slad import wspolrzedne_z_tekstu  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def blisko(a, b, eps=1e-7) -> bool:
    return a is not None and b is not None and abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps


# Slad wymyslony: trzy punkty co minute, potem godzina przerwy i jeszcze jeden.
# Do tego punkt bez czasu i punkt z zepsuta szerokoscia - maja zostac pominiete.
GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
 <trk><trkseg>
  <trkpt lat="50.0" lon="20.0"><time>2026-07-01T10:00:00Z</time></trkpt>
  <trkpt lat="50.1" lon="20.2"><time>2026-07-01T10:01:00Z</time></trkpt>
  <trkpt lat="50.2" lon="20.4"><time>2026-07-01T10:02:00.500Z</time></trkpt>
  <trkpt lat="50.3" lon="20.6"></trkpt>
  <trkpt lat="zle" lon="20.6"><time>2026-07-01T10:03:00Z</time></trkpt>
  <trkpt lat="51.0" lon="21.0"><time>2026-07-01T11:02:00+00:00</time></trkpt>
 </trkseg></trk>
</gpx>
"""

with tempfile.TemporaryDirectory() as tmp:
    plik = os.path.join(tmp, "slad.gpx")
    with open(plik, "w", encoding="utf-8") as handle:
        handle.write(GPX)
    slad = wczytaj_gpx(plik)

check("wczytane tylko punkty z czasem i poprawnymi wspolrzednymi", len(slad) == 4, str(len(slad)))
utc = timezone.utc
t0 = datetime(2026, 7, 1, 10, 0, tzinfo=utc)
dziesiec = timedelta(minutes=10)
check("poczatek i koniec sladu", slad.poczatek == t0
      and slad.koniec == datetime(2026, 7, 1, 11, 2, tzinfo=utc))
check("punkt dokladnie w chwili pomiaru", blisko(slad.polozenie(t0, dziesiec), (50.0, 20.0)))
check("polowa drogi miedzy punktami",
      blisko(slad.polozenie(t0 + timedelta(seconds=30), dziesiec), (50.05, 20.1)),
      str(slad.polozenie(t0 + timedelta(seconds=30), dziesiec)))
check("w dziurze dluzszej niz tolerancja nie ma polozenia",
      slad.polozenie(t0 + timedelta(minutes=30), dziesiec) is None)
check("tuz po dziurze bierzemy najblizszy punkt",
      blisko(slad.polozenie(t0 + timedelta(minutes=58), dziesiec), (51.0, 21.0)))
check("tuz przed dziura bierzemy ostatni punkt",
      blisko(slad.polozenie(t0 + timedelta(minutes=5), dziesiec), (50.2, 20.4)))
check("przed sladem w tolerancji - pierwszy punkt",
      blisko(slad.polozenie(t0 - timedelta(minutes=3), dziesiec), (50.0, 20.0)))
check("daleko przed sladem - nic", slad.polozenie(t0 - timedelta(hours=2), dziesiec) is None)

# Aparat w czasie letnim w Polsce (UTC+2), zegar spieszy sie o 30 s.
czasy = {
    "a.jpg": datetime(2026, 7, 1, 12, 0, 30),   # = 10:00:00 UTC
    "b.jpg": datetime(2026, 7, 1, 12, 1, 0),    # = 10:00:30 UTC
    "c.jpg": datetime(2026, 7, 1, 15, 0, 0),    # poza sladem
    "d.jpg": None,                               # bez daty
}
wynik = dopasuj(slad, czasy, timedelta(hours=2, seconds=30), dziesiec)
check("dopasowane tylko zdjecia z czasem w sladzie", set(wynik) == {"a.jpg", "b.jpg"}, str(wynik))
check("przesuniecie strefy i zegara liczy sie poprawnie",
      blisko(wynik.get("a.jpg"), (50.0, 20.0)) and blisko(wynik.get("b.jpg"), (50.05, 20.1)))
check("bez przesuniecia te same zdjecia sa poza sladem",
      not dopasuj(slad, czasy, timedelta(0), dziesiec))

strefa = strefa_systemu(datetime(2026, 7, 1, 12, 0))
check("strefa systemu to rozsadne przesuniecie",
      isinstance(strefa, timedelta) and abs(strefa) <= timedelta(hours=14), str(strefa))

duzy = Slad([Punkt(t0 + timedelta(seconds=i), 50 + i * 1e-5, 20.0) for i in range(10001)])
linia = duzy.do_mapy()
check("linia na mape jest przerzedzona", len(linia) <= 2002, str(len(linia)))
check("linia konczy sie ostatnim punktem", linia[-1] == [round(50 + 10000 * 1e-5, 6), 20.0])
check("pusty slad nic nie zwraca", Slad([]).polozenie(t0, dziesiec) is None
      and Slad([]).do_mapy() == [])

for tekst, oczekiwane in (
    ("50.068636, 22.229014", (50.068636, 22.229014)),
    ("  -33.8568 151.2153 ", (-33.8568, 151.2153)),
    ("50,0686 22,2290", (50.0686, 22.229)),
    ("50,0686; 22,2290", (50.0686, 22.229)),
):
    check(f"wspolrzedne z tekstu: {tekst.strip()}", blisko(wspolrzedne_z_tekstu(tekst), oczekiwane),
          str(wspolrzedne_z_tekstu(tekst)))
for tekst in ("", "Krakow", "95.0, 20.0", "50.1, 200", "50,06,22,22", "1 2 3"):
    check(f"to nie sa wspolrzedne: {tekst!r}", wspolrzedne_z_tekstu(tekst) is None,
          str(wspolrzedne_z_tekstu(tekst)))

sys.exit(wypisz(results))
