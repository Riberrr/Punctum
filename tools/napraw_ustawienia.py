"""Porzadkuje plik ustawien: wlacza zapis korekt, czysci martwe katalogi.

Powstalo po tym, jak test eksportu zapisal do prawdziwych ustawien swoja
wartosc roboczą. Przydaje sie tez po prostu do sprzatniecia historii.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core.settings import Settings, settings_path

settings = Settings.load()
print(f"plik: {settings_path()}")
print(f"  zapis korekt          : {settings.store_edits}")
print(f"  ostatni katalog       : {settings.last_folder}")
print(f"  historia ({len(settings.recent_folders)}):")
for folder in settings.recent_folders:
    print(f"    {'jest ' if os.path.isdir(folder) else 'brak '} {folder}")

settings.store_edits = True
settings.format_filter = "all"
settings.recent_folders = [f for f in settings.recent_folders if os.path.isdir(f)]
if not os.path.isdir(settings.last_folder):
    settings.last_folder = settings.recent_folders[0] if settings.recent_folders else ""
settings.save()

print("\npo poprawce:")
print(f"  zapis korekt          : {settings.store_edits}")
print(f"  ostatni katalog       : {settings.last_folder}")
print(f"  historia              : {len(settings.recent_folders)} katalogow")
