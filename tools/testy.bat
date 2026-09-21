@echo off
rem Cala seria testow jednym poleceniem. Uruchamiane jeden po drugim, bo
rem wlasnie taki uklad wywolal kiedys chwiejnosc testow z interfejsem.
rem
rem Uzycie:  tools\testy.bat [katalog ze zdjeciami] [--szybkie] [--pelny]
rem
rem   --szybkie   same testy bez interfejsu (kilka sekund, nie potrzebuja zdjec)
rem   --pelny     pelne tabele zamiast samych bledow i podsumowan
rem
rem Katalog mozna tez podac raz na stale zmienna srodowiskowa PUNCTUM_TESTY.
rem Potrzebne sa w nim co najmniej jeden plik RAW i dwa JPEG-i; ktore to beda,
rem ustala tools\wybierz_zdjecia.py. Seria przerywa po pierwszym nieudanym
rem tescie - nie ma sensu czekac minute na reszte, gdy juz wiadomo, ze cos padlo.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
set FOTO=
set FLAGI=
set SZYBKIE=

:argumenty
if "%~1"=="" goto po_argumentach
if /i "%~1"=="--szybkie" (set SZYBKIE=1) else (
    if /i "%~1"=="--pelny" (set FLAGI=%FLAGI% --pelny) else (set FOTO=%~1)
)
shift
goto argumenty

:po_argumentach
if not defined FOTO set FOTO=%PUNCTUM_TESTY%

echo === bez interfejsu ===
for %%T in (test_geo test_sidecar test_auto_zasady test_jpeg test_exif) do (
    %PY% tools\%%T.py %FLAGI% || goto porazka
)

if defined SZYBKIE goto koniec

if not defined FOTO (
    echo.
    echo Testy z interfejsem pominiete - podaj katalog ze zdjeciami:
    echo     tools\testy.bat ^<katalog^>
    goto koniec
)

rem ZDJECIA to trzy sciezki w cudzyslowach, wiec porownania w rodzaju
rem  if "%%ZDJECIA%%"=="" rozsypuja sie na wlasnych cudzyslowach - stad "defined".
set ZDJECIA=
for /f "usebackq delims=" %%f in (`%PY% tools\wybierz_zdjecia.py "%FOTO%"`) do set ZDJECIA=%%f
if not defined ZDJECIA (
    echo.
    echo W podanym katalogu nie ma kompletu zdjec ^(1 RAW + 2 JPEG^) - pomijam testy z interfejsem.
    goto koniec
)

echo.
echo === z interfejsem ===
for %%T in (test_trwalosc_gui test_mapa_gui test_jpeg_gui test_znaczniki_gui test_uklad_gui) do (
    %PY% tools\%%T.py %ZDJECIA% %FLAGI% || goto porazka
)

echo.
echo === porzadki w ustawieniach ===
%PY% tools\napraw_ustawienia.py
goto koniec

:porazka
echo.
echo *** Seria przerwana - powyzszy test nie przeszedl. ***
endlocal
exit /b 1

:koniec
endlocal
exit /b 0
