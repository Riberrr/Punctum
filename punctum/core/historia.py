"""Cofnij / ponow: historia nastaw zdjec i historia przypisan lokalizacji.

Dwie osobne historie, bo to dwa rozne rodzaje pracy. W Edycji krokiem jest
stan jednego zdjecia - kazde zdjecie ma wlasny ciag, wiec cofniecie na
zdjeciu B nie zjada kroku zrobionego chwile wczesniej na zdjeciu A. W Mapie
jeden krok obejmuje wiele zdjec naraz (przypisanie zaznaczonym), wiec
historia jest wspolna dla katalogu i pamieta zmiane "przed -> po".

Modul nie zna Qt: jest to czysta logika, ktora test sprawdza bez okna.
"""

from __future__ import annotations

import copy
from typing import Any

# Tyle krokow wstecz trzymamy na zdjecie. Stan to kilkanascie liczb, wiec
# pamieci to nie kosztuje - limit jest tylko po to, zeby wielogodzinna
# sesja nie rosla bez konca.
LIMIT_KROKOW = 200


class HistoriaStanow:
    """Ciag stanow dla kazdego klucza (sciezki zdjecia) i pozycja w nim.

    Zapamietanie stanu rownego biezacemu nic nie robi - dzieki temu mozna
    je wolac "na wszelki wypadek" (po wczytaniu zdjecia, po cofnieciu),
    a krok powstaje tylko z prawdziwej zmiany.
    """

    def __init__(self, limit: int = LIMIT_KROKOW):
        self.limit = limit
        self._stany: dict[str, list[Any]] = {}
        self._pozycja: dict[str, int] = {}

    def zapamietaj(self, klucz: str, stan: Any) -> bool:
        """Dopisuje stan jako nowy krok. False, gdy nic sie nie zmienilo."""
        stany = self._stany.setdefault(klucz, [])
        pozycja = self._pozycja.get(klucz, -1)
        if pozycja >= 0 and stany[pozycja] == stan:
            return False
        # Nowa zmiana po cofnieciu odcina galaz "do ponowienia" - tak dziala
        # kazdy edytor i inaczej ponow prowadziloby w nieoczekiwane miejsce.
        del stany[pozycja + 1:]
        # Kopia, bo EditParams jest zmienny, a historia ma pamietac stan
        # z chwili zapisu, nie obiekt, ktory ktos pozniej przestawi.
        stany.append(copy.deepcopy(stan))
        if len(stany) > self.limit:
            del stany[: len(stany) - self.limit]
        self._pozycja[klucz] = len(stany) - 1
        return True

    def mozna_cofnac(self, klucz: str | None) -> bool:
        return klucz is not None and self._pozycja.get(klucz, -1) > 0

    def mozna_ponowic(self, klucz: str | None) -> bool:
        if klucz is None:
            return False
        return self._pozycja.get(klucz, -1) < len(self._stany.get(klucz, ())) - 1

    def cofnij(self, klucz: str) -> Any | None:
        if not self.mozna_cofnac(klucz):
            return None
        self._pozycja[klucz] -= 1
        return copy.deepcopy(self._stany[klucz][self._pozycja[klucz]])

    def ponow(self, klucz: str) -> Any | None:
        if not self.mozna_ponowic(klucz):
            return None
        self._pozycja[klucz] += 1
        return copy.deepcopy(self._stany[klucz][self._pozycja[klucz]])

    def wyczysc(self) -> None:
        self._stany.clear()
        self._pozycja.clear()


class HistoriaKrokow:
    """Wspolna lista krokow; krok to {klucz: (przed, po)}.

    Cofniecie oddaje wartosci "przed", ponowienie "po" - tyle wystarczy, zeby
    przypisanie lokalizacji trzydziestu zdjeciom cofnac jednym ruchem.
    """

    def __init__(self, limit: int = LIMIT_KROKOW):
        self.limit = limit
        self._kroki: list[dict[str, tuple[Any, Any]]] = []
        self._pozycja = 0  # liczba krokow "zrobionych"; dalej leza do ponowienia

    def zapamietaj(self, krok: dict[str, tuple[Any, Any]]) -> bool:
        krok = {klucz: para for klucz, para in krok.items() if para[0] != para[1]}
        if not krok:
            return False  # np. usuniecie lokalizacji ze zdjecia, ktore jej nie mialo
        del self._kroki[self._pozycja:]
        self._kroki.append(copy.deepcopy(krok))
        if len(self._kroki) > self.limit:
            del self._kroki[: len(self._kroki) - self.limit]
        self._pozycja = len(self._kroki)
        return True

    def mozna_cofnac(self) -> bool:
        return self._pozycja > 0

    def mozna_ponowic(self) -> bool:
        return self._pozycja < len(self._kroki)

    def cofnij(self) -> dict[str, Any] | None:
        if not self.mozna_cofnac():
            return None
        self._pozycja -= 1
        return {klucz: przed for klucz, (przed, _po) in self._kroki[self._pozycja].items()}

    def ponow(self) -> dict[str, Any] | None:
        if not self.mozna_ponowic():
            return None
        krok = self._kroki[self._pozycja]
        self._pozycja += 1
        return {klucz: po for klucz, (_przed, po) in krok.items()}

    def wyczysc(self) -> None:
        self._kroki.clear()
        self._pozycja = 0
