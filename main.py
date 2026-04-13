import ctypes
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui.main_window import AccountManagerWindow

ICON_PATH = Path(__file__).parent / "icon.ico"
APP_ID = "RiotAccountManager.1.0"


def _set_app_id() -> None:
    """Tell Windows this is its own app, not pythonw.exe — fixes taskbar icon."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except AttributeError:
        pass


def main() -> None:
    _set_app_id()
    app = QApplication(sys.argv)

    icon = QIcon(str(ICON_PATH)) if ICON_PATH.exists() else QIcon()
    app.setWindowIcon(icon)

    window = AccountManagerWindow()
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
