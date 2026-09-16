"""Ile kosztuje miniatura w katalogu mieszanym - RAW wobec JPEG."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import folder_photos, is_jpeg, load_preview

folder = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20

for label, wanted in (("RAW", False), ("JPEG", True)):
    paths = [p for p in folder_photos(folder) if is_jpeg(p) == wanted][:limit]
    if not paths:
        print(f"{label:<6} brak plikow")
        continue
    start = time.perf_counter()
    sizes = [load_preview(p) for p in paths]
    elapsed = (time.perf_counter() - start) * 1000 / len(paths)
    failed = sum(1 for s in sizes if s is None)
    print(f"{label:<6}{len(paths):>4} plikow{elapsed:>8.0f} ms na miniature"
          f"   bledow: {failed}")
