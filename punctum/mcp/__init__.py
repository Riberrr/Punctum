"""Sterowanie Punctum przez agentow AI - serwer MCP (Model Context Protocol).

Uklad:
- `narzedzia` - opisy narzedzi (nazwa, opis dla modelu, schemat wejscia).
  Bez Qt i bez ciezkich bibliotek: czyta je tez mostek stdio, ktory ma
  odpowiadac na `tools/list` nawet przy zamknietym programie.
- `protokol` - JSON-RPC MCP i serwer HTTP na 127.0.0.1 (Streamable HTTP).
  Tez bez Qt - wykonanie narzedzi dostaje z zewnatrz jako funkcje.
- `most` - mostek stdio <-> HTTP dla klientow, ktore uruchamiaja serwer
  jako proces (Claude Desktop, Cursor, VS Code...): `python -m punctum.mcp`.
- `app/mcp_polecenia.py` - wlasciwe dzialanie narzedzi na otwartym oknie.

Wlasna, mala obsluga protokolu zamiast pakietu `mcp`: dla samych narzedzi
to kilka metod JSON-RPC, a pakiet ciagnie starlette, uvicorn i pydantic -
ciezar dla startu programu i dla przyszlej kompilacji (punkt 18).
"""
