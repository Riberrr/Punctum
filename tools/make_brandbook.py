"""Brandbook Punctum: docs/brandbook.html z grafik w punctum/assets.

Strona odwoluje sie do plikow z assets (sciezki wzgledne), wiec pokazuje
zawsze to, co naprawde jest w programie - po zmianie w make_assets.py
wystarczy puscic ten skrypt ponownie. Podglad ekranu startowego to zrzut
prawdziwego okna (EkranStartowy), nie makieta.

Uzycie:  .venv\\Scripts\\python.exe tools\\make_brandbook.py
"""

from __future__ import annotations

import html
import os
import sys

KATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KATALOG)
DOCS = os.path.join(KATALOG, "docs")
os.makedirs(os.path.join(DOCS, "img"), exist_ok=True)

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from punctum import __version__, przeklad  # noqa: E402
from punctum.app import ekran_startowy as es  # noqa: E402

# Zrzut ekranu startowego w obu jezykach, w skali 2x - ostry na ekranach
# o duzej gestosci i w dokumencie powiekszonym w przegladarce.
for jezyk, haslo in (("pl", 0), ("en", 0)):
    przeklad.ustaw_jezyk(jezyk)
    ekran = es.EkranStartowy(haslo=es.HASLA[haslo])
    ekran.stan = przeklad.t("Wczytywanie miniatur… {n} z {m}", n=9, m=16)
    ekran.postep = 0.78
    ekran.show()
    app.processEvents()
    ekran.grab().save(os.path.join(DOCS, "img", f"ekran-startowy-{jezyk}.png"))
    ekran.close()

hasla = []
for h in es.HASLA:
    przeklad.ustaw_jezyk("en")
    hasla.append((h, przeklad.t(h)))
przeklad.ustaw_jezyk("pl")

KOLORY = [
    ("Fiolet Punctum", "#6c63ff", "Kafel ikony programu, pasek postępu, zaznaczenie. Kolor marki."),
    ("Fiolet jasny", "#7b73ff", "Kropka znaku na ciemnym tle, punkt w ikonie geotagu."),
    ("Lawenda", "#b9b3ff", "Akcenty tekstu i obwódek w interfejsie."),
    ("Biel papieru", "#e8e8ea", "Litera P, nazwa programu, główny tekst."),
    ("Srebro ikon", "#c8c8cc", "Kreska wszystkich ikon narzędzi."),
    ("Szarość opisu", "#8a8a90", "Tekst drugorzędny, podpisy, stan ładowania."),
    ("Linia", "#3c3c42", "Obwódki, separatory, obrys ciemnego kafla."),
    ("Kafel", "#26262a", "Tło znaku w wariancie ciemnym."),
    ("Grafit", "#1e1e20", "Tło okna programu."),
    ("Głębia", "#0f0f12", "Najciemniejsze partie ekranu startowego."),
]

IKONY = [
    ("crop", "Kadrowanie"), ("rotate-left", "Obrót w lewo"), ("rotate-180", "Obrót o 180°"),
    ("rotate-right", "Obrót w prawo"), ("before-after", "Przed / po"), ("fit", "Dopasuj"),
    ("actual-size", "100 %"), ("export", "Eksport"), ("undo", "Cofnij"), ("redo", "Ponów"),
    ("lock", "Kłódka"), ("unlock", "Kłódka otwarta"),
    ("pin-top", "Przypnij u góry"), ("pin-bottom", "Przypnij u dołu"), ("unpin", "Odepnij"),
    ("filter", "Filtr"),
    ("select-all", "Zaznacz wszystkie"), ("geotag", "Z geotagiem"), ("no-geotag", "Bez geotagu"),
    ("geotag-reset", "Przywróć geotag"),
]

A = "../punctum/assets"


def e(tekst: str) -> str:
    return html.escape(tekst, quote=True)


kolory_html = "".join(
    f'<div class="kolor"><div class="probka" style="background:{k}"></div>'
    f'<b>{e(n)}</b><code>{k}</code><span>{e(o)}</span></div>'
    for n, k, o in KOLORY
)
ikony_html = "".join(
    f'<figure><div class="przyc"><img src="{A}/icons/{p}.svg" width="24" height="24" alt=""></div>'
    f'<img src="{A}/icons/{p}.svg" width="48" height="48" alt=""><figcaption>{e(n)}<code>{p}</code></figcaption></figure>'
    for p, n in IKONY
)
hasla_html = "".join(f"<tr><td>{e(pl)}</td><td>{e(en)}</td></tr>" for pl, en in hasla)
rozmiary_html = "".join(
    f'<figure><img src="{A}/logo-fiolet.svg" width="{r}" height="{r}" alt=""><figcaption>{r} px</figcaption></figure>'
    for r in (256, 64, 48, 32, 24, 16)
)

STRONA = f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Punctum — brandbook</title>
<style>
:root{{--tlo:#141416;--karta:#1e1e20;--linia:#3c3c42;--tekst:#e8e8ea;--opis:#8a8a90;--fiolet:#6c63ff;--fj:#7b73ff}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--tlo);color:var(--tekst);font:15px/1.6 "Segoe UI",system-ui,sans-serif}}
main{{max-width:1040px;margin:0 auto;padding:48px 20px 80px}}
h1{{font:600 44px/1.1 "Segoe UI Semibold","Segoe UI",sans-serif;margin:0;letter-spacing:-.5px}}
h1 i,.slowo i{{font-style:normal;color:var(--fj)}}
h2{{font:600 24px/1.2 "Segoe UI Semibold","Segoe UI",sans-serif;margin:64px 0 8px;padding-top:24px;border-top:1px solid var(--linia)}}
h2 small{{color:var(--fj);font-size:14px;margin-right:10px}}
h3{{font-size:16px;margin:28px 0 6px}}
p,li{{color:#c4c4ca;max-width:760px}}
code{{font:12.5px Consolas,monospace;color:#b9b3ff}}
.okladka{{display:flex;gap:28px;align-items:center;margin-bottom:12px}}
.lead{{font-size:18px;color:#c4c4ca;max-width:720px}}
.spis{{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;margin-top:24px}}
.spis a{{color:var(--opis);text-decoration:none}}.spis a:hover{{color:var(--tekst)}}
.siatka{{display:grid;gap:14px}}
.dwa{{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}}
.plansza{{border-radius:10px;padding:32px;display:flex;align-items:center;justify-content:center;gap:24px;min-height:220px;border:1px solid var(--linia)}}
.ciemna{{background:#1e1e20}}.jasna{{background:#f3f3f5;color:#1e1e20}}.fioletowa{{background:#6c63ff}}
.podpis{{font-size:13px;color:var(--opis);margin-top:6px}}
.slowo{{font:600 46px/1 "Segoe UI Semibold","Segoe UI",sans-serif;letter-spacing:-.5px}}
.rozmiary{{display:flex;align-items:flex-end;gap:22px;flex-wrap:wrap}}
figure{{margin:0;text-align:center}}figcaption{{font-size:12px;color:var(--opis);margin-top:6px}}
figcaption code{{display:block;font-size:11px}}
.konstrukcja{{position:relative;width:256px;height:256px}}
.konstrukcja svg{{position:absolute;inset:0}}
.nie{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}}
.nie figure{{background:#1e1e20;border:1px solid var(--linia);border-radius:8px;padding:18px 8px 10px}}
.nie figure img{{display:block;margin:0 auto 6px}}
.nie figcaption::before{{content:"✕ ";color:#ff6b6b}}
.kolory{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}}
.kolor{{background:var(--karta);border:1px solid var(--linia);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:2px;font-size:13px}}
.kolor span{{color:var(--opis);font-size:12px}}
.probka{{height:64px;border-radius:5px;margin-bottom:6px;border:1px solid rgba(255,255,255,.08)}}
.ikony{{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:10px}}
.ikony figure{{background:var(--karta);border:1px solid var(--linia);border-radius:8px;padding:12px 6px}}
.ikony figure>img{{margin-left:10px;vertical-align:middle}}
.przyc{{display:inline-flex;background:#2a2a2e;border:1px solid #45454d;border-radius:4px;padding:4px;vertical-align:middle}}
table{{border-collapse:collapse;width:100%;max-width:760px;font-size:14px}}
td,th{{text-align:left;padding:7px 10px;border-bottom:1px solid var(--linia)}}
th{{color:var(--opis);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.06em}}
.zrzut{{width:100%;max-width:640px;border-radius:4px;box-shadow:0 14px 40px rgba(0,0,0,.55);display:block}}
.tak li::marker{{color:#6fd49a}}.nie-lista li::marker{{color:#ff6b6b}}
footer{{margin-top:72px;color:var(--opis);font-size:12px}}
</style></head><body><main>

<div class="okladka"><img src="{A}/logo.svg" width="96" height="96" alt="">
<div><h1>Punctum<i>.</i></h1><div class="podpis">Brandbook · wersja programu {e(__version__)}</div></div></div>
<p class="lead">Zasady znaku, kolorów, ikon i tonu wypowiedzi programu Punctum. Wszystkie grafiki
z tej strony to pliki, których program naprawdę używa — generuje je <code>tools/make_assets.py</code>.</p>
<nav class="spis"><a href="#idea">1 Idea</a><a href="#znak">2 Znak</a><a href="#konstrukcja">3 Konstrukcja</a>
<a href="#bledy">4 Czego unikać</a><a href="#kolory">5 Kolory</a><a href="#typografia">6 Typografia</a>
<a href="#glos">7 Głos i hasła</a><a href="#ikony">8 Ikony</a><a href="#ekran">9 Ekran startowy</a><a href="#pliki">10 Pliki</a></nav>

<h2 id="idea"><small>01</small>Idea</h2>
<p><b>Punctum</b> to pojęcie Rolanda Barthes’a ze „Światła obrazu”: ten jeden szczegół fotografii,
który kłuje patrzącego — przypadkowy, niedający się zaplanować. Jego przeciwieństwem jest <i>studium</i>,
czyli to, co na zdjęciu rozpoznajemy rozumem. Po łacinie <i>punctum</i> to też po prostu <b>kropka</b>.</p>
<p>Z tego bierze się cała identyfikacja: <b>litera P i jedna kropka</b>. Kropka jest jedynym elementem
w kolorze marki — tak jak punctum jest jednym miejscem, które przyciąga wzrok. W interfejsie
fiolet oznacza to samo: to, co wyróżnione, aktywne albo ważne teraz.</p>

<h2 id="znak"><small>02</small>Znak</h2>
<p>Dwa warianty tego samego znaku. Różnią się tylko kolorem kafla — kształt i proporcje są identyczne.</p>
<div class="siatka dwa">
<div><div class="plansza ciemna"><img src="{A}/logo.svg" width="150" height="150" alt=""></div>
<div class="podpis"><b>Ciemny</b> · <code>logo.svg</code> — w programie: okno „O programie”, ekran startowy, README.
Na ciemnym tle kafel ma obrys <code>#3a3a42</code>, żeby nie zlał się z tłem.</div></div>
<div><div class="plansza jasna"><img src="{A}/logo-fiolet.svg" width="150" height="150" alt=""></div>
<div class="podpis"><b>Fioletowy</b> · <code>logo-fiolet.svg</code>, <code>punctum.ico</code> — ikona okna,
paska zadań i skrótów. Czytelny na jasnym i ciemnym pasku zadań, także przy 16 px.</div></div>
</div>
<h3>Znak ze słowem</h3>
<div class="siatka dwa">
<div class="plansza ciemna"><img src="{A}/logo.svg" width="64" height="64" alt=""><span class="slowo">Punctum<i>.</i></span></div>
<div class="plansza jasna"><img src="{A}/logo-fiolet.svg" width="64" height="64" alt=""><span class="slowo" style="color:#1e1e20">Punctum<i style="color:#6c63ff">.</i></span></div>
</div>
<p class="podpis">Nazwa zawsze z kropką w kolorze marki. Odstęp znak–nazwa: ¼ szerokości znaku.
Wysokość wersalików nazwy ≈ 0,5 wysokości znaku.</p>

<h2 id="konstrukcja"><small>03</small>Konstrukcja i rozmiary</h2>
<div class="siatka dwa"><div class="plansza ciemna"><div class="konstrukcja">
<img src="{A}/logo.svg" width="256" height="256" alt="">
<svg viewBox="0 0 256 256" width="256" height="256"><g fill="none" stroke="#ff9a6a" stroke-width="1" stroke-dasharray="3 3">
<rect x="8" y="8" width="240" height="240" rx="54"/><line x1="0" y1="225" x2="256" y2="225"/><line x1="62" y1="0" x2="62" y2="256"/>
<circle cx="191.2" cy="200" r="25"/></g></svg></div></div>
<div><ul>
<li>Siatka 256 × 256, kafel 240 × 240 z promieniem narożnika 54.</li>
<li>Litera P: kreska 34, zaokrąglone zakończenia i narożniki. Brzuszek to półokrąg o promieniu 48.</li>
<li>Kropka: średnica 50 (≈ 1,5 grubości kreski), <b>stoi na linii pisma</b> — dolna krawędź kropki
równa z końcem trzonu, jak prawdziwa kropka po literze.</li>
<li>Grupa P + kropka jest wyśrodkowana optycznie, nie geometrycznie — przesunięcie (−10, −4).</li>
<li><b>Pole ochronne</b>: wokół znaku wolne miejsce co najmniej średnicy kropki.</li>
<li><b>Najmniejszy rozmiar</b>: 16 px — i to jest główne kryterium kształtu. Pliki .ico mają każdy rozmiar
rastrowany osobno z wektora.</li></ul></div></div>
<div class="plansza ciemna rozmiary" style="justify-content:flex-start;min-height:0;margin-top:14px">{rozmiary_html}</div>

<h2 id="bledy"><small>04</small>Czego unikać</h2>
<div class="nie">
<figure><img src="{A}/logo.svg" width="72" height="72" style="transform:scaleX(1.35)" alt=""><figcaption>Rozciągania</figcaption></figure>
<figure><img src="{A}/logo.svg" width="72" height="72" style="transform:rotate(-14deg)" alt=""><figcaption>Obracania</figcaption></figure>
<figure><img src="{A}/logo.svg" width="72" height="72" style="filter:hue-rotate(150deg)" alt=""><figcaption>Innych kolorów</figcaption></figure>
<figure><img src="{A}/logo.svg" width="72" height="72" style="filter:drop-shadow(6px 8px 4px #000) blur(.4px)" alt=""><figcaption>Cieni i efektów</figcaption></figure>
<figure style="background:#6c63ff"><img src="{A}/logo-fiolet.svg" width="72" height="72" alt=""><figcaption style="color:#fff">Fioletu na fiolecie</figcaption></figure>
<figure style="background:#e8e8ea"><img src="{A}/logo-512.png" width="72" height="72" style="opacity:.35" alt=""><figcaption style="color:#555">Półprzezroczystości</figcaption></figure>
</div>
<ul class="nie-lista"><li>Nie przestawiamy kropki (nad literę, do środka brzuszka) i nie zmieniamy jej koloru na biały na ciemnym kaflu.</li>
<li>Nie składamy nazwy innym krojem ani bez kropki; nie piszemy „PUNCTUM” wersalikami.</li>
<li>Nie używamy migawki ani obiektywu jako symbolu programu.</li></ul>

<h2 id="kolory"><small>05</small>Kolory</h2>
<p>Paleta jest ciemna i neutralna, bo zdjęcia ogląda się na szarym tle bez zafarbu. Jedynym kolorem jest
fiolet — używany oszczędnie, jak punctum: jedno miejsce na raz.</p>
<div class="kolory">{kolory_html}</div>

<h2 id="typografia"><small>06</small>Typografia</h2>
<p><b>Segoe UI</b> — krój systemowy Windows, ten sam w nazwie, interfejsie i dokumentach. Nie dołączamy
własnych fontów: program ma wyglądać jak część systemu, a zdjęcie ma być najciekawszą rzeczą na ekranie.</p>
<table><tr><th>Rola</th><th>Krój</th><th>Rozmiar</th></tr>
<tr><td>Nazwa „Punctum.”</td><td>Segoe UI Semibold, światło −0,5 px</td><td>40 px (ekran startowy), 46–58 px (dokumenty)</td></tr>
<tr><td>Hasło</td><td>Segoe UI</td><td>13 px</td></tr>
<tr><td>Interfejs</td><td>Segoe UI</td><td>systemowy (9 pt)</td></tr>
<tr><td>Stan ładowania, wersja</td><td>Segoe UI</td><td>11–12 px, szarość opisu</td></tr></table>

<h2 id="glos"><small>07</small>Głos i hasła</h2>
<ul class="tak"><li>Krótko, zdanie z kropką na końcu — kropka to też punctum.</li>
<li>Mówimy o zdjęciu i patrzeniu, nie o funkcjach programu. „Nieniszczący edytor RAW” to opis
do okna „O programie”, nie hasło.</li>
<li>Do fotografa na „ty”, bez wykrzykników i bez żargonu marketingowego.</li>
<li>Każde hasło ma odpowiednik angielski o tym samym sensie, nie dosłowny przekład.</li></ul>
<p>Ekran startowy losuje hasło przy każdym uruchomieniu (<code>HASLA</code> w <code>punctum/app/ekran_startowy.py</code>,
przekład w <code>punctum/lang/interfejs.en.json</code>):</p>
<table><tr><th>Polski</th><th>English</th></tr>{hasla_html}</table>

<h2 id="ikony"><small>08</small>Ikony narzędzi</h2>
<p>Siatka 24 px, kreska 2 px, zaokrąglone końce i narożniki, kolor <code>#c8c8cc</code>. Bez napisów — nie zależą
od języka; nazwę i skrót podaje dymek. Fiolet tylko tam, gdzie oznacza punkt (geotag) albo stan aktywny.
Wersje wyszarzone tworzy Qt. W kodzie: <code>style.ikona("nazwa")</code>.</p>
<div class="ikony">{ikony_html}</div>

<h2 id="ekran"><small>09</small>Ekran startowy</h2>
<div class="siatka dwa"><img class="zrzut" src="img/ekran-startowy-pl.png" alt="Ekran startowy po polsku">
<img class="zrzut" src="img/ekran-startowy-en.png" alt="Ekran startowy po angielsku"></div>
<ul><li>640 × 380 px, tło w wersji 1× i 2× (<code>ekran-startowy.png</code>, <code>@2x</code>).</li>
<li>Rozmyte światła i <b>jeden ostry punkt</b> — idea punctum wprost: wszystko miękkie, jedno miejsce ostre.</li>
<li>Tło nie ma tekstu. Nazwę, hasło, wersję i stan ładowania rysuje program w języku interfejsu.</li>
<li>Znak 64 px w lewym dolnym rogu, pod nim hasło; na samym dole stan i pasek postępu 3 px w fiolecie marki.</li>
<li>Ekran schodzi, gdy okno jest gotowe do pracy: pierwsze zdjęcie pokazane i widoczne miniatury wczytane
— i zostaje jeszcze 2,5 s, żeby start nie kończył się szarpnięciem (limit 30 s).</li></ul>

<h2 id="pliki"><small>10</small>Pliki</h2>
<table><tr><th>Plik</th><th>Do czego</th></tr>
<tr><td><code>punctum/assets/logo.svg</code></td><td>znak ciemny (źródło wektorowe)</td></tr>
<tr><td><code>punctum/assets/logo-fiolet.svg</code></td><td>znak fioletowy (źródło wektorowe)</td></tr>
<tr><td><code>punctum/assets/punctum.ico</code></td><td>ikona okna, skrótów i przyszłego .exe — 16, 24, 32, 48, 64, 128, 256 px</td></tr>
<tr><td><code>punctum/assets/logo-512.png</code></td><td>README, dokumenty</td></tr>
<tr><td><code>punctum/assets/icons/*.svg</code></td><td>17 ikon narzędzi</td></tr>
<tr><td><code>punctum/assets/ekran-startowy*.png</code></td><td>tło ekranu startowego</td></tr>
<tr><td><code>tools/make_assets.py</code></td><td>generuje wszystkie powyższe</td></tr>
<tr><td><code>tools/make_brandbook.py</code></td><td>generuje tę stronę i zrzuty ekranu startowego</td></tr>
<tr><td><code>tools/utworz_skroty.py</code></td><td>skrót z ikoną w katalogu programu (opcjonalnie pulpit i menu Start)</td></tr></table>

<footer>Punctum. — brandbook generowany z plików programu. Zmiana znaku, kolorów albo ikon: najpierw
<code>tools/make_assets.py</code>, potem <code>tools/make_brandbook.py</code>.</footer>
</main></body></html>
"""

with open(os.path.join(DOCS, "brandbook.html"), "w", encoding="utf-8", newline="\n") as plik:
    plik.write(STRONA)
print(f"zapisano {os.path.join(DOCS, 'brandbook.html')}")
