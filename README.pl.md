# Punctum

Nieniszczący edytor zdjęć — RAW (RW2, CR2/CR3, NEF, ARW, DNG) oraz JPEG,
z podglądem liczonym na karcie graficznej i geotagowaniem na mapie.

> English version: [README.md](README.md). Program działa po polsku i po
> angielsku; język wybiera się w ustawieniach.

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
Nad paskiem miniatur siedzi przełącznik formatów (wszystkie / tylko RAW /
tylko JPEG) — w katalogu z tysiącami JPEG-ów i garścią RAW-ów bez tego nie
da się pracować. Wybór jest zapamiętywany.

**Korekta** — balans bieli w kelwinach (suwaki z gradientem barwnym),
ekspozycja, kontrast, światła, cienie, biele, czernie, jaskrawość, nasycenie.
Dwuklik na suwaku przywraca wartość domyślną.

**Automatyczna korekcja** — przycisk *Automatycznie* dobiera parametry tonalne
z analizy histogramu. Wyniki pokrywają się z przyciskiem *Automatycznie*
w komercyjnym programie, który służył za punkt odniesienia, z dokładnością do kilku punktów (patrz niżej).

**Kadrowanie** — przycisk z ikoną kadru (skrót `R`). Ciągnięcie za krawędzie
i rogi zmienia kadr, `Shift` zachowuje proporcje, ciągnięcie poza kadrem obraca
zdjęcie. W spoczynku widać trójpodział, podczas przeciągania siatkę 8×8.
Osobne przyciski obracają o 90° i 180°. `Enter` zatwierdza.

**Podgląd** — zoom kółkiem, suwakiem (logarytmicznym, od „dopasuj” do 1600 %)
albo przyciskami *Dopasuj* / *100 %*; dwuklik przełącza dopasowanie ↔ 100 %.
Nawigator z ramką pokazującą powiększony fragment (klikalny), przytrzymanie
*Przed / po* pokazuje zdjęcie bez korekt, histogram na żywo.

**Wyostrzanie** — ilość, promień, szczegóły, maskowanie; RAW domyślnie 40,
JPEG 0 (wyostrzył go już aparat).

**Usuwanie szumu** — osobno szum jasności i szum koloru, siła dopasowana do
szumu zmierzonego na zdjęciu.

**Eksport** — `Ctrl+E` otwiera okno z kompletem opcji: katalog docelowy,
opcjonalny podfolder, zachowanie wobec istniejących plików, nazwa z numeratorem,
format, jakość, ograniczenie dłuższego boku i dokładność odszumiania. Na dole
widać pełną ścieżkę pierwszego pliku, więc skutek wszystkich nastaw naraz jest
widoczny przed kliknięciem.

Eksport idzie w tle — pasek postępu z licznikiem siedzi w pasku stanu i można
go przerwać. Błąd pojedynczego pliku nie zatrzymuje reszty; lista problemów
pokazuje się na końcu.

Zaznaczenie kilku zdjęć w pasku miniatur (`Ctrl`, `Shift`) eksportuje je razem.
Program pamięta nastawy **osobno dla każdego zdjęcia**, więc powrót do wcześniej
poprawionego kadru przywraca suwaki. Zdjęcia, których nigdy nie otwarto, wychodzą
bez zmian — okno eksportu mówi o tym wprost, zanim zaczniesz.

## Okno programu

Okno ma dwie zakładki ułożone jak ścieżka pracy: **Edycja** i **Mapa**.
Kolejne moduły (biblioteka, albumy, pokaz slajdów) mogą w przyszłości
dochodzić jako następne zakładki. Przycisk *Eksportuj…* stoi w prawym rogu
belki zakładek, więc jest pod ręką w obu widokach.

Zakładka Edycja:

```
┌──────────────┬──────────────────────────────────┬─────────────────────┐
│ nawigator    │                                  │ histogram           │
│              │                                  ├─────────────────────┤
│ ─●────────── │                                  │ KADROWANIE I OBRÓT  │
│ Dopasuj 100 %│             podgląd              │ [kadr] ↺90 180 90↻  │
│ [Przed / po] │                                  │ Kąt ──────●───────  │
│              │                                  │ [  Wyzeruj kadr   ] │
│ dane zdjęcia │                                  │ [Automat.][Wyzeruj] │
│   ▾ EXIF     │                                  ├─────────────────────┤
│              │                                  │ suwaki — przewija   │
│              │                                  │ się tylko ta część  │
├──────────────┴──────────────────────────────────┴─────────────────────┤
│ Pokaż: [Wszystkie ▾]   1 RAW • 2 JPEG                                 │
│ ▢ ▢ ▢ ▢ ▢ ▢ ▢   pasek miniatur                                        │
└───────────────────────────────────────────────────────────────────────┘
```

**Lewy panel** odpowiada na pytania „gdzie jestem w zdjęciu" i „co to za
zdjęcie":

- **nawigator** — całe zdjęcie z ramką widocznego fragmentu; kliknięcie albo
  przeciągnięcie przenosi tam podgląd. Rośnie razem z szerokością panelu,
  można go ukryć w ustawieniach,
- **suwak powiększenia** — logarytmiczny, od „dopasuj do okna" do 1600 %.
  Skala logarytmiczna, bo między dopasowaniem (np. 12 %) a maksimum jest ponad
  sto razy: przy liniowej cały zakres poniżej 100 % mieściłby się w kilku
  pikselach. Suwak, kółko myszy i przyciski *Dopasuj* / *100 %* chodzą
  razem; pod spodem pojawia się stan dociągania ostrego fragmentu
  („ostrzenie…", „pełna ostrość"),
- **Przed / po** — przytrzymanie pokazuje zdjęcie bez korekt. Wiersz ma
  miejsce na drugi przycisk: podzielony podgląd przed/po jest w planach,
- **dane zdjęcia** — aparat, ogniskowa, czas, przysłona, ISO, data
  i lokalizacja. Strzałka w rogu rozwija pełne metadane (patrz niżej); wtedy
  przewija się wyłącznie ta sekcja, a nawigator i powiększenie zostają na
  miejscu. Przyciski *Wszystkie tagi*, *Wyczyść zmiany* i *Zapisz do
  oryginału* są przypięte na dole sekcji.

**Prawy panel** zbiera to, co zmienia zdjęcie. Na górze, zawsze widoczne:
histogram, kadrowanie i obrót (przycisk kadrowania, obroty o 90° i 180°,
suwak kąta, *Wyzeruj kadr*) oraz wiersz *Automatycznie* / *Wyzeruj*. Pod
nimi lista suwaków — balans bieli, odcień, obecność, redukcja szumu —
przewijana we własnym obszarze.

**Rozmiary.** Szerokość obu paneli i wysokość paska miniatur zmienia się
przeciąganiem krawędzi (uchwyt podświetla się pod kursorem):

| Element | Zakres | Domyślnie |
|---|---|---|
| lewy panel | 220–420 px | 260 px |
| prawy panel | 290–480 px | 340 px |
| pasek miniatur | 90–260 px | 150 px |

Przy zmianie rozmiaru okna wolne miejsce dostaje podgląd, panele trzymają
swoją szerokość. Miniatury rosną razem z paskiem (zawsze jeden rząd) i są
przechowywane w rozdzielczości 300×208, żeby przy wysokim pasku nie były
rozmyte. Program pamięta wszystkie trzy rozmiary między uruchomieniami.
Rozwinięcie metadanych nie zmienia szerokości żadnego panelu ani podglądu.

### Menu i skróty

| Menu | Polecenie | Skrót |
|---|---|---|
| Plik | Otwórz folder… | `Ctrl+O` |
| | Eksportuj… | `Ctrl+E` |
| | Ostatnie katalogi | |
| | Ustawienia… | `Ctrl+,` |
| | Zakończ | `Alt+F4` |
| Edycja | Automatyczna korekcja | `Ctrl+U` |
| | Kadrowanie (włącz / wyłącz) | `R` |
| Widok | Dopasuj do okna | `Ctrl+0` |
| | Powiększenie 100 % | `Ctrl+1` |
| Pomoc | O programie | |

W trybie kadrowania `Enter` albo `Esc` kończy kadrowanie. Dwuklik na podglądzie
przełącza dopasowanie ↔ 100 %, dwuklik na suwaku przywraca jego wartość
domyślną. *Pomoc ▸ O programie* otwiera okno ustawień od razu na zakładce
„O programie".

## Mapa i geotagowanie

W zakładce **Mapa** po lewej stoi lista zdjęć z miniaturami i znacznikami
stanu, pośrodku mapa OpenStreetMap z wyszukiwarką miejsc i czterema warstwami
(mapa, ciemna, satelita, hybryda), a po prawej panel metadanych.

Nadawanie lokalizacji: zaznacz zdjęcia na liście, włącz *Przypisz zaznaczonym*
i kliknij miejsce na mapie — wszystkie zaznaczone dostają ten punkt. Pinezki
pokazują zarówno lokalizacje nadane w programie, jak i te, które zdjęcia miały
już z aparatu albo telefonu. Dwuklik na liście wraca do edycji tego zdjęcia.

**Współrzędne nie trafiają do pliku źródłowego.** Lądują w sidecarze XMP, tak
jak korekty, a do metadanych wpisujemy je dopiero w pliku wynikowym przy
eksporcie — do ostatniej chwili można się rozmyślić, a oryginał zostaje
nietknięty. W samym sidecarze są obie postaci: nasza (liczba ze znakiem)
i `exif:GPS*` dla innych programów.

Mapa to strona Leaflet w silniku przeglądarki, przeniesiona z osobnej
aplikacji GeoTagger napisanej wcześniej w PyQt6. Dwa wiązania Qt nie mogą
współistnieć w jednym procesie — każde ładuje własną kopię bibliotek Qt —
więc strona została przeniesiona, a nie uruchomiona obok. Sama treść (HTML
i JavaScript) przeniosła się bez zmian; zmienił się sposób rozmowy z Pythonem:
**QWebChannel** zamiast kolejki komunikatów odpytywanej zegarem co 100 ms.
Stara aplikacja importowała QWebChannel, ale go nie używała.

Mapa powstaje przy starcie programu, zanim okno pojawi się na ekranie — i jest
to decyzja o **migotaniu**, nie o wydajności. Silnik przeglądarki potrzebuje
okna natywnego zdolnego do kompozycji OpenGL; dołożony do okna, które już stoi
na ekranie, każe Qt przebudować całe okno najwyższego poziomu. Wygląda to tak,
jakby program na ułamek sekundy znikał i wracał. Widać to wprost po uchwycie
okna: przy budowie leniwej zmieniał się przy pierwszym wejściu na zakładkę,
przy budowie przed pokazaniem okna zostaje ten sam (`tools/diag_zakladki.py`).
Kosztuje to ok. 260 ms startu (2080 → 2340 ms), ale dzieje się, zanim
użytkownik cokolwiek zobaczy. Sam widżet OpenGL zamiast mapy nie wystarcza —
sprawdzone, okno i tak się przebudowuje.

Bez internetu zakładka mówi wprost, czego brakuje, zamiast pokazywać szary
prostokąt; lista zdjęć i usuwanie lokalizacji działają dalej.

## Trwałość pracy

Zamknięcie programu nie gubi korekt. Nastawy każdego zdjęcia lądują w osobnym
pliku XMP obok oryginału i wracają na suwaki przy kolejnym otwarciu katalogu.
Dzięki temu obróbkę dwóch tysięcy zdjęć można rozłożyć na kilka dni i dopiero
na końcu wyeksportować całość.

Zasada nieniszcząca dotyczy też zapisu: **plik ze zdjęciem nie jest ruszany**.

Zapis idzie przy każdym przejściu na inne zdjęcie i przy zamknięciu okna, a nie
dopiero na koniec sesji — zawieszenie programu po trzech godzinach pracy ma
kosztować jedno zdjęcie, nie trzy godziny. Kosztuje 2 ms, więc nie da się go
zauważyć.

Obie listy zdjęć — pasek miniatur w Edycji i kolumna w Mapie — mówią tym samym
językiem. Zdjęcie dostaje dwa niezależne znaczniki:

| Znacznik | Znaczenie |
|---|---|
| kropka | zdjęcie ma zapisaną pracę (nastawy w sidecarze) |
| pinezka | zdjęcie ma współrzędne — nadane w programie albo z aparatu |

Znaczniki są **rysowane**, a nie wpisywane w nazwę pliku: znak w tekście
przesuwałby nazwy w każdym wierszu inaczej i lista przestawałaby się czytać
jedna pod drugą. W pasku miniatur siedzą w rogach kafelka, w kolumnie w Mapie
w stałym miejscu przed nazwą — tam też miniatury stoją przy prawej krawędzi,
żeby wszystkie nazwy zaczynały się w tym samym miejscu.

Pasek stanu podaje, ilu zdjęć dotyczy pierwszy z nich. Bez tego dzielenie
obróbki na etapy nie miałoby sensu, bo po otwarciu katalogu nie wiadomo by
było, gdzie się skończyło — a przy geotagowaniu nie widać by było, które kadry
wciąż czekają na pinezkę.

W pliku XMP są dwa komplety wartości. Pola `crs:` to te same nazwy, których
używa Camera Raw — inny program coś z nich odczyta. Zgodność jest jednak tylko
częściowa, bo nasze suwaki nie odpowiadają jeden do jednego tamtym, więc
traktujemy je jako grzeczność, a nie źródło prawdy. Pola `punctum:` to nasze
dokładne wartości i to z nich czytamy.

Dwie decyzje warte uwagi:

- **Cudzych plików nie nadpisujemy.** Jeśli obok zdjęcia leży XMP napisany
  w innym programie, nasze nastawy idą do `<nazwa>.punctum.xmp`. Dodatkowy plik
  jest mniejszym złem niż skasowana cudza praca.
- **Cudzych nastaw nie podstawiamy pod suwaki.** Wczytanie sidecara
  z innego programu wyglądałoby jak przeniesienie edycji, a po cichu zmieniałoby
  zdjęcie — te same liczby znaczą u nas co innego.

Funkcję można wyłączyć w `Plik ▸ Ustawienia… ▸ Eksport ▸ Ogólne`. Menu `Plik`
pamięta też ostatnio otwierane katalogi.

## Metadane (EXIF)

Panel metadanych stoi w obu zakładkach. W Edycji jest chowanym dnem sekcji
z danymi zdjęcia w lewym panelu — rozwija go strzałka w jej rogu, więc zwinięty
nie zajmuje ani jednego wiersza, a rozwinięty zajmuje resztę wysokości panelu
i przewija się sam, bez ruszania nawigatora i suwaka powiększenia.
W Mapie jest kolumną po prawej stronie okna. Obie kopie pokazują ten sam stan.

Edytowalnych pól jest dziewiętnaście, w sześciu grupach: autorstwo (autor,
prawa autorskie), opis (tytuł, komentarz, słowa kluczowe, temat), czas (trzy
daty), sprzęt (producent, model, obiektyw, numer seryjny, oprogramowanie),
naświetlenie (ISO, przysłona, czas, ogniskowa) i orientacja. Przycisk
*Wszystkie tagi* pokazuje dodatkowo pełną zawartość pliku, tylko do odczytu —
czytaną dopiero po kliknięciu, bo przy dwóch tysiącach zdjęć nie ma powodu
czytać wszystkiego z każdego pliku.

Zmiany idą tą samą drogą, co korekty i współrzędne: **do sidecara**, a do
metadanych pliku dopiero przy eksporcie. Przycisk *Zapisz do oryginału* robi
wyjątek na żądanie — wpisuje je wprost w plik ze zdjęciem:

- **tylko JPEG.** RW2 to zamknięty format Panasonica i majstrowanie w jego
  nagłówku skończyłoby się uszkodzonym plikiem. Program mówi to wprost, zamiast
  po cichu pomijać takie zdjęcia.
- **bezstratnie** — przepisywany jest sam nagłówek EXIF, piksele zostają
  nietknięte, a data pliku wraca na swoje miejsce po zapisie.
- **dotychczasowe metadane zostają.** Wpisujemy tylko pola zmienione w panelu;
  reszta nagłówka, razem z blokiem GPS, przechodzi bez zmian.

Puste pole znaczy „nie zmieniam", a nie „skasuj tag" — kasowanie metadanych
jest nieodwracalne, więc nie może się zdarzyć przez nieuwagę.

## Pliki JPEG

JPEG przechodzi przez dokładnie ten sam tor, co RAW — wraz z automatem,
kadrowaniem, odszumianiem i podglądem na karcie graficznej. Różnica jest
jedna i siedzi we wczytywaniu: z JPEG-a zdejmujemy krzywą sRGB, żeby wejść
w tor liniowy. Poprawność tego kroku sprawdza `tools/test_jpeg.py` — plik
przepuszczony przez cały tor bez żadnych korekt wychodzi **piksel w piksel
taki sam**.

Czego z JPEG-a nie da się odzyskać:

- **nie ma zapasu w światłach** — w RAW nad białą ścianą zostaje jeszcze
  materiał do ściągnięcia, w JPEG-u wszystko powyżej punktu bieli zostało
  ścięte przy zapisie,
- **w cieniach jest 8 bitów zamiast dwunastu** — mocne podnoszenie pokaże
  schodki tam, gdzie RAW dałby gładkie przejście,
- **nie ma mnożników aparatu ani macierzy barw**, więc temperatury „jak na
  ujęciu" nie da się odtworzyć.

Dlatego balans bieli działa przy JPEG-u inaczej i program mówi to wprost:
suwak nazywa się wtedy *Temperatura (wzgl.)*, a pasek stanu pisze „balans
bieli względny". Przyjmujemy, że plik jest w sRGB o punkcie bieli D65 (6500 K)
i że taki jest jego stan wyjściowy; suwak przesuwa barwę **względem tego, co
zapisał aparat**, a nie względem światła sceny. Kelwiny są tu umowne.

Eksport pilnuje jednej rzeczy więcej niż przy RAW: plik źródłowy nigdy nie
jest celem. Przy RAW było to niemożliwe (wynik ma inne rozszerzenie), przy
JPEG-u eksport do tego samego katalogu trafiałby dokładnie w oryginał —
dostaje więc nową nazwę niezależnie od wybranej polityki nadpisywania.

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
najbliższym sąsiadem, widoczność nawigatora, włączanie podpowiedzi (patrz
niżej), a także zachowanie kółka myszy nad suwakami.

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
katalog docelowy, domyślny autor i prawa autorskie oraz sprawy ogólne: język
programu, otwieranie ostatniego folderu, zapis korekt w plikach XMP.

**O programie** — wersja, pełne dane sprzętu i sterownika, ścieżka pliku
ustawień, wersje bibliotek.

Ustawienia lądują w `%APPDATA%\Punctum\settings.json` (na Linuksie
`~/.config/Punctum/`). Zapis idzie przez plik tymczasowy, więc przerwanie nie
zostawia uszkodzonego pliku. Odczyt jest pobłażliwy: nieznane klucze są
pomijane, brakujące uzupełniane domyślnymi, wartości spoza zakresu przycinane —
uszkodzony plik nie zablokuje uruchomienia programu.

W tym samym pliku program trzyma rzeczy, których nie ustawia się w oknie
ustawień, tylko przy okazji pracy: filtr formatów w pasku miniatur, historię
katalogów, ostatnie opcje eksportu oraz rozmiary paneli i paska miniatur
(`left_panel_width`, `right_panel_width`, `filmstrip_height`). Rozmiary spoza
dopuszczalnych zakresów są przy odczycie przycinane, więc ręcznie popsuty plik
nie zostawi panelu, w którym nie mieści się żaden przycisk.

## Podpowiedzi

Każdy przycisk, suwak i pole w programie ma dymek: pogrubiony tytuł, opis
działania z praktyczną radą oraz szarą linię ze skrótem klawiszowym, gestem
(dwuklik zeruje suwak) albo formatem pola. Dymki wyłącza się w
`Ustawienia ▸ Podgląd ▸ Pokazuj podpowiedzi` — od razu, bez ponownego
uruchamiania (to filtr zdarzeń na całej aplikacji, nie kasowanie tekstów).

Kod zna tylko klucze (`suwak.shadows`, `eksport.podfolder`…). Teksty leżą
w `punctum/lang/podpowiedzi.pl.json` — polski jest bazowy i kompletny. Nowy
język to kopia tego pliku pod nazwą `podpowiedzi.<kod>.json`, bez zmian
w kodzie; brakujący wpis albo pole zastępuje polski, więc niepełny przekład
niczego nie psuje.

## Języki

Program jest po polsku i po angielsku. Język wybiera się w
`Ustawienia ▸ Eksport ▸ Ogólne ▸ Język`; zmiana działa po ponownym
uruchomieniu, bo napisy liczą się przy tworzeniu okien. Przy pierwszym
starcie program bierze język systemu, a gdy go nie zna — angielski.

Kod pisze napisy po polsku i przepuszcza je przez `t()`: `t("Zapisz")`.
Polski tekst jest zarazem kluczem, więc kod czyta się jak dotąd, a polski nie
potrzebuje osobnego pliku. Przekład leży w `punctum/lang/interfejs.<kod>.json`
(pary polski → przekład), podpowiedzi w `podpowiedzi.<kod>.json`. Kolejny język
to dwa pliki, bez zmian w kodzie — lista w ustawieniach bierze się z plików na
dysku.

- **Pola w zdaniu idą po nazwie**, a nie doklejaniem kawałków:
  `t("Wczytywanie {plik}…", plik=nazwa)`. W innym języku nazwa pliku albo
  liczba stoją często w innym miejscu zdania.
- **Liczba mnoga** ma własną funkcję: `mnoga(n, "{n} zdjęcie|{n} zdjęcia|{n} zdjęć")`.
  Polski ma trzy formy, angielski dwie; przekład podaje tyle, ile ma jego język.
- **Liczby** mają separator języka — „2,50” po polsku, „2.50” po angielsku,
  także w polach liczbowych.
- **Napisy samego Qt** (okno wyboru folderu, menu pola tekstowego) biorą
  standardowy przekład z biblioteki Qt.

`tools/test_przeklad.py` przegląda źródła i wyłapuje napis widoczny na
ekranie, który ominął `t()`, zdanie sklejane z kawałków, brak przekładu,
wpis, którego nikt nie używa, oraz niezgodne pola `{...}`.

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
nasycenie / jaskrawość         ← po krzywej, nie na danych liniowych
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
temperaturę dającą najbardziej zbliżone mnożniki. Program odniesienia dla tego samego
pliku pokazuje 7100 K.

Poprawność macierzy potwierdza `tools/verify_color.py` — mnożniki policzone
dla D65 muszą zgadzać się z `daylight_whitebalance` z pliku. Różnica: 0,006 %.

### Wyostrzanie

Maska wyostrzająca na samej luminancji (`core/sharpen.py`) — wyostrzanie
kanałów barwnych dawałoby kolorowe obwódki. *Szczegóły* miękko ograniczają
amplitudę maski (`tanh`): mocna krawędź, która daje aureolę, zostaje ścięta,
a drobna faktura przechodzi. *Maskowanie* ogranicza wyostrzanie do krawędzi,
zostawiając gładkie powierzchnie. Domyślne 40 / 1,0 / 25 / 0 dla RAW
dobrane pomiarem wobec eksportu z Lightrooma przy jego domyślnym
wyostrzaniu (stosunek energii pasm 0,7–1,5 px i 1,5–4 px, `tools/ostrosc_lab.py`):
nasze 40 daje 106 % wzorca — celowo odrobinę więcej detalu.

Shader nie wyostrza: tak jak odszumianie, liczy to procesor w przebiegu po
podglądzie i w ostrym fragmencie przy powiększeniu. Promień podawany jest
w pikselach zdjęcia; na podglądzie pomniejszonym tak, że promień spada
poniżej 0,5 piksela, wyostrzanie jest pomijane.

### Usuwanie szumu

Suwaki *Szum jasności* i *Szum koloru* nie ustawiają bezwzględnej siły
filtra, tylko siłę **względem szumu zmierzonego na samym zdjęciu**
(`core/denoise.py`). Dzięki temu „50" działa podobnie przy ISO 400 i ISO 6400,
w cieniach i w światłach, dla RAW-a i JPEG-a.

1. **Pomiar.** Filtr Immerkaera (zerowa odpowiedź na płaskie tło i gradienty)
   daje sigma szumu w przedziałach jasności co 8 poziomów.
2. **Wyrównanie szumu (VST).** Tablica `f(v) = ∫ 1/σ(v)` sprowadza szum do tej
   samej wielkości w każdej tonacji. Bez tego filtr dobrany do cieni rozmywał
   światła, a dobrany do świateł zostawiał szum w cieniach.
3. **Jasność.** Non-local means na danych po VST z `h` wyrażonym
   w wielokrotnościach zmierzonej sigmy (50 → 2σ). Szum jest **tłumiony,
   nie wygładzany**: część oryginału wraca jako drobne ziarno (30 → ok. 30 %,
   50 → 15 %). Lightroom przy 30–40 zostawia wyraźne ziarno i tak wygląda
   to lepiej niż gładki „wosk”; kontur odzyskuje wyostrzanie.
4. **Kolor.** Falki à trous na pięciu skalach, w połowie rozdzielczości
   (tak jak JPEG 4:2:0 i tak zapisuje chrominancję). Szum koloru siedzi
   zarówno w drobnych iskrach, jak i w większych plamach, więc tłumimy
   wszystkie skale.

Kalibracja na zdjęciu ISO 6400 wobec eksportów Lightrooma: jasność 50 daje
szum resztkowy zbliżony do jego 50, kolor 25 usuwa barwne iskry podobnie jak
jego domyślne 25. Dawny tor (NLM na obrazie po krzywej tonalnej, stałe `h`)
usuwał przy 50 ok. 20 % szumu, a Lightroom już przy 30 ok. 85 %.

Koszt przy eksporcie zdjęcia 20 MP: 3,6 s przy 50/25 (dawniej 5,1 s),
0,8 s przy samym kolorze. Podgląd dopasowany do okna: 0,2 s.

Znana granica: szum zależy nie tylko od jasności, ale i od barwy — w mocno
nasyconym niebieskim (kanał niebieski ma największe wzmocnienie) zostaje
więcej ziarna niż w szarościach, bo pomiar dzieli piksele tylko według
jasności.

**Odszumianie musi działać na pikselach natywnych, przed powiększeniem.**
Wcześniej tor liczył je po przeskalowaniu, więc przy 400 % ziarno było
czterokrotnie większe niż zasięg filtra i suwak nie robił nic widocznego.
Przy okazji poprawna kolejność jest tańsza — im większe powiększenie, tym
mniej natywnych pikseli trzeba przeliczyć. Na obrazie pomniejszonym pomiar
sam wykrywa mniejszy szum i filtr słabnie.

Narzędzia: `tools/szum_lab.py` (krzywe szumu na dwóch skalach, czasy
i mozaika wycinków 1:1 wobec wzorców z innego programu),
`tools/szum_demozaik.py` (wpływ algorytmu demozaikowania LibRaw — żaden
z siedmiu wariantów nie zmniejszał szumu, zostajemy przy AHD).

### Automatyczna korekcja

Automat nie zgaduje, CO jest na zdjęciu — opiera się na zasadach, które
w fotografii obowiązują niezależnie od tematu. Decyzje zapadają w przestrzeni
percepcyjnej L\*, gdzie „o pięć jednostek jaśniej" znaczy to samo w cieniach
i w światłach, więc progi ustawia się raz i działają na każdym kadrze.

Punkt wyjścia: **nie ma jednego dobrego histogramu**. Poprawnie naświetlona noc
jest zbita przy lewej krawędzi i to jest prawidłowe. Automat sprowadzający każdy
histogram do dzwonu pośrodku powtarza błąd światłomierza, który zamienia śnieg
w szarość.

Ekspozycja ma dwa warunki i decyduje ostrożniejszy:

- **treść** — mediana jasności ma trafić w strefę właściwą dla klucza sceny,
- **światła** — biel rozproszona nie może wyjść poza zakres; refleks wolno
  przepalić, biel z fakturą nie, bo tego się już nie odzyska.

Cel dla mediany przesuwa **klucz sceny** (udział kadru leżącego ponad 2,5 działki
poniżej *własnej* bieli zdjęcia — miara opisuje układ sceny, a nie błąd
naświetlenia) oraz **rozpiętość** (im dłuższa skala, tym niżej musi leżeć środek,
żeby światła zmieściły się pod ramieniem krzywej). Scena bez rozpiętości — karta
szarości, jednolita ściana, mgła — nie ma klucza, więc oba przesunięcia gasną
proporcjonalnie do pewności oceny.

Biel rozproszoną wyznaczamy z pominięciem refleksów: gdy szczyt histogramu
odstaje od 99. percentyla o ponad 1,5 działki, punkt bieli bierzemy niżej.
Inaczej jedna latarnia w kadrze zaciemniałaby całe zdjęcie.

Sprawdzian to `tools/test_auto_zasady.py` — 21 przypadków na obrazach o znanych
właściwościach: karta szarości i jej wersje prze- i niedoświetlone, klin
stopniowy 8 EV i 2 EV, syntetyczna noc i śnieg, odporność na refleks.
Najważniejszy jest ostatni: scena nocna zestawiona ze zwykłym zdjęciem
niedoświetlonym o 4 EV. Mediany różnią się o niecałą jednostkę L\*, a korekty
o dwie działki — bo o decyzji nie stanowi jasność mediany, tylko układ sceny.

Porównanie z komercyjnym punktem odniesienia na pliku referencyjnym
(kalibracja metody, nie cel do naśladowania):

| parametr | Punctum | odniesienie |
|---|---:|---:|
| ekspozycja | +1,22 | +1,00 |
| kontrast | +7 | +6 |
| podświetlenia | −48 | −47 |
| cienie | +57 | +57 |
| biele | 0 | +9 |
| czernie | −3 | −8 |

Balansu bieli automat celowo nie rusza — aparat zna warunki oświetlenia lepiej
niż histogram, a „poprawiony" zachód słońca traci sens.

Przy okazji tych prac wyszła wada suwaka **bieli**: był zwykłym mnożnikiem
całego obrazu, czyli drugą ekspozycją pod inną nazwą, i nie potrafił zrobić
tego, po co istnieje — postawić punktu bieli bez rozjaśniania całości. Teraz
działa od ok. 1,4 działki ponad szarością, wyżej niż maska świateł, więc oba
suwaki nie powielają swojej roli.

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

### Układ okna

Kilka decyzji, które nie wynikają z samego wyglądu:

- **Panele stoją na splitterach z jawnymi granicami szerokości.** Jawne
  minimum i maksimum mają w Qt pierwszeństwo przed tym, o co prosi zawartość.
  Bez tego rozwinięcie metadanych poszerzało kolumnę, bo formularz chciał
  więcej miejsca niż suwaki, a razem z kolumną przeskakiwał podgląd zdjęcia.
- **Zapamiętane rozmiary nakładamy dopiero po pokazaniu okna.** Przed
  pokazaniem splitter nie zna swojej prawdziwej szerokości i przy pierwszym
  ułożeniu rozdzieliłby różnicę po swojemu; okno otwierane jako
  zmaksymalizowane dostaje ostateczny rozmiar chwilę po `showEvent`.
- **Suwak powiększenia niczego nie liczy sam.** Widok zgłasza każdą zmianę
  (kółko, przycisk, dopasowanie po zmianie rozmiaru okna), a panel tylko ją
  pokazuje — jeden tor synchronizacji zamiast trzech. Ruch suwaka skaluje
  obraz względem bieżącego stanu, więc środek widoku zostaje na miejscu.
- **Kafelki miniatur liczone są z wysokości całego paska**, nie z obszaru
  widoku. Obszar widoku zmienia się, gdy pojawia się poziomy pasek
  przewijania, a zmiana kafelków potrafi ten pasek schować — i tak w kółko.
- **Mapa nadal powstaje przed pokazaniem okna** (patrz wyżej) — przebudowa
  układu Edycji tego nie zmienia.

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
    jpeg_loader.py   dekodowanie JPEG, zdjęcie krzywej sRGB
    loader.py        wspólne wejście dla obu formatów, filtr formatów
    pipeline.py      tor tonalny, geometria
    denoise.py       usuwanie szumu dopasowane do zmierzonego szumu
    sharpen.py       wyostrzanie (maska wyostrzająca na luminancji)
    auto.py          automatyczny dobór parametrów
    metadata.py      odczyt EXIF (z obsługą pól własnych Panasonica)
    exif_edit.py     podgląd wszystkich tagów i zapis edytowalnych pól
    sidecar.py       zapis i odczyt korekt obok zdjęcia (XMP)
    export.py        zapis JPEG / PNG / TIFF
    settings.py      ustawienia programu: odczyt, zapis, walidacja
    hardware.py      wykrywanie procesora i karty graficznej
punctum/app/
    main_window.py   złożenie całości
    image_view.py    płótno, zoom, warstwa detalu, kadrowanie
    edit_panel.py    histogram, dane zdjęcia, kadrowanie, suwaki
    sliders.py       suwaki, w tym te z gradientem barwnym
    navigator.py     miniatura z ramką powiększenia
    zoom_panel.py    suwak i przyciski powiększenia w lewym panelu
    filmstrip.py     pasek miniatur
    markers.py       znaczniki przy nazwach zdjęć, wspólne dla obu list
    exif_panel.py    panel metadanych: formularz, podgląd tagów, zapis
    map_view.py      zakładka mapy: lista zdjęć, most do strony, przypisywanie
    map_page.py      strona mapy (Leaflet) jako HTML i JavaScript
    workers.py       zadania w tle
    podpowiedzi.py   dymki: klucze, składanie tekstu, języki, wyłącznik
    jezyk.py         włączenie języka w całej aplikacji przy starcie
punctum/przeklad.py  t(), mnoga(), liczba(), lista języków
punctum/lang/        przekład interfejsu i teksty podpowiedzi, pliki na język
tools/               narzędzia diagnostyczne, testy i CLI
```

## Testy

```powershell
tools\testy.bat --szybkie                 # same testy bez interfejsu, ~5 s
tools\testy.bat "C:\Zdjęcia\Wycieczka"    # cała seria, ~300 sprawdzeń, ~60 s
tools\testy.bat "C:\Zdjęcia\Wycieczka" --pelny   # z pełnymi tabelami wyników
```

Domyślnie każdy test wypisuje tylko to, co nie przeszło, i jedną linię
podsumowania — kod wyjścia równa się liczbie błędów, więc seria przerywa po
pierwszym nieudanym teście zamiast mielić resztę.

Testy bez interfejsu (tor tonalny, automat, JPEG, sidecary, metadane) idą zawsze
i nie potrzebują niczego poza repozytorium. Testy z interfejsem otwierają
prawdziwe okno, więc potrzebują katalogu ze zdjęciami — wystarczy jeden plik RAW
i dwa JPEG-i, a które to będą, program dobiera sam. Katalog można podać raz na
stałe zmienną `PUNCTUM_TESTY`; bez niego seria po prostu pomija tę część.

| Test | Co pilnuje |
|---|---|
| `test_geo.py` | współrzędne w sidecarze bez straty dokładności, GPS w eksporcie |
| `test_sidecar.py` | komplet suwaków zapisany i wczytany daje dokładnie te same wartości |
| `test_auto_zasady.py` | automat tonalny na scenach o z góry znanych cechach |
| `test_jpeg.py` | JPEG przepuszczony przez tor liniowy bez korekt wychodzi taki sam |
| `test_exif.py` | zapis do oryginału nie niszczy obrazu, reszty metadanych ani daty pliku |
| `test_przeklad.py` | każdy napis na ekranie przechodzi przez przekład, komplet angielskiego interfejsu i podpowiedzi, zgodne pola `{...}`, liczba mnoga, separator dziesiętny |
| `test_podpowiedzi.py` | każdy klucz z kodu ma tekst, brak tekstów nieużywanych, język z niepełnym przekładem uzupełniany polskim, jakość odszumiania podglądu z ustawień |
| `test_trwalosc_gui.py` | poprawki przeżywają przejście dalej i ponowne uruchomienie |
| `test_mapa_gui.py` | przypisanie punktu na mapie i jego trwałość |
| `test_jpeg_gui.py` | mieszany katalog: filtr formatów, opis balansu bieli |
| `test_znaczniki_gui.py` | znaczniki na listach i panel metadanych w obu zakładkach |
| `test_uklad_gui.py` | układ okna: widoczność elementów przy maksymalizacji, szerokości przy rozwinięciu metadanych, suwak powiększenia, przeciąganie i zapamiętywanie rozmiarów |
| `test_podpowiedzi_gui.py` | żaden przycisk, suwak ani pole w oknie głównym, Ustawieniach i eksporcie bez podpowiedzi; wyłącznik dymków |

Test układu zapisuje też zrzut okna (`punctum-uklad.png` w katalogu
tymczasowym) — tak sprawdzamy wygląd po zmianach bez proszenia o zrzuty.

Testy z interfejsem czekają na **warunek**, nie na ustalony czas — obciążona
maszyna potrafiła kiedyś nie zdążyć wczytać zdjęcia w wyznaczonych sekundach
i seria wywracała się przy poprawnym kodzie. Z tego samego powodu etapy testu
idą łańcuchem: kolejny rusza, gdy poprzedni wróci, a nie o wyznaczonej
sekundzie. Sama ta zmiana skróciła serię ze 105 do 37 sekund.

## Czego jeszcze nie ma

- Dopasowania lokalizacji do śladu GPS (pliki GPX) i grupowania po dniach —
  na razie współrzędne nadaje się zaznaczeniu zdjęć.
- Presetów i kopiowania ustawień między zdjęciami.
- Szybkiego eksportu wsadowego — działa, ale liczy sekwencyjnie na procesorze.
- Integracji z Google Photos.
- Podzielonego podglądu przed/po (linia podziału albo dwa widoki obok siebie) —
  na razie *Przed / po* działa przez przytrzymanie przycisku.
- Ikon narzędzi w jednym stylu — przyciski obrotu to na razie znaki; ikonę ma
  tylko kadrowanie.
