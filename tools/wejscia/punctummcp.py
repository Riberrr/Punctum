"""Plik startowy mostka MCP dla kompilacji (punkt 18): daje PunctumMCP.exe (tools/kompiluj.py).

Mostek wchodzi do tej samej kompilacji co program (drugie --main), ale
importuje tylko punctum.mcp.most - bez Qt i bibliotek obrazu, wiec startuje
w ulamku sekundy.
"""

from punctum.mcp.most import main

raise SystemExit(main())
