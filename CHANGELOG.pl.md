# Historia zmian

Istotne zmiany w Punctum, od najnowszych. Numer wersji ma postać
GŁÓWNA.POBOCZNA.POPRAWKA: poprawki podbijają ostatnią liczbę, nowe funkcje
środkową. English version: [CHANGELOG.md](CHANGELOG.md).

## 0.12.0 — 2026-10-08

### Nowe

- Wstępna wersja na Maca z Apple Silicon (macOS 12 i nowsze): obraz `.dmg`
  na stronie wydań. Zdjęcia otwiera się też z Findera („Otwórz za pomocą”)
  i przez upuszczenie na ikonę Punctum w Docku.

## 0.11.0 — 2026-10-05

### Nowe

- Po zmianie języka w Ustawieniach ▸ Ogólne pojawia się ostrzeżenie
  i link "Zapisz i uruchom ponownie": program zapisuje pracę, otwiera
  się od nowa w wybranym języku - z tym samym zdjęciem i z oknem
  ustawień w tym samym miejscu.

### Zmienione

- Dwuklik zdjęcia przy otwartym Punctum otwiera je w działającym oknie
  (i wyciąga je na wierzch) zamiast uruchamiać drugi program.

## 0.10.1 — 2026-10-04

### Poprawione

- Pierwsze wydanie z instalatorem na stronie wydań GitHuba — budowa
  wersji 0.10.0 przerwała się przed powstaniem instalatora; zawartość
  programu jest ta sama.

## 0.10.0 — 2026-10-04

### Nowe

- Pomoc ▸ „Co nowego” — historia zmian w programie. Po aktualizacji okno
  pokazuje się samo, jeden raz.
- Ustawienia ▸ O programie ▸ „Licencje zewnętrzne” — biblioteki innych
  autorów dołączone do programu i pełne teksty ich licencji; ich spis
  pokazuje też instalator.
- Instalator do pobrania ze strony wydań na GitHubie, z sumą kontrolną
  SHA-256.

### Poprawione

- Płynniejszy podgląd przy przesuwaniu suwaków: zdjęcie nie miga już
  poprzednim ustawieniem ani rozmytym obrazem, także w powiększeniu,
  a kolory nie zmieniają się chwilę po zatrzymaniu suwaka — odszumianie
  koloru liczy teraz karta graficzna przy każdym ruchu.
- Suwaki szumu jasności i wyostrzania pokazują efekt już w trakcie
  przesuwania, a nie dopiero po puszczeniu.

## 0.9.0 — 2026-09-29

Pierwsze wydanie.

### Nowe

- Obróbka zdjęć RAW (RW2, CR2, CR3, NEF, ARW, DNG) i JPEG w jednym torze,
  z podglądem liczonym na karcie graficznej.
- Korekty światła i koloru, balans bieli, automatyczna korekta tonalna.
- Kadrowanie i obrót, także o dowolny kąt.
- Usuwanie szumu dopasowane do zmierzonego szumu zdjęcia, z podglądem;
  wyostrzanie.
- Monochrom z mieszaniem barw i presety nastaw.
- Porównanie przed / po: obok siebie (Y) albo z linią podziału (Shift+Y).
- Cofnij / ponów w edycji i na mapie.
- Praca nieniszcząca: nastawy zapisywane obok zdjęcia w pliku XMP, oryginał
  zostaje nietknięty.
- Eksport w tle z oknem opcji: autor, prawa autorskie, tagi, dane aparatu
  i znak wodny.
- Mapa i geotagowanie: ślad GPX, grupowanie zdjęć po dniach, schowek
  współrzędnych, nazwa miejsca.
- Panel metadanych i znaczniki stanu na liście zdjęć.
- Panele z sekcjami: zwijanie, zmiana kolejności, przypinanie i ukrywanie;
  skala całego interfejsu.
- Interfejs po polsku i po angielsku, podpowiedź przy każdym przycisku,
  suwaku i polu.
- Sterowanie przez agentów AI (serwer MCP).
- Instalator dla Windows: skojarzenia plików RAW i otwieranie zdjęcia
  prosto z Eksploratora.
