@echo off
rem Skrot uruchamiajacy Punctum. Mozna go przeciagnac na pulpit.
rem Opcjonalnie: przeciagnij folder ze zdjeciami na ten plik, zeby otworzyc go od razu.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m punctum %*
