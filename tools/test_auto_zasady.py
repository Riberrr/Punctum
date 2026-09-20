"""Sprawdzenie automatu na obrazach o ZNANYCH wlasciwosciach.

Zdjecia z aparatu nie nadaja sie do sprawdzenia zasad, bo nie wiadomo, jaki
wynik jest poprawny - mozna tylko porownac z cudzym gustem. Dlatego wiekszosc
tego testu to sceny zbudowane od zera, o ktorych z gory wiadomo, co automat
powinien z nimi zrobic.

Najwazniejszy jest ostatni test: scena nocna i zdjecie niedoswietlone maja
niemal identyczna mediane jasnosci, a wymagaja calkiem innego potraktowania.
Automat, ktory traktuje je tak samo, zamienia noc w poludnie.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wspolne  # noqa: E402  - przestawia wydruk na UTF-8 (konsola w cp1250)

# Ten test wypisuje po drodze duze tabele diagnostyczne (sceny, pomiary).
# Sa cenne, gdy sie w nim grzebie, i zbedne przy zwyklym przebiegu serii,
# wiec domyslnie milkna - `--pelny` je przywraca razem z tabela wynikow.
if not wspolne.PELNY:
    def print(*args, **kwargs):  # noqa: A001 - swiadome przeslonienie
        pass

from punctum.core.auto import (  # noqa: E402
    analyse_image,
    auto_tone_from,
    linear_to_lstar,
    lstar_to_linear,
)

rng = np.random.default_rng(11)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def grey(value: float, size: int = 300) -> np.ndarray:
    """Jednolita plama o zadanej luminancji liniowej."""
    return np.full((size, size, 3), value, dtype=np.float32)


def lognormal_scene(median: float, spread_ev: float, size: int = 300) -> np.ndarray:
    """Zwyczajna scena: jasnosci rozlozone logarytmicznie wokol mediany."""
    values = median * 2.0 ** rng.normal(0.0, spread_ev, (size, size))
    values = np.clip(values, 1e-5, 1.0).astype(np.float32)
    return np.repeat(values[:, :, None], 3, axis=2)


def step_wedge(low: float, high: float, steps: int = 11, size: int = 330) -> np.ndarray:
    """Klin stopniowy - wzorzec kalibracyjny o znanej rozpietosci."""
    levels = np.geomspace(low, high, steps).astype(np.float32)
    band = size // steps
    image = np.zeros((size, size, 3), dtype=np.float32)
    for index, level in enumerate(levels):
        image[:, index * band : (index + 1) * band] = level
    return image


def night_scene(size: int = 300) -> np.ndarray:
    """Noc: wielka ciemna masa, troche sredniego swiatla, punktowe latarnie."""
    image = np.clip(0.008 * 2.0 ** rng.normal(0, 0.8, (size, size)), 1e-5, 1.0)
    glow = rng.random((size, size)) < 0.14
    image[glow] = np.clip(0.06 * 2.0 ** rng.normal(0, 0.6, glow.sum()), 0, 1)
    lamps = rng.random((size, size)) < 0.004
    image[lamps] = 0.95
    return np.repeat(image.astype(np.float32)[:, :, None], 3, axis=2)


def snow_scene(size: int = 300) -> np.ndarray:
    """Snieg: wiekszosc kadru jasna, niewielkie ciemne akcenty."""
    image = np.clip(0.62 * 2.0 ** rng.normal(0, 0.35, (size, size)), 1e-5, 1.0)
    dark = rng.random((size, size)) < 0.14
    image[dark] = np.clip(0.07 * 2.0 ** rng.normal(0, 0.5, dark.sum()), 0, 1)
    return np.repeat(image.astype(np.float32)[:, :, None], 3, axis=2)


def report(name: str, image: np.ndarray) -> tuple:
    """Analizuje scene i pokazuje, gdzie automat ja przesuwa."""
    scene = analyse_image(image)
    values = auto_tone_from(scene)
    gain = 2.0 ** values["exposure"]
    median_after = float(linear_to_lstar(scene.p50 * gain))
    upper_after = float(linear_to_lstar(scene.p90 * gain))
    print(
        f"{name:<26}{scene.key:<11}{scene.dark_share:>6.2f}{scene.range_ev:>7.1f}"
        f"{values['exposure']:>8.2f}{median_after:>8.1f}{upper_after:>8.1f}"
        f"{values['highlights']:>7.0f}{values['shadows']:>8.0f}{values['contrast']:>6.0f}"
    )
    return scene, values, median_after, upper_after


print("=" * 96)
print("SCENY O ZNANYCH WŁAŚCIWOŚCIACH")
print("=" * 96)
print(f"{'scena':<26}{'klucz':<11}{'ciemne':>6}{'zakres':>7}"
      f"{'EV':>8}{'L* med':>8}{'L* p90':>8}{'świat.':>7}{'cienie':>8}{'kontr':>6}")
print("-" * 96)

# --- 1. karta szarosci ----------------------------------------------------
scene, values, median, upper = report("karta szarości 18 %", grey(0.18))
check("karta szarości: automat jej nie rusza", abs(values["exposure"]) < 0.15,
      f"EV{values['exposure']:+.2f}")
check("karta szarości: brak fałszywego klucza", scene.key == "neutralny",
      f"zakres {scene.range_ev:.2f} EV, pewność {scene.key_confidence:.2f}")

scene, values, median, upper = report("karta 2 EV za ciemno", grey(0.18 / 4))
check("za ciemna karta wraca na miejsce", abs(values["exposure"] - 2.0) < 0.25,
      f"EV{values['exposure']:+.2f}")

scene, values, median, upper = report("karta 2 EV za jasno", grey(0.18 * 4))
check("za jasna karta wraca na miejsce", abs(values["exposure"] + 2.0) < 0.35,
      f"EV{values['exposure']:+.2f}")

# --- 2. klin stopniowy ----------------------------------------------------
scene, values, median, upper = report("klin stopniowy 8 EV", step_wedge(0.004, 1.0))
check("klin: rozpiętość zmierzona poprawnie", abs(scene.range_ev - 8.0) < 1.2,
      f"{scene.range_ev:.2f} EV wobec 8 oczekiwanych")
check("klin: szeroki zakres uruchamia kompresję", values["highlights"] < -30,
      f"światła {values['highlights']:.0f}")

scene, values, median, upper = report("klin wąski 2 EV", step_wedge(0.09, 0.36))
check("wąski zakres nie wyzwala kompresji", values["highlights"] > -5,
      f"światła {values['highlights']:.0f}")
check("wąski zakres dostaje kontrast", values["contrast"] > 3,
      f"kontrast {values['contrast']:.0f}")

# --- 3. sceny skrajnych kluczy --------------------------------------------
night, night_values, night_median, night_upper = report("noc", night_scene())
check("noc rozpoznana jako niski klucz", night.key == "niski",
      f"ciemne {night.dark_share:.2f}")
check("noc pozostaje nocą", night_median < 35.0,
      f"mediana ląduje na L* {night_median:.0f}")
check("noc nie zamienia latarni w dzień", night_upper < 75.0,
      f"90. percentyl ląduje na L* {night_upper:.0f}")

snow, snow_values, snow_median, snow_upper = report("śnieg", snow_scene())
check("śnieg rozpoznany jako wysoki klucz", snow.key == "wysoki",
      f"ciemne {snow.dark_share:.2f}")
check("śnieg pozostaje biały", snow_median > 60.0,
      f"mediana ląduje na L* {snow_median:.0f}")

# --- 4. zwyczajna scena, trzy naświetlenia --------------------------------
normal, normal_values, normal_median, normal_upper = report(
    "scena zwykła", lognormal_scene(0.18, 1.0))
check("poprawnie naświetlona scena zostaje", abs(normal_values["exposure"]) < 0.5,
      f"EV{normal_values['exposure']:+.2f}")

under, under_values, under_median, under_upper = report(
    "scena 2 EV niedoświetlona", lognormal_scene(0.18 / 4, 1.0))
check("niedoświetlona scena zostaje podniesiona", under_values["exposure"] > 1.4,
      f"EV{under_values['exposure']:+.2f}")
check("obie wersje tej samej sceny lądują tak samo",
      abs(under_median - normal_median) < 4.0,
      f"L* {normal_median:.0f} wobec {under_median:.0f}")

# --- 5. TEST KLUCZOWY -----------------------------------------------------
print()
print("=" * 88)
print("NOC A ZDJĘCIE NIEDOŚWIETLONE — podobna mediana, inne potraktowanie")
print("=" * 88)

dark_normal = lognormal_scene(0.010, 0.9)
dark_scene = analyse_image(dark_normal)
dark_values = auto_tone_from(dark_scene)

print(f"{'':<26}{'mediana L*':>12}{'ciemne':>9}{'zakres EV':>11}{'korekta EV':>12}")
print("-" * 70)
print(f"{'noc (latarnie w kadrze)':<26}{night.median_lstar:>12.1f}"
      f"{night.dark_share:>9.2f}{night.range_ev:>11.1f}{night_values['exposure']:>12.2f}")
print(f"{'zwykła scena, 4 EV za mało':<26}{dark_scene.median_lstar:>12.1f}"
      f"{dark_scene.dark_share:>9.2f}{dark_scene.range_ev:>11.1f}"
      f"{dark_values['exposure']:>12.2f}")

check("obie sceny mają podobnie ciemną medianę",
      abs(night.median_lstar - dark_scene.median_lstar) < 12.0,
      f"L* {night.median_lstar:.1f} wobec {dark_scene.median_lstar:.1f}")
check("niedoświetlona dostaje wyraźnie mocniejszą korektę",
      dark_values["exposure"] - night_values["exposure"] > 0.8,
      f"{dark_values['exposure']:+.2f} wobec {night_values['exposure']:+.2f} EV")

# --- 6. odporność na refleksy --------------------------------------------
print()
base = lognormal_scene(0.18, 0.9)
without = analyse_image(base)
with_lamp = base.copy()
mask = rng.random(with_lamp.shape[:2]) < 0.002
with_lamp[mask] = 1.0
withl = analyse_image(with_lamp)
values_without = auto_tone_from(without)
values_with = auto_tone_from(withl)
print(f"scena bez refleksów : biel rozproszona {without.diffuse_white:.3f}, "
      f"EV{values_without['exposure']:+.2f}")
print(f"ta sama z latarnią  : biel rozproszona {withl.diffuse_white:.3f}, "
      f"EV{values_with['exposure']:+.2f}")
check("refleks nie zaciemnia całego zdjęcia",
      abs(values_with["exposure"] - values_without["exposure"]) < 0.35,
      f"różnica {values_with['exposure'] - values_without['exposure']:+.2f} EV")

# --- 7. przestrzeń L* -----------------------------------------------------
check("L* 50 odpowiada szarości 18 %", abs(lstar_to_linear(50.0) - 0.184) < 0.005,
      f"{lstar_to_linear(50.0):.4f}")
check("konwersja L* jest odwracalna",
      abs(float(linear_to_lstar(lstar_to_linear(72.0))) - 72.0) < 0.01)

from wspolne import wypisz  # noqa: E402  (test jest skryptem, nie modulem)

sys.exit(wypisz(results, szerokosc=50))
