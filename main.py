import ctypes
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from ui.main_window import AccountManagerWindow

ICON_PATH = Path(__file__).parent / "icon.ico"
APP_ID    = "RiotAccountManager.1.0"
IPC_NAME  = "RiotAccountManager-Instance"


def _set_app_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except AttributeError:
        pass


def main() -> None:
    _set_app_id()
    app = QApplication(sys.argv)

    # If another instance is running, tell it to raise and exit.
    sock = QLocalSocket()
    sock.connectToServer(IPC_NAME)
    if sock.waitForConnected(300):
        sock.write(b"raise")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        sys.exit(0)

    # First instance: start the IPC server.
    server = QLocalServer()
    QLocalServer.removeServer(IPC_NAME)
    server.listen(IPC_NAME)

    icon = QIcon(str(ICON_PATH)) if ICON_PATH.exists() else QIcon()
    app.setWindowIcon(icon)

    window = AccountManagerWindow()
    window.setWindowIcon(icon)

    def _on_new_connection() -> None:
        client = server.nextPendingConnection()
        if client:
            window._show_window()
            client.disconnectFromServer()

    server.newConnection.connect(_on_new_connection)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
