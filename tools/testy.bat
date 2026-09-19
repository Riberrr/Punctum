@echo off
rem Cala seria testow jednym poleceniem. Uruchamiane jeden po drugim, bo
rem wlasnie taki uklad wywolal kiedys chwiejnosc testow z interfejsem.
rem
rem Uzycie:  tools\testy.bat [katalog ze zdjeciami testowymi]
rem Katalog mozna tez podac raz na stale zmienna srodowiskowa PUNCTUM_TESTY.
rem Potrzebne sa w nim co najmniej jeden plik RAW i dwa JPEG-i; ktore to beda,
rem ustala tools\wybierz_zdjecia.py. Bez katalogu ida same testy bez interfejsu.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
set FOTO=%~1
if not defined FOTO set FOTO=%PUNCTUM_TESTY%

echo === bez interfejsu ===
%PY% tools\test_geo.py
%PY% tools\test_sidecar.py
%PY% tools\test_auto_zasady.py
%PY% tools\test_jpeg.py
%PY% tools\test_exif.py

if not defined FOTO (
    echo.
    echo Testy z interfejsem pominiete - podaj katalog ze zdjeciami:
    echo     tools\testy.bat ^<katalog^>
    goto :koniec
)

rem ZDJECIA to trzy sciezki w cudzyslowach, wiec porownania w rodzaju
rem  if "%%ZDJECIA%%"=="" rozsypuja sie na wlasnych cudzyslowach - stad "defined".
set ZDJECIA=
for /f "usebackq delims=" %%f in (`%PY% tools\wybierz_zdjecia.py "%FOTO%"`) do set ZDJECIA=%%f
if not defined ZDJECIA (
    echo.
    echo W podanym katalogu nie ma kompletu zdjec ^(1 RAW + 2 JPEG^) - pomijam testy z interfejsem.
    goto :koniec
)

echo.
echo === z interfejsem ===
%PY% tools\test_trwalosc_gui.py %ZDJECIA%
%PY% tools\test_mapa_gui.py %ZDJECIA%
%PY% tools\test_jpeg_gui.py %ZDJECIA%
%PY% tools\test_znaczniki_gui.py %ZDJECIA%

echo.
echo === porzadki w ustawieniach ===
%PY% tools\napraw_ustawienia.py

:koniec
endlocal
