"""Stan pol wyboru w oknie ustawien - odczytany z widzetow, nie z pikseli."""

import os
import sys

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication(sys.argv)

from punctum.app.settings_dialog import SettingsDialog
from punctum.core.hardware import detect_system
from punctum.core.settings import Settings, settings_path

settings = Settings.load()
print(f"plik ustawien: {settings_path()}")
print(f"istnieje     : {os.path.exists(settings_path())}")
print(f"reopen_last_folder w ustawieniach: {settings.reopen_last_folder}")
print(f"show_navigator w ustawieniach    : {settings.show_navigator}")

dialog = SettingsDialog(settings, detect_system())
print(f"\npole 'otwieraj ostatni folder' zaznaczone: {dialog.reopen_box.isChecked()}")
print(f"pole 'pokazuj nawigator' zaznaczone      : {dialog.navigator_box.isChecked()}")
print(f"wybrany silnik: {[k for k, b in dialog.engine_buttons.items() if b.isChecked()]}")
