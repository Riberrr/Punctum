"""Podpowiedzi bez interfejsu: katalog tekstow, klucze w kodzie, jezyki, wylacznik.

Pilnuje trzech rzeczy z punktu 26: kazdy klucz uzyty w kodzie ma polski
tekst, w katalogu nie wisza teksty, ktorych nikt nie uzywa, a jezyk
z niepelnym przekladem uzupelnia braki polskim. Przy okazji: pole
"Odszumianie podgladu" naprawde trafia do watkow podgladu.

Uzycie:  python tools/test_podpowiedzi.py [--pelny]
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

from wspolne import wypisz  # noqa: E402

app = QCoreApplication(sys.argv)

from punctum.app import podpowiedzi as pp  # noqa: E402
from punctum.core.exif_edit import FIELDS  # noqa: E402
from punctum.core.settings import ENGINE_LABELS, Settings  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "punctum", "app")
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# --- katalog bazowy --------------------------------------------------------
baza = pp.katalog(pp.BAZOWY)
check("katalog polski wczytany", len(baza) > 90, f"{len(baza)} wpisow")
puste = [k for k, v in baza.items() if not (v.get("tytul") or v.get("opis") or v.get("uwaga"))]
check("kazdy wpis ma tresc", not puste, ", ".join(puste))
bez_tytulu = [k for k, v in baza.items()
              if not v.get("tytul") and k not in (pp.SUWAK, "suwak.temperature_jpeg")]
check("kazdy dymek ma tytul", not bez_tytulu, ", ".join(bez_tytulu))
obce = [k for k, v in baza.items() for pole in v if pole not in ("tytul", "opis", "uwaga", "uwaga_suwaka")]
check("tylko znane pola we wpisach", not obce, ", ".join(obce))

# --- klucze uzyte w kodzie ---------------------------------------------------
# Klucze doslowne: kazdy napis w kodzie interfejsu, ktory wyglada jak klucz
# z jednego z prefiksow katalogu. Klucze skladane w locie (suwaki, pola EXIF,
# silnik podgladu) liczymy z tych samych zrodel, z ktorych sklada je kod.
prefiksy = sorted({k.split(".")[0] for k in baza})
wzor = re.compile(r"[\"']((?:%s)\.[A-Za-z0-9_]+)[\"']" % "|".join(prefiksy))
uzyte: set[str] = set()
for plik in glob.glob(os.path.join(APP, "*.py")):
    with open(plik, encoding="utf-8") as handle:
        uzyte |= set(wzor.findall(handle.read()))
with open(os.path.join(APP, "edit_panel.py"), encoding="utf-8") as handle:
    suwaki = re.findall(r"self\._add\([^,]+,\s*\"(\w+)\"", handle.read())
check("znalezione suwaki", len(suwaki) >= 17, f"{len(suwaki)}")
uzyte |= {f"suwak.{k}" for k in suwaki}
uzyte |= {f"exif.{f.key}" for f in FIELDS}
uzyte |= {f"ustawienia.silnik_{k}" for k in ENGINE_LABELS}

brak = sorted(uzyte - set(baza))
check("kazdy klucz z kodu ma tekst", not brak, ", ".join(brak))
zbedne = sorted(set(baza) - uzyte)
check("brak tekstow, ktorych nikt nie uzywa", not zbedne, ", ".join(zbedne))

# --- skladanie dymka ---------------------------------------------------------
t = pp.tekst("suwak.shadows", suwak=True)
check("tytul pogrubiony", "<b>Cienie</b>" in t)
check("suwak dostaje linie o dwukliku", "Dwuklik przywraca" in t)
check("rada w osobnej linii", "<br>Rada:" in t)
t = pp.tekst("suwak.temperature", suwak=True, dopisek="suwak.temperature_jpeg")
check("temperatura: wlasna linia zamiast wspolnej",
      "ustawienia aparatu" in t and "Dwuklik przywraca" not in t)
check("temperatura JPEG: dopisek o kelwinach", "umowne" in t)
t = pp.tekst("suwak.noise_color", suwak=True)
check("uwaga wpisu obok linii suwaka", "Dwuklik" in t and "odświeża" in t)
baza["test.html"] = {"tytul": "a < b", "opis": "x & y"}
t = pp.tekst("test.html")
del baza["test.html"]
check("znaki HTML ucieczkowane", "a &lt; b" in t and "x &amp; y" in t)
t = pp.tekst("podglad.dopasuj")
check("krotki dymek bez stalej szerokosci", "<table" not in t)
check("dlugi dymek lamany na stala szerokosc", "<table" in pp.tekst("suwak.shadows"))

# --- jezyki: nowy plik bez zmian w kodzie, braki z polskiego ---------------
katalog_org, lang_org = pp.LANG_DIRECTORY, dict(pp._katalogi)
tmp = tempfile.mkdtemp(prefix="punctum-jezyki-")
try:
    shutil.copy(pp.plik(pp.BAZOWY), tmp)
    with open(os.path.join(tmp, "podpowiedzi.xx.json"), "w", encoding="utf-8") as handle:
        json.dump({"suwak.shadows": {"tytul": "Shadows"}}, handle)
    pp.LANG_DIRECTORY = tmp
    pp._katalogi.clear()
    check("jezyk wykryty z pliku", pp.jezyki() == ["pl", "xx"], str(pp.jezyki()))
    pp.ustaw_jezyk("xx")
    w = pp.wpis("suwak.shadows")
    check("przelozone pole z pliku jezyka", w.get("tytul") == "Shadows")
    check("brakujace pole z polskiego", "ciemne partie" in w.get("opis", ""))
    check("brakujacy wpis z polskiego", pp.wpis("podglad.sto")["tytul"] == "Powiększenie 100 %")
    pp.ustaw_jezyk("zz")
    check("nieznany jezyk -> polski", pp.wpis("suwak.shadows")["tytul"] == "Cienie")
finally:
    pp.ustaw_jezyk(pp.BAZOWY)
    pp.LANG_DIRECTORY = katalog_org
    pp._katalogi.clear()
    pp._katalogi.update(lang_org)
    shutil.rmtree(tmp, ignore_errors=True)

# --- wylacznik ---------------------------------------------------------------
wyl = pp.WylacznikPodpowiedzi()
dymek, inne = QEvent(QEvent.ToolTip), QEvent(QEvent.Enter)
check("wlaczone: dymek przechodzi", wyl.eventFilter(None, dymek) is False)
wyl.wlaczone = False
check("wylaczone: dymek zjedzony", wyl.eventFilter(None, dymek) is True)
check("wylaczone: inne zdarzenia przechodza", wyl.eventFilter(None, inne) is False)
s = Settings()
check("podpowiedzi domyslnie wlaczone", s.show_tooltips is True)
s.show_tooltips = False
check("ustawienie przezywa normalizacje", s.normalised().show_tooltips is False)

# --- odszumianie podgladu z ustawien ----------------------------------------
from punctum.app import workers  # noqa: E402

zlapane: list[str] = []
org_detail, org_region = workers.apply_detail, workers.develop_region
try:
    workers.apply_detail = lambda img, p, q, scale=1.0: zlapane.append(q) or img
    workers.develop_region = lambda raw, p, r, scale=1.0, quality="": zlapane.append(quality) or None
    workers.NoiseReductionTask(1, None, None, 1.0, quality="fast").run()
    from PySide6.QtCore import QRect  # noqa: E402
    task = workers.DetailRenderTask(1, None, None, QRect(0, 0, 1, 1), 1.0, quality="high")
    try:
        task.run()
    except Exception:  # noqa: BLE001 - emisja None bywa odrzucona, liczy sie argument
        pass
finally:
    workers.apply_detail, workers.develop_region = org_detail, org_region
check("odszumianie podgladu: jakosc z ustawien", zlapane[:1] == ["fast"], str(zlapane))
check("ostry fragment: jakosc z ustawien", zlapane[1:2] == ["high"], str(zlapane))
with open(os.path.join(APP, "main_window.py"), encoding="utf-8") as handle:
    zrodlo = handle.read()
check("okno podaje jakosc z ustawien obu watkom",
      zrodlo.count("quality=self.settings.preview_noise_quality") == 2)

sys.exit(wypisz(results))
