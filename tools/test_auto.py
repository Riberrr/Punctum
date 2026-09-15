"""Porownanie automatycznej korekcji z tym, co proponuje Lightroom."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import auto_tone, develop, load_raw

# wartosci odczytane ze zrzutu ekranu Lightrooma dla tego samego pliku
LIGHTROOM = {
    "01158845": dict(exposure=1.00, contrast=6, highlights=-47,
                     shadows=57, whites=9, blacks=-8, vibrance=15),
}

for path in sys.argv[1:]:
    stem = os.path.splitext(os.path.basename(path))[0]
    raw = load_raw(path)

    t = time.perf_counter()
    result = auto_tone(raw)
    elapsed = (time.perf_counter() - t) * 1000

    print(f"\n{stem}   (balans bieli {raw.as_shot_temp:.0f} K, analiza {elapsed:.0f} ms)")
    reference = LIGHTROOM.get(stem)
    if reference:
        print(f"  {'parametr':<14}{'nasze':>8}{'Lightroom':>12}{'roznica':>10}")
        for key, value in result.items():
            ref = reference.get(key)
            if ref is None:
                print(f"  {key:<14}{value:>8}{'-':>12}{'-':>10}")
            else:
                print(f"  {key:<14}{value:>8}{ref:>12}{value - ref:>+10.2f}")
    else:
        for key, value in result.items():
            print(f"  {key:<14}{value:>8}")
