"""Pomiar czasow: ile trwa dekodowanie, a ile sama obrobka na podgladzie."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punctum.core import EditParams, develop, load_raw, load_thumbnail

path = sys.argv[1]

t = time.perf_counter()
thumb = load_thumbnail(path)
print(f"miniatura z RAW   : {(time.perf_counter() - t) * 1000:6.0f} ms  {thumb.shape if thumb is not None else 'brak'}")

t = time.perf_counter()
raw = load_raw(path)
print(f"pelne dekodowanie : {(time.perf_counter() - t) * 1000:6.0f} ms  {raw.shape[1]}x{raw.shape[0]}")

t = time.perf_counter()
proxy = raw.proxy(2048)
print(f"budowa proxy      : {(time.perf_counter() - t) * 1000:6.0f} ms  {proxy.shape[1]}x{proxy.shape[0]}")

p = EditParams(exposure=0.57, contrast=7, highlights=-76, shadows=28,
               whites=14, blacks=-19, vibrance=15, temperature=6100.0)

for _ in range(3):
    t = time.perf_counter()
    develop(proxy, p, denoise=False)
    print(f"obrobka proxy     : {(time.perf_counter() - t) * 1000:6.0f} ms")

t = time.perf_counter()
develop(raw, p, denoise=False)
print(f"obrobka pelna     : {(time.perf_counter() - t) * 1000:6.0f} ms")
