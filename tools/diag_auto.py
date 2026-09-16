"""Podglad wszystkich liczb, na ktorych opiera sie automat."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import load_photo
from punctum.core.auto import analyse, auto_tone_from, linear_to_lstar, lstar_to_linear

for path in sys.argv[1:]:
    raw = load_photo(path)
    s = analyse(raw)
    v = auto_tone_from(s)
    gain = 2.0 ** v["exposure"]
    print(f"\n{os.path.basename(path)}")
    for name, value in (("p02", s.p02), ("p10", s.p10), ("p50", s.p50),
                        ("p90", s.p90), ("biel rozproszona", s.diffuse_white),
                        ("szczyt", s.peak_white)):
        print(f"  {name:<20}{value:>10.5f}   L* {float(linear_to_lstar(value)):>6.1f}"
              f"   po korekcie L* {float(linear_to_lstar(value * gain)):>6.1f}")
    print(f"  {'zakres':<20}{s.range_ev:>10.2f} EV")
    print(f"  {'ciemne':<20}{s.dark_share:>10.2f}   klucz {s.key}"
          f"   pewnosc {s.key_confidence:.2f}")
    print(f"  {'refleksy':<20}{s.specular_share:>10.4f}")
    print(f"  {'nasycenie':<20}{s.saturation:>10.3f}")
    print(f"  {'cel mediany':<20}{s.target_median_lstar:>10.1f} L*"
          f"  = {lstar_to_linear(s.target_median_lstar):.4f}")
    tonal = float(__import__("numpy").log2(
        lstar_to_linear(s.target_median_lstar) / max(s.p50, 1e-7)))
    ceiling = float(__import__("numpy").log2(
        lstar_to_linear(96.0) / max(s.diffuse_white, 1e-7)))
    print(f"  warunek tresci {tonal:+.2f} EV, warunek swiatel {ceiling:+.2f} EV")
    print(f"  wynik: {v}")
