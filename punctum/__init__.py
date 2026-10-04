"""Punctum - edytor zdjec RAW i JPEG.

Edycja nieniszczaca: plik zrodlowy nigdy nie jest zmieniany, a komplet nastaw
opisuje `core.params.EditParams`.
"""

# Jedyne zrodlo numeru wersji: czytaja go ekran startowy, okno "O programie",
# metadane eksportu, serwer MCP i kompilacja (zasoby .exe, instalator).
# Schemat MAJOR.MINOR.PATCH; 0.x, dopoki program nie przejdzie proby przy
# prawdziwej obrobce - wtedy 1.0.0.
__version__ = "0.10.1"

# Identyfikator programu dla Windows (pasek zadan, skroty). Ten sam musi
# stac w oknie i w skrocie - inaczej przypiety skrot i uruchomione okno
# daja dwie osobne ikony na pasku zadan.
APP_ID = "Punctum.Punctum"
