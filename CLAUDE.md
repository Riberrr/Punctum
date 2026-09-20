# Punctum — zasady pracy nad tym repozytorium

Nieniszczący edytor zdjęć RAW i JPEG. Python 3.14 + PySide6, venv w `.venv`.
Pełny opis programu jest w `README.md`; poniżej tylko to, czego trzeba się
trzymać przy zmianach w kodzie.

## Prywatność — repozytorium jest publiczne

Nigdy nie wstawiać do plików repozytorium ścieżek z dysku użytkownika, nazw
jego katalogów ze zdjęciami ani danych osobowych. W przykładach używać
neutralnych ścieżek w rodzaju `C:\Zdjęcia\Wycieczka`. Katalog ze zdjęciami
testowymi podaje się argumentem albo zmienną `PUNCTUM_TESTY`.

Przed commitem:

```powershell
git ls-files | ForEach-Object { Select-String -Path $_ -Pattern 'D:\\|C:\\Users\\' }
```

## Język i komentarze

- Interfejs, komunikaty i dokumentacja: po polsku.
- Komentarze i docstringi w kodzie: po polsku, **bez polskich znaków**
  (pliki źródłowe zostają w czystym ASCII poza napisami interfejsu).
- Komentarz mówi DLACZEGO, nie co: opisuje decyzję, kompromis albo pułapkę.
  Komentarz powtarzający kod jest do usunięcia.
- Program opisujemy jako „edytor zdjęć RAW". Słowo „wywoływarka" jest odrzucone.

## Uruchamianie i testy

```powershell
python -m punctum "C:\Zdjęcia\Wycieczka"              # albo Punctum.bat
tools\testy.bat --szybkie                             # bez interfejsu, ~5 s
tools\testy.bat "C:\Zdjęcia\Wycieczka"                # cała seria, ~37 s
tools\testy.bat "C:\Zdjęcia\Wycieczka" --pelny        # z pełnymi tabelami
.venv\Scripts\python.exe tools\test_exif.py           # pojedynczy obszar
```

Domyślnie każdy test wypisuje tylko to, co nie przeszło, i jedną linię
podsumowania; kod wyjścia to liczba błędów, więc seria przerywa po pierwszej
przegranej. W trakcie pracy puszczać `--szybkie` plus test obszaru, który się
rusza; całą serię raz, przed commitem. Przy zmianach w dokumentacji testy nie
są potrzebne.

Testy bez interfejsu nie potrzebują zdjęć. Testy z interfejsem otwierają
prawdziwe okno i potrzebują katalogu z co najmniej jednym RAW-em i dwoma
JPEG-ami; pliki dobiera `tools/wybierz_zdjecia.py`.

Wspólne części testów (raport, czekanie na warunek, łańcuch etapów) siedzą
w `tools/wspolne.py` — nowy test korzysta z nich, zamiast kopiować swoje.

Pisząc test z interfejsem:

- etapy spinać `lancuch(app, [etap1, etap2, ...], report)`, nigdy budzikiem
  `QTimer.singleShot(5000, ...)` — test ma trwać tyle, ile trwa praca,
- czekać na **warunek** (`czekaj(app, ...)`), nigdy na ustaloną liczbę sekund —
  obciążona maszyna wywracała testy przy poprawnym kodzie,
- zaślepić zapis ustawień (`window.settings.save = lambda *a, **k: True`) —
  inaczej test zapisuje swoje wartości do prawdziwych ustawień użytkownika,
- raport drukować w UTF-8 (`sys.stdout.reconfigure`), a sprzątanie trzymać
  w `finally` — polska konsola chodzi w cp1250 i potrafi wywrócić test na jego
  własnym wydruku,
- stan pozycji na listach sprawdzać przez dane (role), nie przez napisy.

## Zasady, które przesądzają o kodzie

1. **Zasada nieniszcząca.** Plik ze zdjęciem nie jest ruszany. Korekty,
   współrzędne i metadane idą do `EditParams` → sidecara XMP → pliku wynikowego
   przy eksporcie. Wyjątek tylko na wyraźne żądanie: „Zapisz do oryginału",
   i wyłącznie dla JPEG-a.
2. **Nowe pole w `EditParams` trzeba dopisać także do `core/sidecar.py`** —
   inaczej nie przeżyje zamknięcia programu.
3. **Operacje tonalne działają na danych liniowych**, krzywa sRGB idzie na
   końcu. Odwrócenie kolejności daje plastikowe kolory.
4. **Tor numpy (`core/pipeline.py`) i shader (`app/gpu_renderer.py`) muszą
   liczyć to samo.** Każda zmiana w jednym idzie do drugiego; pilnuje tego
   `tools/test_gpu.py`.
5. **Przetwarzanie pikseli przed powiększeniem, nigdy po** — inaczej filtry
   nie robią nic widocznego przy dużym zoomie.

## Git

- Gałąź `main`, zdalne `origin` = https://github.com/Riberrr/Punctum
- Autor ustawiony lokalnie dla repozytorium (brak konfiguracji globalnej).
- Opisy commitów po polsku, podawane przez plik (`git commit -F <plik>`),
  zapisany **poza** katalogiem `.git`. Opis mówi, jaki problem zamyka commit
  i jaką decyzję zapisuje — nie wylicza zmienionych plików.
- Commit zamyka obszar: kod + testy + zaktualizowane README.

## Struktura

```
punctum/core/   tor obróbki, wejście plików, sidecary, eksport, ustawienia
punctum/app/    okno, widoki, panele, zakładki, shader, zadania w tle
tools/          testy, narzędzia diagnostyczne i pomiarowe
```
