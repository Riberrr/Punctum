"""Automatyczny dobor parametrow tonalnych.

Automat nie probuje zgadnac, CO jest na zdjeciu. Opiera sie na zasadach, ktore
w fotografii obowiazuja niezaleznie od tematu: systemie stref, zakotwiczeniu
krancow histogramu, ksztalcie krzywej charakterystycznej filmu i prawach
widzenia barwnego.

Dwie rzeczy warto wiedziec, zanim sie tu cokolwiek zmieni.

**Nie ma jednego dobrego histogramu.** Poprawnie naswietlone zdjecie nocne ma
histogram zbity przy lewej krawedzi, portret w plenerze przy prawej i oba sa
prawidlowe. Automat, ktory kazdy histogram sprowadza do dzwonu posrodku, robi
dokladnie ten sam blad, co swiatlomierz zamieniajacy snieg w szarosc.

**Analiza idzie w L\\*, nie w wartosciach liniowych.** W przestrzeni percepcyjnej
"o piec jednostek jasniej" znaczy to samo w cieniach i w swiatlach, wiec progi
daja sie ustawic raz i dzialaja na kazdym zdjeciu. Sam obraz liczymy oczywiscie
dalej liniowo - L\\* sluzy wylacznie do podejmowania decyzji.

Kalibracja: progi dobrano tak, zeby wynik pokrywal sie z przyciskiem
"Automatycznie" w Lightroomie na zdjeciach referencyjnych, a jednoczesnie
przechodzil testy na obrazach o znanych wlasciwosciach (karta szarosci, klin
stopniowy, sceny skrajnych kluczy) - patrz tools/test_auto_zasady.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .params import EditParams
from .pipeline import LUMA, _smoothstep, apply_white_balance, camera_to_srgb
from .raw_loader import RawImage

ANALYSIS_SIZE = 640  # analiza na pomniejszonym obrazie - wynik ten sam, czas znikomy

# --- progi wyrazone w systemie stref ------------------------------------
# Strefa V to szarosc 18 %, czyli L* 50. Jasna skora ma ladowac w strefie VI,
# ciemna zielen w III-IV, biel z faktura w VIII.
MID_GREY_L = 50.0
MID_GREY_LINEAR = 0.18  # ten sam punkt zaczepienia, co maski w torze tonalnym
DIFFUSE_WHITE_L = 96.0  # gdzie ma wyladowac biel rozproszona (nie refleks)
PEAK_WHITE_L = 99.0  # gdzie ma wyladowac sam szczyt histogramu
DEEP_BLACK_L = 3.0  # gdzie ma wyladowac najciemniejszy istotny piksel
SHADOW_FLOOR_L = 18.0  # ponizej tego cienie uznajemy za zalepione

# Tyle kadru lezy ponizej progu ciemnosci w scenie o zrownowazonym kluczu.
# Wartosc zmierzona na scenie logarytmiczno-normalnej o rozrzucie 1 EV, czyli
# na najblizszym matematycznym odpowiedniku "zwyczajnego zdjecia".
NEUTRAL_DARK_SHARE = 0.45

# Scena o rozpietosci ponizej tylu dzialek EV miesci sie na monitorze
# bez kompresji krancow.
NEUTRAL_RANGE_EV = 5.0
FULL_COMPRESSION_EV = 9.0  # przy tej rozpietosci kompresja jest pelna


# ------------------------------------------------------- przestrzen L*


def linear_to_lstar(y: np.ndarray | float) -> np.ndarray | float:
    """Luminancja liniowa -> jasnosc percepcyjna CIE L* (0..100)."""
    y = np.maximum(y, 0.0)
    threshold = (6.0 / 29.0) ** 3
    f = np.where(
        y > threshold,
        np.cbrt(y),
        y / (3.0 * (6.0 / 29.0) ** 2) + 4.0 / 29.0,
    )
    return 116.0 * f - 16.0


def lstar_to_linear(lightness: float) -> float:
    """CIE L* -> luminancja liniowa."""
    f = (lightness + 16.0) / 116.0
    return f**3 if f > 6.0 / 29.0 else 3.0 * (6.0 / 29.0) ** 2 * (f - 4.0 / 29.0)


# ------------------------------------------------------------- analiza


@dataclass
class SceneAnalysis:
    """Opis sceny: co w niej jest jasne, co ciemne i jak szeroko rozciagniete."""

    # percentyle luminancji liniowej
    p02: float
    p10: float
    p50: float
    p90: float
    diffuse_white: float
    peak_white: float

    range_ev: float  # rozpietosc od cieni do bieli rozproszonej
    dark_share: float  # jaka czesc kadru jest ciemna wzgledem wlasnej bieli
    specular_share: float  # udzial refleksow ponad biela rozproszona
    saturation: float

    @property
    def median_lstar(self) -> float:
        return float(linear_to_lstar(self.p50))

    @property
    def compression(self) -> float:
        """Ile kompresji krancow potrzebuje scena: 0 (wcale) do 1 (maksimum)."""
        span = FULL_COMPRESSION_EV - NEUTRAL_RANGE_EV
        return float(np.clip((self.range_ev - NEUTRAL_RANGE_EV) / span, 0.0, 1.0))

    @property
    def key_confidence(self) -> float:
        """Na ile mozna ufac ocenie klucza sceny.

        Scena bez rozpietosci tonalnej - karta szarosci, jednolita sciana,
        mgla - nie ma zadnego klucza. Ocena "w wiekszosci ciemna" jest tam
        bez sensu, bo nie ma od czego odmierzac. Przy waskim zakresie
        wracamy wiec do neutralnego celu.
        """
        return float(np.clip(self.range_ev / 3.0, 0.0, 1.0))

    @property
    def effective_dark_share(self) -> float:
        """Udzial ciemnej czesci kadru sciagniety do pewnosci oceny.

        Karta szarosci nie ma ani jednego ciemnego piksela, wiec surowa miara
        oglasza ja scena wysokiego klucza. Przy zerowej rozpietosci nie ma
        jednak czego oceniac i miara musi wrocic do wartosci neutralnej.
        """
        deviation = (self.dark_share - NEUTRAL_DARK_SHARE) * self.key_confidence
        return float(NEUTRAL_DARK_SHARE + deviation)

    @property
    def key(self) -> str:
        """Klucz sceny: niski (noc, wnetrze), neutralny, wysoki (snieg, mgla)."""
        share = self.effective_dark_share
        return "niski" if share > 0.58 else "wysoki" if share < 0.30 else "neutralny"

    @property
    def target_median_lstar(self) -> float:
        """Gdzie ma wyladowac mediana jasnosci.

        Mediana, a nie srednia ani 90. percentyl: srednia zbija do czerni kazde
        zdjecie z duza ciemna plama, a 90. percentyl opisuje swiatla, ktore i
        tak pilnuje osobne ograniczenie od gory. Mediana mowi, gdzie lezy sama
        tresc kadru.

        Cel przesuwaja dwie rzeczy.

        Klucz sceny - i to jest decyzja, ktora ratuje naraz noc i snieg: scena
        w wiekszosci ciemna wzgledem wlasnej bieli ma zostac ciemna, w
        wiekszosci jasna - jasna. Bez tego przesuniecia automat powtarza blad
        swiatlomierza, ktory kazda scene sprowadza do szarosci.

        Rozpietosc - bo im dluzsza skala sceny, tym nizej musi lezec jej
        srodek, zeby swiatla zmiescily sie pod ramieniem krzywej. Tak samo
        dziala material swiatloczuly: zdjecie o rozpietosci 9 EV naswietlone
        "na srodek" traci niebo, a scena plaska bez szkody siedzi wyzej.
        """
        key_shift = (NEUTRAL_DARK_SHARE - self.dark_share) * 80.0
        range_shift = float(np.clip((NEUTRAL_RANGE_EV - self.range_ev) * 3.0, -15.0, 5.0))
        shift = (key_shift + range_shift) * self.key_confidence
        return float(np.clip(MID_GREY_L + shift, 18.0, 78.0))


def _analysis_image(raw: RawImage, params: EditParams) -> np.ndarray:
    """Maly, liniowy obraz sRGB z aktualnym balansem bieli."""
    source = raw.camera_linear
    h, w = source.shape[:2]
    scale = min(1.0, ANALYSIS_SIZE / float(max(h, w)))
    if scale < 1.0:
        source = cv2.resize(
            source,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return camera_to_srgb(apply_white_balance(source, raw, params), raw)


def _mean_saturation(img: np.ndarray) -> float:
    mx, mn = img.max(axis=2), img.min(axis=2)
    return float(np.clip((mx - mn) / np.maximum(mx, 1e-6), 0.0, 1.0).mean())


def analyse_image(img: np.ndarray) -> SceneAnalysis:
    """Opis sceny na podstawie liniowego obrazu sRGB."""
    lum = np.maximum(img @ LUMA, 1e-7).ravel()
    p02, p10, p50, p90, p99, p999 = (
        float(v) for v in np.percentile(lum, [2, 10, 50, 90, 99, 99.9])
    )

    # Biel rozproszona a refleks. Odbicie w wodzie albo zarowka MA prawo byc
    # bialy - gdyby wyznaczac punkt bieli po absolutnym maksimum, kazde zdjecie
    # z latarnia w kadrze wyszloby beznadziejnie ciemne.
    specular_gap_ev = float(np.log2(max(p999, 1e-7) / max(p99, 1e-7)))
    diffuse_white = float(np.percentile(lum, 98.0)) if specular_gap_ev > 1.5 else p99
    specular_share = float((lum > diffuse_white).mean())

    # Udzial ciemnej czesci kadru, liczony WZGLEDEM wlasnej bieli sceny.
    # Dzieki temu miara nie zalezy od tego, czy zdjecie jest nie- czy
    # przeswietlone - opisuje sam uklad sceny, a nie blad naswietlenia.
    dark_share = float((lum < 0.18 * diffuse_white).mean())

    return SceneAnalysis(
        p02=p02, p10=p10, p50=p50, p90=p90,
        diffuse_white=diffuse_white, peak_white=p999,
        range_ev=float(np.log2(max(diffuse_white, 1e-7) / max(p02, 1e-7))),
        dark_share=dark_share,
        specular_share=specular_share,
        saturation=_mean_saturation(img),
    )


def analyse(raw: RawImage, params: EditParams | None = None) -> SceneAnalysis:
    return analyse_image(_analysis_image(raw, params or EditParams()))


# --------------------------------------------------------------- automat


def auto_tone_from(scene: SceneAnalysis) -> dict[str, float]:
    """Dobiera parametry tonalne z opisu sceny."""

    # --- 1. ekspozycja: dwa warunki, decyduje ostrozniejszy --------------
    # Warunek tresci: mediana ma wyladowac w strefie wlasciwej dla klucza
    # sceny. Warunek swiatel: biel rozproszona nie moze wyjsc ponad zakres.
    # Refleks wolno przepalic, biel z faktura - nie, bo tego sie juz nie
    # odzyska. Bierzemy mniejsze z dwoch wzmocnien, wiec zaden z warunkow
    # nie da sie zlamac drugiemu.
    #
    # Wczesniej kotwiczony byl 90. percentyl i to bylo zrodlo bledu: w
    # poprawnie naswietlonej scenie gorne 10 % lezy okolo L* 72, a nie L* 50,
    # wiec automat sciagal takie zdjecie o ponad dzialke w dol. Swiatlami
    # zajmuje sie teraz wylacznie ograniczenie od gory.
    tonal = float(
        np.log2(lstar_to_linear(scene.target_median_lstar) / max(scene.p50, 1e-7))
    )
    ceiling = float(
        np.log2(lstar_to_linear(DIFFUSE_WHITE_L) / max(scene.diffuse_white, 1e-7))
    )
    exposure = float(np.clip(min(tonal, ceiling), -4.0, 4.0))
    gain = 2.0**exposure

    compression = scene.compression

    # --- 2. kompresja krancow ------------------------------------------
    # Im szersza scena, tym mocniej trzeba scisnac oba konce, zeby zmiescila
    # sie w zakresie monitora. Zachod slonca ma okolo 8 EV i wymaga silnej
    # kompresji; plaskie pochmurne niebo prawie zadnej.
    highlights = -float(np.clip(compression * 55.0, 0.0, 85.0))

    # Cienie podnosimy o tyle, o ile dolne partie zdjecia nie dociagaja
    # do progu czytelnosci - liczone juz po ekspozycji.
    shadow_lstar = float(linear_to_lstar(scene.p10 * gain))
    shadows = float(np.clip((SHADOW_FLOOR_L - shadow_lstar) * 3.5, 0.0, 85.0))

    # --- 3. zakotwiczenie krancow --------------------------------------
    # Podzial pracy: ekspozycja odpowiada za biel rozproszona (i ma na to
    # wlasne ograniczenie od gory), suwak bieli - za sam szczyt histogramu,
    # czyli za to, zeby najjasniejszy punkt kadru siegal konca skali i ani
    # o krok dalej. Dzieki temu oba nie walcza o to samo.
    #
    # Szczyt liczymy tam, gdzie naprawde wyladuje: po ekspozycji i po
    # sciagnieciu swiatel, a wartosc suwaka - z jego rzeczywistej odpowiedzi
    # w tym punkcie. Inaczej automat zadalby ruch, ktorego suwak nie jest w
    # stanie wykonac.
    #
    # Jesli w scenie nie ma nic jasnego - zachod slonca, wnetrze przy
    # zarowce, mglisty switu - maska suwaka nie siega szczytu i biel zostaje
    # nietknieta. To nie jest brak dzialania: w takiej scenie nie ma bieli do
    # postawienia, a udawanie jej rozjasnieniem calosci zniszczyloby nastroj.
    peak_after = scene.peak_white * gain
    peak_ev = float(np.log2(max(peak_after, 1e-7) / MID_GREY_LINEAR))
    peak_after *= 1.0 + (highlights / 100.0) * _smoothstep(-0.2, 2.5, peak_ev) * 0.9
    peak_ev = float(np.log2(max(peak_after, 1e-7) / MID_GREY_LINEAR))

    white_reach = float(_smoothstep(0.5, 3.0, peak_ev)) * 0.8
    if white_reach > 0.15:
        needed = lstar_to_linear(PEAK_WHITE_L) / max(peak_after, 1e-7) - 1.0
        whites = float(np.clip(needed / white_reach * 100.0, -35.0, 35.0))
        whites *= scene.key_confidence
    else:
        whites = 0.0

    black_lstar = float(linear_to_lstar(scene.p02 * gain))
    # Podniesienie cieni splaszcza czern, wiec przywracamy punkt zaczepienia.
    blacks = float(np.clip((DEEP_BLACK_L - black_lstar) * 1.6, -30.0, 20.0))
    blacks -= float(np.clip(shadows * 0.10, 0.0, 12.0))
    blacks = float(np.clip(blacks, -35.0, 20.0))

    # --- 4. kontrast ----------------------------------------------------
    # Dwa powody, zeby go podniesc, i zaden, zeby go obnizac.
    #
    # Pierwszy: kompresja krancow splaszcza srodek zdjecia - im mocniej
    # sciagamy swiatla i podnosimy cienie, tym wiecej kontrastu trzeba oddac
    # z powrotem, inaczej szeroka scena wychodzi mdla.
    #
    # Drugi: scena plaska sama w sobie - mgla, pochmurne niebo, zdjecie przez
    # szybe - nie wypelnia zakresu monitora i zyskuje na rozciagnieciu. Warunek
    # pewnosci pilnuje, zeby nie dotyczylo to karty szarosci, ktora jest plaska
    # nie z powodu mgly, tylko dlatego, ze nie ma na niej nic do pokazania.
    compensation = compression * 8.0
    flatness = float(np.clip((NEUTRAL_RANGE_EV - scene.range_ev) / NEUTRAL_RANGE_EV, 0.0, 1.0))
    expansion = flatness * scene.key_confidence * 15.0
    contrast = float(np.clip(compensation + expansion, 0.0, 30.0))

    # --- 5. nasycenie ---------------------------------------------------
    # Efekt Hunta: postrzegana kolorowosc rosnie z jasnoscia, a podnoszenie
    # cieni odbarwia. Zdjecie juz nasycone zyskuje mniej, blade - wiecej.
    vibrance = float(np.clip(29.0 - 30.0 * scene.saturation + 6.0 * compression, 0.0, 32.0))

    return {
        "exposure": round(exposure, 2),
        "contrast": round(contrast),
        "highlights": round(highlights),
        "shadows": round(shadows),
        "whites": round(whites),
        "blacks": round(blacks),
        "vibrance": round(vibrance),
    }


def auto_tone(raw: RawImage, params: EditParams | None = None) -> dict[str, float]:
    """Dobiera parametry tonalne i zwraca je jako slownik nazw suwakow.

    Balansu bieli celowo nie ruszamy. Aparat zna warunki oswietlenia lepiej
    niz histogram, a automat "poprawiajacy" kolor zachodu slonca na neutralny
    psuje wiecej, niz naprawia.
    """
    return auto_tone_from(analyse(raw, params))
