"""Plik startowy dla kompilacji (punkt 18): daje Punctum.exe (tools/kompiluj.py).

Osobny plik, bo `punctum/__main__.py` ma importy wzgledne - skompilowany
jako skrypt glowny stracilby pakiet, w ktorym lezy.
"""

from punctum.__main__ import main

raise SystemExit(main())
