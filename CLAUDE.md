# Punctum — zasady pracy nad tym repozytorium

Nieniszczący edytor zdjęć RAW i JPEG. Python 3.14 + PySide6, venv w `.venv`.
Pełny opis programu jest w `README.md`; poniżej tylko to, czego trzeba się
trzymać przy zmianach w kodzie.

## Tryb pracy: najpierw ustalenia, potem kod

**Nie zaczynaj pisać kodu, dopóki użytkownik nie powie wyraźnie: „piszemy kod".**
Do tego momentu trwa ustalanie zakresu — i to nie jest formalność, tylko
najtańszy moment na decyzje. Poprawka wyglądu wprowadzona po fakcie kosztuje
pełny cykl (edycje, testy, commit); ta sama decyzja podjęta wcześniej kosztuje
jedno zdanie.

Przed sygnałem **wolno**: czytać pliki i notatki, szukać w kodzie, uruchamiać
pomiary i diagnostykę tylko do odczytu, pokazywać zrzuty i warianty.
Przed sygnałem **nie wolno**: zmieniać plików w repozytorium, commitować,
pisać „na szybko, żeby pokazać".

Ustalenia spisujemy jako kartę punktu:

```
PUNKT n — nazwa
Problem:        co dziś boli, w jednym zdaniu
Oczekiwanie:    jak ma być po zmianie
Gotowe, gdy:    2-4 sprawdzalne warunki
Nie ruszamy:    co zostaje jak jest
Decyzje:        rozstrzygniete z gory, zeby nie pytac w trakcie
Otwarte:        co zdecydujemy, patrzac na wynik
```

Pytania zadawać **hurtem, do czterech naraz i tylko te, których zła odpowiedź
kosztuje przeróbkę** — nie pojedynczo, bo każda runda pytań kosztuje tyle, co
przeczytanie całej rozmowy. O rzeczy obojętne nie pytać: wybrać samemu
i napisać, co się wybrało. Karta trafia do notatek projektu dopiero wtedy, gdy
jest kompletna.

**Kolejność: najpierw pytanie, potem czytanie kodu** — o ile odpowiedź zmienia
to, CO trzeba przeczytać. Przeczytany plik zostaje w kontekście do końca sesji
i dolicza się do każdej następnej rundy; niepotrzebnie otwarty moduł kosztuje
wielokrotnie więcej niż jedno zdanie pytania. Jeśli opis zadania ma dziurę,
powiedzieć o niej od razu, zamiast zgadywać i czytać „na wszelki wypadek".

Odwrotnie, gdy pytanie dotyczy samego kodu („jak to jest dziś zrobione") albo
gdy rozstrzyga je jeden pomiar — wtedy sprawdzić, a nie pytać. Pytanie
o fakty z repozytorium to przerzucanie własnej roboty na użytkownika.

Lista dziur do sprawdzenia w każdym zadaniu: cel, czego NIE ruszamy, kryterium
gotowości, wygląd i umiejscowienie (gdy dotyczy interfejsu), zachowanie
w sytuacjach brzegowych, wpływ na sidecar, eksport i testy.

Przy usterkach interfejsu **prosić o zrzut z ponumerowanymi zaznaczeniami**,
najlepiej wycinek samego fragmentu okna, plus jedna linia tekstu na numer.
Obrazek mówi GDZIE, tekst mówi CO ma być inaczej — samo jedno albo drugie
kończy się zgadywaniem i przeróbką. Usterek dynamicznych (miganie, kolejność
zdarzeń, co się dzieje po kliknięciu) zrzut nie pokaże: tam liczy się opis
objawu, a rozstrzyga pomiar. Zrzuty „po zmianie" robimy sami
(`window.grab().save(...)` w tescie), nie prosimy o nie uzytkownika.

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
