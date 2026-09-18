"""Czy silnik przegladarki wstaje w srodowisku Punctum.

QtWebEngine jest czescia PySide6-Addons, ale nie na kazdym systemie startuje
(sterowniki, polityka GPU, brak bibliotek). Lepiej dowiedziec sie tego teraz
niz po napisaniu calej mapy.
"""

import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception as error:  # noqa: BLE001
    print(f"BRAK QtWebEngine: {type(error).__name__}: {error}")
    raise SystemExit(1)

print("import QtWebEngineWidgets: OK")

view = QWebEngineView()
view.resize(900, 600)
view.setHtml(
    "<html><body style='background:#0e0e12;color:#e8e6f0;font:16px sans-serif'>"
    "<h1 id='t'>silnik dziala</h1></body></html>",
    QUrl("http://localhost/"),
)
view.show()


def probe() -> None:
    def got(value) -> None:
        print(f"JavaScript odpowiedzial: {value!r}")
        from PySide6 import __version__
        print(f"PySide6 {__version__}")
        app.quit()

    view.page().runJavaScript("document.getElementById('t').textContent", got)


QTimer.singleShot(2500, probe)
QTimer.singleShot(12000, app.quit)  # gdyby silnik nie odpowiedzial wcale
sys.exit(app.exec())
