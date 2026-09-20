"""Porzadkuje plik ustawien: wlacza zapis korekt, czysci martwe katalogi.

Powstalo po tym, jak test eksportu zapisal do prawdziwych ustawien swoja
wartosc robocza. Przydaje sie tez po prostu do sprzatniecia historii.

Domyslnie mowi jednym zdaniem, co poprawil (albo ze nie bylo czego);
`--pelny` wypisuje stan przed i po.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wspolne import PELNY  # noqa: E402

from punctum.core.settings import Settings, settings_path  # noqa: E402

settings = Settings.load()
if PELNY:
    print(f"plik: {settings_path()}")
    print(f"  zapis korekt          : {settings.store_edits}")
    print(f"  ostatni katalog       : {settings.last_folder}")
    print(f"  historia ({len(settings.recent_folders)}):")
    for folder in settings.recent_folders:
        print(f"    {'jest ' if os.path.isdir(folder) else 'brak '} {folder}")

zmiany = []
if not settings.store_edits:
    settings.store_edits = True
    zmiany.append("wlaczono zapis korekt")
if settings.format_filter != "all":
    settings.format_filter = "all"
    zmiany.append("filtr formatow z powrotem na wszystkie")

martwe = [f for f in settings.recent_folders if not os.path.isdir(f)]
if martwe:
    settings.recent_folders = [f for f in settings.recent_folders if os.path.isdir(f)]
    zmiany.append(f"usunieto {len(martwe)} martwych katalogow z historii")
if not os.path.isdir(settings.last_folder):
    settings.last_folder = settings.recent_folders[0] if settings.recent_folders else ""
    zmiany.append("ostatni katalog przestawiony na istniejacy")

settings.save()

if PELNY:
    print("\npo poprawce:")
    print(f"  zapis korekt          : {settings.store_edits}")
    print(f"  ostatni katalog       : {settings.last_folder}")
    print(f"  historia              : {len(settings.recent_folders)} katalogow")
elif zmiany:
    print("ustawienia: " + ", ".join(zmiany))
else:
    print("ustawienia: nic do poprawiania")
