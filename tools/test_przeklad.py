"""Przeklad interfejsu bez okien: napisy w kodzie, pliki jezykow, liczby, liczba mnoga.

Pilnuje punktu 27. Kod musi puszczac kazdy napis widoczny dla uzytkownika
przez `t()`/`N_()`/`mnoga()` - test przeglada zrodla i wylapuje polskie
napisy poza nimi, f-stringi z polskim tekstem (pola maja isc przez
`{nazwa}`, bo w innym jezyku stoja gdzie indziej) oraz napisy w wywolaniach
Qt, ktore pokazuja tekst. Dla kazdego jezyka z pliku sprawdza, ze przelozone
jest wszystko, nic nie wisi bez uzycia, a pola `{...}` sie zgadzaja.

Uzycie:  python tools/test_przeklad.py [--pelny] [--lista]
         --lista  wypisuje wszystkie napisy z kodu i braki (do pracy nad przekladem)
"""

from __future__ import annotations

import ast
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wspolne import wypisz  # noqa: E402

from punctum import przeklad as p  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKIET = os.path.join(ROOT, "punctum")
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


PL = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
POLE = re.compile(r"\{(\w+)[^}]*\}")
ZNACZNIKI = {"t": 0, "N_": 0, "mnoga": 1}  # funkcja -> pozycja napisu
# Wywolania, ktore pokazuja tekst na ekranie: goly napis w nich to brak przekladu.
EKRANOWE = {"setText", "QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QGroupBox",
            "addRow", "addTab", "setWindowTitle", "setPlaceholderText", "setSpecialValueText",
            "addMenu", "addAction", "QAction", "_section", "showMessage", "information",
            "warning", "critical", "question", "addItem", "setTitle", "drawText",
            "getExistingDirectory", "QMenu", "addButton", "_hint", "QToolButton", "setSuffix"}
# Wywolania, w ktorych f-string jest kodem, nie zdaniem (JavaScript, sciezki, zapis plikow).
TECHNICZNE = {"_js", "runJavaScript", "setStyleSheet", "join", "open", "print", "debug",
              "info", "exception", "error", "setUniformValue", "uniformLocation"}
# F-stringi, ktore sa kluczem albo nazwa wlasna, a nie zdaniem.
KOD_W_FSTRINGU = re.compile(r"^([a-z_.]+[._]|Punctum|Python)$")
BEZ_INTERFEJSU = {"core/sidecar.py"}  # zapis XMP - nic z tego nie trafia na ekran
# Napisy, ktore celowo zostaja jak sa: nazwy wlasne, formaty, jednostki.
STALE = re.compile(r"^(\s*(px|ms|K|%|×|°|mm)\s*|(Ctrl|Shift|Alt)\+.*|Punctum|OpenCV|Pillow|"
                   r"PySide6 ?|OpenGL ?|Python|JPEG|RAW|TIFF|PNG|GPS|EXIF|XMP|numpy|rawpy|\W*)$")
# Pliki bez napisow interfejsu albo z wlasnym mechanizmem (podpowiedzi maja katalog JSON).
POMIJANE = {"przeklad.py", os.path.join("app", "podpowiedzi.py")}
# Stale, ktorych tresc przechodzi przez przeklad inna droga (map_page.strona()).
STALE_MODULU = {("app/map_page.py", "MAP_HTML"), ("app/style.py", "STYLESHEET_TEMPLATE")}


def nazwa(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def przejrzyj(rel: str, zrodlo: str, klucze: dict, bledy: list) -> None:
    drzewo = ast.parse(zrodlo)
    rodzic: dict = {}
    for n in ast.walk(drzewo):
        for c in ast.iter_child_nodes(n):
            rodzic[c] = n
    opisy = {n.body[0].value for n in ast.walk(drzewo)
             if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
             and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    oznaczone = set()
    for n in ast.walk(drzewo):
        if isinstance(n, ast.Call) and nazwa(n) in ZNACZNIKI:
            poz = ZNACZNIKI[nazwa(n)]
            if len(n.args) <= poz:
                continue
            arg = n.args[poz]
            for c in ast.walk(arg):
                oznaczone.add(c)
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                klucze.setdefault(arg.value, (nazwa(n), f"{rel}:{n.lineno}"))
            elif isinstance(arg, ast.JoinedStr) or (isinstance(arg, ast.BinOp) and nazwa(n) != "t"):
                bledy.append(f"{rel}:{n.lineno} {nazwa(n)}() z f-stringiem albo sklejka")
    pominiete = set()
    for n in ast.walk(drzewo):
        if isinstance(n, ast.Assign) and any(
                isinstance(c, ast.Name) and (rel, c.id) in STALE_MODULU for c in n.targets):
            pominiete |= set(ast.walk(n.value))
    for n in ast.walk(drzewo):
        if n in oznaczone or n in opisy or n in pominiete:
            continue
        if isinstance(n, ast.JoinedStr):
            tekst = "".join(c.value for c in n.values if isinstance(c, ast.Constant))
            wyzej = rodzic.get(n)
            techniczne = (isinstance(wyzej, ast.Call) and nazwa(wyzej) in TECHNICZNE
                          or rel in BEZ_INTERFEJSU
                          or KOD_W_FSTRINGU.match(re.sub(r"[\s•—·:]+", " ", tekst).strip()))
            # slowo bez ogonkow ("poprawionych") tez zdradza polskie zdanie
            if not techniczne and (PL.search(tekst) or re.search(r"[a-z]{4,}", tekst)):
                bledy.append(f"{rel}:{n.lineno} f-string z tekstem: {tekst[:50]!r}")
            continue
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
            continue
        r = rodzic.get(n)
        if isinstance(r, (ast.JoinedStr, ast.FormattedValue)):
            continue
        s = n.value
        if isinstance(r, ast.Dict) and n in r.keys:
            continue
        if PL.search(s):
            bledy.append(f"{rel}:{n.lineno} napis bez przekladu: {s[:50]!r}")
            continue
        # napis bez ogonkow tez bywa polski ("Mapa") - lapiemy go po miejscu uzycia
        wyzej = r
        while isinstance(wyzej, (ast.IfExp, ast.BoolOp, ast.BinOp, ast.Tuple, ast.keyword)):
            wyzej = rodzic.get(wyzej)
        if (isinstance(wyzej, ast.Call) and nazwa(wyzej) in EKRANOWE
                and re.search(r"[A-Za-z]{2}", s) and not STALE.match(s)
                and not (nazwa(wyzej) == "_section" and False)):
            bledy.append(f"{rel}:{n.lineno} napis w {nazwa(wyzej)}() bez przekladu: {s[:50]!r}")


# --- napisy w kodzie ------------------------------------------------------------
klucze: dict[str, tuple[str, str]] = {}
bledy: list[str] = []
for sciezka in sorted(glob.glob(os.path.join(PAKIET, "**", "*.py"), recursive=True)):
    rel = os.path.relpath(sciezka, PAKIET)
    if rel in POMIJANE:
        continue
    with open(sciezka, encoding="utf-8") as handle:
        przejrzyj(rel.replace(os.sep, "/"), handle.read(), klucze, bledy)
if "--lista" in sys.argv:
    # pelna lista do pracy nad przekladem: napisy bez przekladu i klucze z miejscem uzycia
    print("\n".join(bledy))
    print("\n".join(f"KLUCZ\t{m}\t{k!r}" for k, (_, m) in klucze.items()))
    sys.exit(0)
check("kod: napisy przechodza przez przeklad", not bledy,
      f"{len(bledy)}: " + " | ".join(bledy[:12]))
check("kod: znalezione napisy do przekladu", len(klucze) > 250, f"{len(klucze)} napisow")
zle_mnogie = [k for k, (f, _) in klucze.items() if f == "mnoga" and k.count("|") != 2]
check("mnoga(): trzy polskie formy", not zle_mnogie, " | ".join(zle_mnogie[:5]))


def pola(tekst: str) -> set[str]:
    return set(POLE.findall(tekst))


# --- pliki jezykow ----------------------------------------------------------------
jezyki = p.jezyki()
check("jezyki z plikow: polski pierwszy, jest angielski",
      jezyki[0] == "pl" and "en" in jezyki, ", ".join(jezyki))
for kod in jezyki[1:]:
    with open(p.plik(kod), encoding="utf-8") as handle:
        dane = json.load(handle)
    check(f"{kod}: nazwa jezyka i separator", bool(dane.get("_nazwa")) and dane.get("_separator") in (".", ","),
          f"{dane.get('_nazwa')!r} {dane.get('_separator')!r}")
    wpisy = {k: v for k, v in dane.items() if not k.startswith("_")}
    brak = [k for k in klucze if not wpisy.get(k)]
    check(f"{kod}: przelozone wszystkie napisy", not brak, f"{len(brak)}: " + " | ".join(brak[:10]))
    wiszace = [k for k in wpisy if k not in klucze]
    check(f"{kod}: brak nieuzywanych wpisow", not wiszace, f"{len(wiszace)}: " + " | ".join(wiszace[:10]))
    rozne = [k for k, v in wpisy.items() if k in klucze and pola(k) != pola(v)]
    check(f"{kod}: pola {{...}} jak w polskim", not rozne, " | ".join(rozne[:6]))
    formy = 2 if kod == "en" else None
    zle = [k for k, v in wpisy.items() if klucze.get(k, ("",))[0] == "mnoga"
           and formy and v.count("|") != formy - 1]
    check(f"{kod}: liczba mnoga ma wlasna liczbe form", not zle, " | ".join(zle[:5]))
    klawisze = [k for k, v in wpisy.items() if k.count("&") != v.count("&")]
    check(f"{kod}: skroty menu (&) zachowane", not klawisze, " | ".join(klawisze[:6]))

# podpowiedzi: ten sam komplet kluczy i pol co w polskim
from punctum.app import podpowiedzi as pp  # noqa: E402

baza = pp.katalog(pp.BAZOWY)
for kod in pp.jezyki()[1:]:
    obce = pp.katalog(kod)
    brak = [k for k, v in baza.items() if any(pole not in obce.get(k, {}) for pole in v)]
    check(f"podpowiedzi {kod}: komplet wpisow i pol", not brak, f"{len(brak)}: " + ", ".join(brak[:8]))
    wiszace = [k for k in obce if k not in baza]
    check(f"podpowiedzi {kod}: brak nieuzywanych", not wiszace, ", ".join(wiszace[:8]))

# --- zachowanie w biegu ---------------------------------------------------------------
p.ustaw_jezyk("pl")
check("pl: napis bez zmian", p.t("Zapisz") == "Zapisz")
check("pl: przecinek dziesietny", p.liczba(2.5, 2) == "2,50" and p.liczba(3, 0, znak=True) == "+3")
formy = [p.mnoga(n, "{n} zdjęcie|{n} zdjęcia|{n} zdjęć") for n in (1, 2, 5, 12, 22, 0)]
check("pl: trzy formy liczby mnogiej",
      formy == ["1 zdjęcie", "2 zdjęcia", "5 zdjęć", "12 zdjęć", "22 zdjęcia", "0 zdjęć"], str(formy))
p.ustaw_jezyk("en")
check("en: napis przelozony", p.t("Zapisz") == "Save", p.t("Zapisz"))
check("en: kropka dziesietna", p.liczba(2.5, 2) == "2.50", p.liczba(2.5, 2))
check("en: pole wstawione", "photo.jpg" in p.t("Wczytywanie {plik}…", plik="photo.jpg"))
formy = [p.mnoga(n, "{n} zdjęcie|{n} zdjęcia|{n} zdjęć") for n in (1, 2, 5)]
check("en: dwie formy", formy == ["1 photo", "2 photos", "5 photos"], str(formy))
check("en: brakujacy wpis zostaje po polsku", p.t("napis, ktorego nikt nie przelozyl") ==
      "napis, ktorego nikt nie przelozyl")
from punctum.app.map_page import strona  # noqa: E402

check("en: mapa bez polskich napisow",
      not PL.search(strona()) and not re.search(r">(Mapa|Ciemna|Satelita|Hybryda|Szukaj)<", strona()),
      str(PL.findall(strona())[:5]))
check("nieznany jezyk konczy sie polskim", p.ustaw_jezyk("xx") == "pl" and p.t("Zapisz") == "Zapisz")
check("nazwa jezyka w nim samym", p.nazwa_jezyka("en") == "English" and p.nazwa_jezyka("pl") == "Polski")
check("start: zapisany jezyk wygrywa", p.dobierz_jezyk("pl", "en_US") == "pl")
check("start: pusty = jezyk systemu", p.dobierz_jezyk("", "pl_PL") == "pl")
check("start: nieznany system = angielski", p.dobierz_jezyk("", "de_DE") == "en")

from punctum.core.settings import Settings  # noqa: E402

check("ustawienia: nieznany jezyk wraca do wyboru przy starcie",
      Settings(language="xx").normalised().language == "" and
      Settings(language="en").normalised().language == "en")
p.ustaw_jezyk("pl")

sys.exit(wypisz(results))
