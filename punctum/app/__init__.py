"""Warstwa interfejsu uzytkownika (PySide6).

MainWindow laduje sie leniwie: `punctum.app.jezyk` i ekran startowy musza
dac sie zaimportowac, zanim wstanie cale okno z mapa i torem obrobki -
inaczej ekran startowy pokazalby sie dopiero po najdluzszej czesci startu.
"""

__all__ = ["MainWindow"]


def __getattr__(nazwa: str):
    if nazwa == "MainWindow":
        from .main_window import MainWindow

        globals()["MainWindow"] = MainWindow
        return MainWindow
    raise AttributeError(nazwa)
