"""Wlaczenie jezyka w calej aplikacji Qt - raz, przed zbudowaniem okien.

Napisy licza sie w chwili tworzenia widzetow, dlatego jezyk zmienia sie
dopiero po ponownym uruchomieniu: przebudowa wszystkich okien w locie
kosztowalaby wiecej niz jest warta przy zmianie robionej raz na zawsze.
"""

from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

from .. import przeklad
from . import podpowiedzi


def zastosuj_jezyk(app, zapisany: str) -> str:
    """Ustawia jezyk napisow, podpowiedzi, liczb i okien Qt. Zwraca kod."""
    kod = przeklad.ustaw_jezyk(przeklad.dobierz_jezyk(zapisany, QLocale.system().name()))
    podpowiedzi.ustaw_jezyk(kod)
    # Pola liczbowe (QDoubleSpinBox) biora separator z domyslnego QLocale,
    # a nie z naszego przekladu - bez tego "2,50" zostaloby po angielsku.
    QLocale.setDefault(QLocale(kod))
    # Napisy samego Qt: przyciski okna wyboru folderu, menu pod prawym
    # przyciskiem w polach tekstowych. Qt ma je po angielsku z natury,
    # po polsku potrzebuje swojego pliku.
    tlumacz = QTranslator(app)
    katalog = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if tlumacz.load(f"qtbase_{kod}", katalog):
        app.installTranslator(tlumacz)
    return kod
