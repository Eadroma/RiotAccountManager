import ctypes
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

from account_storage import DATA_DIR, StorageError
from ui.main_window import AccountManagerWindow

ICON_PATH = Path(__file__).parent / "icon.ico"
APP_ID    = "RiotAccountManager.1.0"
IPC_NAME  = "RiotAccountManager-Instance"
LOG_MAX_BYTES = 1_000_000


def _write_error_log(exc_type, exc, tb) -> Path:
    """Append a timestamped traceback (type, message, stack; no locals) to error.log."""
    log_file = DATA_DIR / "error.log"
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    stamp = datetime.now().isoformat(timespec="seconds")
    try:
        too_big = log_file.exists() and log_file.stat().st_size > LOG_MAX_BYTES
        with log_file.open("w" if too_big else "a", encoding="utf-8") as f:
            f.write(f"[{stamp}]\n{text}\n")
    except OSError:
        pass
    return log_file


def _excepthook(exc_type, exc, tb) -> None:
    # A custom hook also stops PyQt6 from aborting the app on an exception inside a slot.
    log_file = _write_error_log(exc_type, exc, tb)
    if QApplication.instance() is not None:
        QMessageBox.critical(
            None, "AccountManager",
            f"Unexpected error ({exc_type.__name__}).\nDetails were saved to {log_file}.",
        )


def _set_app_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except AttributeError:
        pass


def main() -> None:
    sys.excepthook = _excepthook
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

    try:
        window = AccountManagerWindow()
    except StorageError as exc:
        QMessageBox.critical(None, "AccountManager", str(exc))
        sys.exit(1)
    window.setWindowIcon(icon)

    def _on_new_connection() -> None:
        client = server.nextPendingConnection()
        if client:
            window._show_window()
            client.disconnectFromServer()

    server.newConnection.connect(_on_new_connection)

    if not ("--minimized" in sys.argv or window._settings.start_minimized):
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
