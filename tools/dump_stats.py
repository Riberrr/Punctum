import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import load_raw
from punctum.core.auto import analyse

for pattern in sys.argv[1:]:
    for path in sorted(glob.glob(pattern)):
        try:
            stats = analyse(load_raw(path))
        except Exception as exc:
            print(f"{os.path.basename(path):<20} pominiety ({type(exc).__name__})")
            continue
        print(
            f"{os.path.basename(path):<20} "
            f"nasycenie={stats['saturation']:.3f}  "
            f"rozpietosc={stats['span_ev']:.2f} EV"
        )
