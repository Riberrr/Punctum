@echo off
rem Cala seria testow jednym poleceniem. Uruchamiane jeden po drugim, bo
rem wlasnie taki uklad wywolal kiedys chwiejnosc testow z interfejsem.
rem Uzycie:  tools\testy.bat [katalog ze zdjeciami testowymi]
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
set FOTO=%~1
if "%FOTO%"=="" set FOTO=D:\zdjecia - plaska\2023 - Pozostale

echo === bez interfejsu ===
%PY% tools\test_geo.py
%PY% tools\test_sidecar.py
%PY% tools\test_auto_zasady.py
%PY% tools\test_jpeg.py

echo.
echo === z interfejsem ===
%PY% tools\test_trwalosc_gui.py "%FOTO%\01158845.rw2" "%FOTO%\01159590.jpg" "%FOTO%\01159592.jpg"
%PY% tools\test_mapa_gui.py "%FOTO%\01158845.rw2" "%FOTO%\01159590.jpg" "%FOTO%\01159592.jpg"
%PY% tools\test_jpeg_gui.py "%FOTO%\01158845.rw2" "%FOTO%\01159590.jpg" "%FOTO%\01159592.jpg"

echo.
echo === porzadki w ustawieniach ===
%PY% tools\napraw_ustawienia.py
endlocal
