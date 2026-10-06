#!/usr/bin/env bash
# Cala seria testow na macOS i Linuksie - odpowiednik tools\testy.bat.
# Listy testow musza byc te same co w testy.bat (pilnuje test_platforma).
#
# Uzycie:  tools/testy.sh [katalog ze zdjeciami] [--szybkie] [--pelny]
#
# PY mozna podmienic zmienna srodowiskowa (w CI: python z setup-python).
cd "$(dirname "$0")/.." || exit 1
PY="${PY:-.venv/bin/python}"
FOTO=""
FLAGI=""
SZYBKIE=""

for arg in "$@"; do
    case "$arg" in
        --szybkie) SZYBKIE=1 ;;
        --pelny) FLAGI="$FLAGI --pelny" ;;
        *) FOTO="$arg" ;;
    esac
done
[ -z "$FOTO" ] && FOTO="$PUNCTUM_TESTY"

porazka() {
    echo
    echo "*** Seria przerwana - powyzszy test nie przeszedl. ***"
    exit 1
}

echo "=== bez interfejsu ==="
for T in test_geo test_sidecar test_auto_zasady test_jpeg test_exif test_podpowiedzi test_przeklad test_ekran_startowy test_panele test_historia test_slad test_presety test_znak_wodny test_mcp test_program_exe test_instalator test_changelog test_licencje test_instancja test_platforma; do
    "$PY" "tools/$T.py" $FLAGI || porazka
done

[ -n "$SZYBKIE" ] && exit 0

if [ -z "$FOTO" ]; then
    echo
    echo "Testy z interfejsem pominiete - podaj katalog ze zdjeciami:"
    echo "    tools/testy.sh <katalog>"
    exit 0
fi

# wybierz_zdjecia.py wypisuje sciezki w cudzyslowach (dla cmd) - eval
# rozbiera je na osobne argumenty razem ze spacjami w nazwach.
ZDJECIA="$("$PY" tools/wybierz_zdjecia.py "$FOTO")"
if [ -z "$ZDJECIA" ]; then
    echo
    echo "W podanym katalogu nie ma kompletu zdjec (1 RAW + 2 JPEG) - pomijam testy z interfejsem."
    exit 0
fi
eval "set -- $ZDJECIA"

echo
echo "=== z interfejsem ==="
for T in test_trwalosc_gui test_mapa_gui test_jpeg_gui test_znaczniki_gui test_uklad_gui test_panele_gui test_szum_podglad_gui test_podpowiedzi_gui test_historia_gui test_podzial_gui test_mcp_gui test_gpu_kolor; do
    "$PY" "tools/$T.py" "$@" $FLAGI || porazka
done

echo
echo "=== porzadki w ustawieniach ==="
"$PY" tools/napraw_ustawienia.py
exit 0
