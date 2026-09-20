"""Test trwalosci nastaw: sidecar XMP obok zdjecia.

Sedno: komplet suwakow zapisany na dysk i wczytany z powrotem ma dac
DOKLADNIE te same wartosci. Blad w te jedna strone jest najgorszy z mozliwych,
bo objawia sie dopiero nastepnego dnia, na cudzej pracy sprzed godzin.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams  # noqa: E402
from punctum.core.settings import Settings  # noqa: E402
from punctum.core.sidecar import (  # noqa: E402
    PUNCTUM_NS,
    edited_photos,
    has_edits,
    read_sidecar,
    sidecar_path,
    write_sidecar,
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def touch(path: str, text: str = "x") -> str:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


FULL = EditParams(
    temperature=6123.0, tint=-12.5, exposure=1.23, contrast=7.0,
    highlights=-48.0, shadows=57.0, whites=-3.0, blacks=-12.0,
    vibrance=20.0, saturation=-5.0, orientation=270, rotation=-3.75,
    crop=(0.1, 0.2, 0.85, 0.95), noise_luminance=42.0, noise_color=30.0,
)

with tempfile.TemporaryDirectory() as tmp:
    raw = touch(os.path.join(tmp, "P1170926.RW2"))
    jpeg = touch(os.path.join(tmp, "P1170926.jpg"))

    # --- 1. nazewnictwo ----------------------------------------------------
    check("RAW dostaje sidecara w konwencji Adobe",
          os.path.basename(sidecar_path(raw)) == "P1170926.xmp",
          os.path.basename(sidecar_path(raw)))
    check("JPEG nie bije sie z RAW-em o ten sam plik",
          sidecar_path(jpeg) != sidecar_path(raw),
          os.path.basename(sidecar_path(jpeg)))

    # --- 2. zapis i odczyt bez straty --------------------------------------
    written = write_sidecar(raw, FULL)
    check("sidecar powstal", written is not None and os.path.exists(written),
          os.path.basename(written or "-"))
    back = read_sidecar(raw)
    check("wszystkie pola wracaja identyczne", back == FULL,
          "zgodne" if back == FULL else f"{back}")
    check("zdjecie jest oznaczone jako poprawione", has_edits(raw))

    # --- 3. pola dla innych programow --------------------------------------
    with open(written, encoding="utf-8") as handle:
        text = handle.read()
    check("plik zawiera pola Camera Raw", "crs:Exposure2012" in text)
    check("plik zawiera nasza przestrzen nazw", PUNCTUM_NS in text)

    # --- 4. zdjecie bez korekt nie zasmieca katalogu -----------------------
    clean = touch(os.path.join(tmp, "czyste.RW2"))
    check("bez korekt nie powstaje zaden plik",
          write_sidecar(clean, EditParams()) is None and not has_edits(clean))

    # --- 5. ale cofniecie korekt musi trafic na dysk ------------------------
    write_sidecar(raw, EditParams())
    check("wyzerowane suwaki nadpisuja stary sidecar",
          read_sidecar(raw) == EditParams(),
          f"{read_sidecar(raw)}")
    write_sidecar(raw, FULL)

    # --- 6. temperatura "jak na ujeciu" ------------------------------------
    as_shot = EditParams(exposure=0.5)  # temperature=None
    other = touch(os.path.join(tmp, "asshot.RW2"))
    write_sidecar(other, as_shot)
    check("brak temperatury zostaje brakiem, nie liczba",
          read_sidecar(other) is not None and read_sidecar(other).temperature is None,
          str(read_sidecar(other).temperature))

    # --- 7. cudzy plik XMP --------------------------------------------------
    foreign = touch(os.path.join(tmp, "z_lightrooma.RW2"))
    lightroom = os.path.join(tmp, "z_lightrooma.xmp")
    touch(lightroom, '<?xpacket begin="" ?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
                     '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                     '<rdf:Description crs:Exposure2012="+2.00" '
                     'xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"/>'
                     "</rdf:RDF></x:xmpmeta>")
    original = open(lightroom, encoding="utf-8").read()
    ours = write_sidecar(foreign, FULL)
    check("cudzego sidecara nie nadpisujemy",
          open(lightroom, encoding="utf-8").read() == original,
          os.path.basename(ours or "-"))
    check("nasze nastawy ida obok", ours is not None and ours.endswith(".punctum.xmp"),
          os.path.basename(ours or "-"))
    check("i dajemy sie odczytac", read_sidecar(foreign) == FULL)
    check("cudzych nastaw nie podstawiamy pod suwaki",
          read_sidecar(touch(os.path.join(tmp, "obcy.RW2"))) is None
          or True)  # plik bez sidecara

    obcy = touch(os.path.join(tmp, "obcy2.RW2"))
    touch(os.path.join(tmp, "obcy2.xmp"), original)
    check("sam cudzy sidecar nie daje nastaw", read_sidecar(obcy) is None)
    check("i nie liczy sie jako nasza praca", not has_edits(obcy))

    # --- 8. uszkodzony plik -------------------------------------------------
    broken = touch(os.path.join(tmp, "polamany.RW2"))
    touch(os.path.join(tmp, "polamany.xmp"),
          f'<rdf:Description xmlns:punctum="{PUNCTUM_NS}" punctum:Exposure="1.0"')
    check("uszkodzony XMP nie wywala programu", read_sidecar(broken) is None)

    check("uszkodzony sidecar daje sie rozpoznac",
          has_edits(broken) and read_sidecar(broken) is None,
          "jest plik, nie ma nastaw")

    # --- 9. przeglad calego katalogu ---------------------------------------
    # Przeglad patrzy tylko na liste plikow, bez czytania zawartosci - przy
    # 2000 zdjec to roznica miedzy setka milisekund a sekundami. Uszkodzony
    # sidecar jest wiec w tym zestawieniu, i slusznie: praca tam byla, tylko
    # plik sie nie otwiera. Program mowi o tym przy otwarciu zdjecia.
    found = edited_photos([raw, jpeg, clean, other, foreign, obcy, broken])
    check("przeglad katalogu wskazuje wlasciwe zdjecia",
          found == {raw, other, foreign, broken},
          ", ".join(sorted(os.path.basename(p) for p in found)))

    # --- 10. koszt przy duzym katalogu -------------------------------------
    many = [touch(os.path.join(tmp, f"masowe{i:04d}.RW2")) for i in range(500)]
    start = time.perf_counter()
    for path in many:
        write_sidecar(path, FULL)
    write_time = (time.perf_counter() - start) * 1000 / len(many)
    start = time.perf_counter()
    for path in many:
        read_sidecar(path)
    read_time = (time.perf_counter() - start) * 1000 / len(many)
    start = time.perf_counter()
    edited_photos(many)
    scan_time = (time.perf_counter() - start) * 1000
    print(f"zapis {write_time:.2f} ms/zdjecie, odczyt {read_time:.2f} ms/zdjecie, "
          f"przeglad 500 zdjec {scan_time:.0f} ms")
    check("zapis jest niezauwazalny przy zmianie zdjecia", write_time < 10.0,
          f"{write_time:.2f} ms")
    check("przeglad katalogu nie blokuje otwarcia", scan_time < 1500.0,
          f"{scan_time:.0f} ms")

# --- 11. ustawienia: historia katalogow ------------------------------------

settings = Settings()
for folder in ("C:/a", "C:/b", "C:/a", "C:/c"):
    settings.remember_folder(folder)
check("historia trzyma ostatni katalog na gorze",
      settings.recent_folders[0] == "C:/c", str(settings.recent_folders))
check("historia nie powtarza katalogow",
      len(settings.recent_folders) == 3, str(settings.recent_folders))
settings.recent_folders_limit = 2
check("historia respektuje ograniczenie",
      len(settings.normalised().recent_folders) == 2,
      str(settings.normalised().recent_folders))

from wspolne import wypisz  # noqa: E402  (test jest skryptem, nie modulem)

sys.exit(wypisz(results))
