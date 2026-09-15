# Punctum

Program do obróbki zdjęć RAW — nieniszczący edytor z obsługą RW2, CR2/CR3,
NEF, ARW i DNG, z podglądem liczonym na karcie graficznej.

> *A non-destructive RAW photo editor with a GPU-accelerated preview pipeline.
> The interface and documentation are currently Polish-only.*

## Uruchomienie

Dwuklik na `Punctum.bat` (można przeciągnąć na pulpit albo upuścić na niego
folder ze zdjęciami), lub z wiersza poleceń:

```powershell
python -m punctum "C:\Zdjęcia\Wycieczka"
```

Pierwsza instalacja:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Co działa

**Przeglądanie** — pasek miniatur wczytywany z podglądów wbudowanych w pliki
RAW (ok. 100 ms na zdjęcie), panel z aparatem, ogniskową, czasem, przysłoną,
ISO, datą i lokalizacją. Uszkodzone pliki są oznaczane, nie wywalają programu.

**Korekta** — balans bieli w kelwinach (suwaki z gradientem barwnym),
ekspozycja, kontrast, światła, cienie, biele, czernie, jaskrawość, nasycenie.
Dwuklik na suwaku przywraca wartość domyślną.

**Automatyczna korekcja** — przycisk *Automatycznie* dobiera parametry tonalne
z analizy histogramu. Wyniki pokrywają się z przyciskiem *Automatycznie*
w Lightroomie z dokładnością do kilku punktów (patrz niżej).

**Kadrowanie** — przycisk *Kadruj* (skrót `R`). Ciągnięcie za krawędzie i rogi
zmienia kadr, `Shift` zachowuje proporcje, ciągnięcie poza kadrem obraca
zdjęcie. W spoczynku widać trójpodział, podczas przeciągania siatkę 8×8.
Osobne przyciski obracają o 90° i 180°. `Enter` zatwierdza.

**Podgląd** — zoom kółkiem, dwuklik przełącza dopasowanie ↔ 100 %, nawigator
z ramką pokazującą powiększony fragment (klikalny), przytrzymanie *Przed / po*
pokazuje zdjęcie bez korekt, histogram na żywo.

**Redukcja szumu** — osobno luminancja i kolor.

**Eksport** — pełna rozdzielczość, dokładniejsze odszumianie, do wskazanego
katalogu.

## Ustawienia

`Plik ▸ Ustawienia…` (`Ctrl+,`). Okno ma cztery zakładki:

**Wydajność** — wykryty sprzęt (procesor z liczbą rdzeni i pamięcią, karta
graficzna z pamięcią i wersją OpenGL) oraz wybór silnika podglądu:

| Ustawienie | Zachowanie |
|---|---|
| Automatycznie | Karta, jeśli dostępna; w razie problemu zejście na procesor |
| Karta graficzna | Wymuszone liczenie na GPU |
| Procesor | Wymuszone liczenie na CPU, tekstura zwalniana z pamięci karty |

Tu też mieszka rozmiar podglądu (dłuższy bok obrazu liczonego dla widoku
dopasowanego do okna) i liczba wątków wczytujących miniatury.

**Podgląd** — opóźnienie doliczania ostrego fragmentu i redukcji szumu, jakość
odszumiania podglądu, próg powiększenia, powyżej którego obraz skalowany jest
najbliższym sąsiadem, widoczność nawigatora, a także zachowanie kółka myszy nad
suwakami (patrz niżej).

### Kółko myszy nad suwakami

Qt kieruje zdarzenie kółka do widżetu pod kursorem, więc przy przewijaniu długiej
listy suwaki podjeżdżają pod nieruchomy kursor i po drodze łapią zdarzenie —
użytkownik chciał przewinąć panel, a zmienił ekspozycję.

Suwak przyjmuje kółko dopiero, gdy spełnione są dwa niezależne warunki:

- **lista nie była przewijana** przez ostatnie 400 ms (parametr *Blokada po
  przewinięciu*) — dzięki temu ciągłe przewijanie nigdy nie zahacza o suwak,
- **kursor stoi nad suwakiem** od co najmniej 220 ms (parametr *Wymagane
  zatrzymanie*) — to łapie suwak, który dopiero podjechał pod kursor.

Celowe użycie — najedź i kręć — działa bez zmian. Zero w polu *Blokada po
przewinięciu* wyłącza zabezpieczenie i przywraca zachowanie Qt.

Gdy warunki nie są spełnione, suwak wywołuje `event.ignore()` i Qt przekazuje
zdarzenie wyżej, do obszaru przewijania — panel przewija się normalnie.

**Eksport** — format, jakość JPEG, dłuższy bok, jakość odszumiania, domyślny
katalog docelowy.

**O programie** — wersja, pełne dane sprzętu i sterownika, ścieżka pliku
ustawień, wersje bibliotek.

Ustawienia lądują w `%APPDATA%\Punctum\settings.json` (na Linuksie
`~/.config/Punctum/`). Zapis idzie przez plik tymczasowy, więc przerwanie nie
zostawia uszkodzonego pliku. Odczyt jest pobłażliwy: nieznane klucze są
pomijane, brakujące uzupełniane domyślnymi, wartości spoza zakresu przycinane —
uszkodzony plik nie zablokuje uruchomienia programu.

## Architektura

### Edycja nieniszcząca

Plik RAW nigdy nie jest modyfikowany. Komplet nastaw opisuje klasa
`EditParams`; obraz wyjściowy powstaje dopiero przy eksporcie.

### Dekodowanie raz, edycja wielokrotnie

`load_raw()` dekoduje plik **jeden raz** do liniowego float32 w przestrzeni
barw aparatu i trzyma go w pamięci. Każdy ruch suwaka operuje już tylko na tej
tablicy — bez tego każda zmiana kosztowałaby ~0,9 s na ponowne dekodowanie.

Demozaikowanie i rekonstrukcję świateł zostawiamy LibRaw. Przejmujemy kontrolę
od momentu, gdy mamy liniowe RGB.

### Kolejność operacji

```
dekodowanie → demozaikowanie → WB aparatu      (LibRaw)
─────────────────────────────────────────────────────────
geometria (obrót 90°, kąt, kadr)
korekta balansu bieli          ┐
przestrzeń aparatu → sRGB      │
ekspozycja                     │ wszystko na danych LINIOWYCH
światła / cienie               │
biele / czernie                │
kontrast                       ┘
krzywa przenoszenia sRGB       ← dopiero tutaj gamma
nasycenie / jaskrawość         ← po krzywej, jak w Lightroomie
redukcja szumu
```

Operacje tonalne **muszą** działać na danych liniowych. Nałożenie gammy przed
ekspozycją daje plastikowe, „cyfrowe" kolory — najczęstszy błąd w amatorskich
programach do obróbki RAW.

### Dwie warstwy podglądu

Spodnia warstwa to obraz z proxy (1600 px) rozciągnięty na całe zdjęcie —
pojawia się natychmiast, ale przy powiększeniu jest miękki. Wierzchnia to
widoczny fragment przeliczony z **pełnej rozdzielczości, od razu w
rozdzielczości ekranu**; dokłada się po ~160 ms i to ona daje ostrość.

Kluczowa sztuczka: obrót, przesunięcie kadru i powiększenie składamy w jedną
macierz przekształcenia i każemy `warpAffine` policzyć wyłącznie widoczny
prostokąt. Koszt zależy więc od rozmiaru okna, a nie od stopnia powiększenia
ani wielkości pliku. Zmierzony zysk ostrości względem rozciągniętego proxy:
**18×** (wariancja laplasjanu 47,4 wobec 2,6).

### Balans bieli w kelwinach

Aparat zapisuje wyłącznie mnożniki kanałów, nie temperaturę barwową. Żeby
pokazać „7110 K", `estimate_temp_tint()` przeszukuje krzywą Plancka i znajduje
temperaturę dającą najbardziej zbliżone mnożniki. Lightroom dla tego samego
pliku pokazuje 7100 K.

Poprawność macierzy potwierdza `tools/verify_color.py` — mnożniki policzone
dla D65 muszą zgadzać się z `daylight_whitebalance` z pliku. Różnica: 0,006 %.

### Redukcja szumu

Szum koloru to plamy o niskiej częstotliwości — usuwamy je zmniejszając kanały
chrominancji, rozmywając i skalując z powrotem. Szczegóły obrazu siedzą
w luminancji, więc jest to praktycznie niewidoczne.

Luminancję czyści non-local means w trzech poziomach dokładności: filtr
bilateralny na podglądzie dopasowanym do okna, okno 5/11 na doliczanym
fragmencie przy powiększeniu, okno 7/21 przy eksporcie.

Dwie rzeczy okazały się kluczowe i obie były źródłem błędów:

**Odszumianie musi działać na pikselach natywnych, przed powiększeniem.**
Wcześniej tor liczył je po przeskalowaniu, więc przy 400 % ziarno było
czterokrotnie większe niż zasięg filtra i suwak nie robił nic widocznego.
Przy okazji poprawna kolejność jest tańsza — im większe powiększenie, tym
mniej natywnych pikseli trzeba przeliczyć (26 ms przy 400 % wobec 164 ms
przy 100 %).

**Siłę suwaka realizujemy mieszaniem, nie parametrem `h`.** Non-local means
działa progowo: poniżej `h ≈ 3` nie robi nic, powyżej 10 jest nasycony.
Odwzorowanie suwaka wprost na `h` dawało martwe zakresy — przy sile 25 szum
znikał całkowicie, a 30–100 nie różniło się niczym. Liczymy więc jedno mocne
odszumianie i mieszamy je z oryginałem proporcjonalnie do suwaka; szum
resztkowy maleje wtedy liniowo.

Zmierzone na zdjęciu ISO 3200 przy powiększeniu 400 % (odchylenie szumu):

| suwak | 0 | 25 | 50 | 75 | 100 |
|---|---:|---:|---:|---:|---:|
| szum | 7,33 | 6,06 | 4,26 | 2,51 | 1,17 |

### Automatyczna korekcja

Progi wyrażone w działkach EV, nie w ułamkach jasności — oko reaguje na światło
logarytmicznie. Ekspozycja celuje 90. percentylem w szarość 18 %, ale nigdy
kosztem wypalenia świateł. Kompresja świateł i cieni zależy od rozpiętości
tonalnej sceny: zachód słońca ma ok. 8 EV i wymaga silnej, płaskie niebo 4,6 EV
i prawie żadnej.

Porównanie z Lightroomem na pliku `01158845.rw2`:

| parametr | Punctum | Lightroom |
|---|---:|---:|
| ekspozycja | +1,20 | +1,00 |
| kontrast | +7 | +6 |
| podświetlenia | −54 | −47 |
| cienie | +62 | +57 |
| biele | +15 | +9 |
| czernie | −9 | −8 |

Balansu bieli automat celowo nie rusza — aparat zna warunki oświetlenia lepiej
niż histogram.

### Tor tonalny na karcie graficznej

Podgląd liczy fragment shader GLSL w kontekście OpenGL 3.3 poza ekranem. Dane
RAW w pełnej rozdzielczości trafiają do pamięci karty **raz**, przy otwarciu
zdjęcia (244 MB, ~20 ms). Każdy ruch suwaka to potem podmiana kilkunastu
uniformów i ponowne narysowanie prostokąta.

Z jednej tekstury powstaje zarówno podgląd dopasowany do okna, jak i ostry
fragment przy powiększeniu — mipmapy załatwiają poprawne pomniejszanie.
Geometria (obrót o 90°, kąt, kadr, powiększenie) siedzi w jednej macierzy
przekształcającej współrzędne tekstury, więc kadrowanie i obracanie są równie
tanie co suwaki.

Macierz pochodzi z modułu `core/geometry.py`, z którego korzysta również tor
numpy — dzięki temu obie implementacje nie mogą się rozjechać. Zgodność
sprawdza `tools/test_gpu.py`: na ośmiu zestawach parametrów (z geometrią
włącznie) średnia różnica wynosi **0,04 poziomu jasności**, maksymalna 1.

Odszumianie zostaje na procesorze — non-local means nie ma sensownego
odpowiednika w shaderze. Jest osobnym, opóźnionym krokiem: podgląd pojawia się
natychmiast, a szum znika chwilę później, gdy suwak stanie.

## Zmierzona wydajność

Panasonic DC-G91, 20 Mpix (5200 × 3904), NVIDIA GTX 1660.

Opóźnienie od ruchu suwaka do odświeżonego podglądu (`tools/test_lag.py`),
mierzone przez pełną drogę zdarzenia — próg dostrzegalności to ok. 16 ms:

| Operacja | Mediana | Najgorzej |
|---|---:|---:|
| Suwak ekspozycji | 11,5 ms | 18,9 ms |
| Suwak cieni (maski EV) | 12,4 ms | — |
| Suwak temperatury barwowej | 12,5 ms | 19,6 ms |
| Suwak kąta obrotu | 11,4 ms | 17,6 ms |
| Ciągnięcie narożnika kadru | 3,2 ms | 6,1 ms |
| Obrót ciągnięciem poza kadrem | 12,7 ms | 16,3 ms |
| Doliczanie ostrego fragmentu | 16,3 ms | 21,2 ms |

Sam shader liczy podgląd w **5,9 ms** (169 klatek na sekundę); reszta to
konwersja obrazu i odświeżenie widżetów.

Pozostałe operacje:

| Operacja | Czas |
|---|---|
| Miniatura z pliku RAW | 102 ms |
| Pełne dekodowanie | 894 ms |
| Wgranie tekstury do karty | 20 ms |
| Analiza do automatu | 90 ms |
| Obróbka pełna na procesorze (eksport) | 4562 ms |

Tor numpy pozostaje jako ścieżka referencyjna i eksportowa oraz jako
zabezpieczenie: gdy kontekst OpenGL nie wstanie, aplikacja wraca na procesor
i pisze o tym na pasku stanu.

## Struktura

```
punctum/core/
    params.py        komplet nastaw edycji (EditParams)
    whitebalance.py  krzywa Plancka, kelwiny ↔ mnożniki, macierze barw
    raw_loader.py    dekodowanie RAW, proxy, miniatury, orientacja
    pipeline.py      tor tonalny, geometria, redukcja szumu
    auto.py          automatyczny dobór parametrów
    metadata.py      odczyt EXIF (z obsługą pól własnych Panasonica)
    export.py        zapis JPEG / PNG / TIFF
punctum/app/
    main_window.py   złożenie całości
    image_view.py    płótno, zoom, warstwa detalu, kadrowanie
    edit_panel.py    histogram, dane zdjęcia, suwaki
    sliders.py       suwaki, w tym te z gradientem barwnym
    navigator.py     miniatura z ramką powiększenia
    filmstrip.py     pasek miniatur
    workers.py       zadania w tle
tools/               narzędzia diagnostyczne, testy i CLI
```

## Czego jeszcze nie ma

- Zapisu ustawień między sesjami (SQLite, sidecary XMP).
- Mapy i geotagowania — główny cel projektu, następny w kolejce.
- Presetów i kopiowania ustawień między zdjęciami.
- Eksportu wsadowego (na razie jedno zdjęcie naraz).
- Integracji z Google Photos.
