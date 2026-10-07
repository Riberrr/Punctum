"""Plik startowy dla kompilacji (punkt 18): daje Punctum.exe (tools/kompiluj.py).

Osobny plik, bo `punctum/__main__.py` ma importy wzgledne - skompilowany
jako skrypt glowny stracilby pakiet, w ktorym lezy.
"""

import faulthandler

# Awaria w kodzie natywnym (Qt, OpenGL, LibRaw) konczy skompilowany program
# bez sladu; tak przynajmniej na stderr zostaje stos funkcji Pythona.
# Tylko tutaj (plik startowy kompilacji) - ze zrodel nic sie nie zmienia.
# Program bez konsoli (Windows) nie ma stderr - wtedy enable() rzuca wyjatek.
try:
    faulthandler.enable(all_threads=True)
except (RuntimeError, AttributeError, ValueError):
    pass

from punctum.__main__ import main  # noqa: E402

raise SystemExit(main())
