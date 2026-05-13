from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from riot_ui_login import RiotUIError, login
from riot_process import kill_riot_processes, launch_riot_client, wait_for_login_window


class LoginWorker(QThread):
    progress     = pyqtSignal(str)
    finished_ok  = pyqtSignal(str)   # username
    finished_err = pyqtSignal(str)   # error message

    def __init__(
        self,
        username: str,
        password: str,
        *,
        disconnect_first: bool = False,
        riot_client_path: str = "",
    ) -> None:
        super().__init__()
        self._username = username
        self._password = password
        self._disconnect_first = disconnect_first
        self._riot_client_path = riot_client_path

    def run(self) -> None:
        try:
            hwnd: int | None = None
            if self._disconnect_first:
                if not self._riot_client_path:
                    raise RiotUIError(
                        "Riot Client path not set. Configure it in the Settings tab."
                    )
                self.progress.emit("Closing Riot Client…")
                kill_riot_processes()

                self.progress.emit("Launching Riot Client…")
                launch_riot_client(self._riot_client_path)

                self.progress.emit("Waiting for login form to load…")
                hwnd = wait_for_login_window()
                self.progress.emit("Sending credentials…")

            login(self._username, self._password, hwnd=hwnd)
            self.finished_ok.emit(self._username)
        except (RiotUIError, FileNotFoundError) as exc:
            self.finished_err.emit(str(exc))
        except Exception as exc:
            self.finished_err.emit(f"Unexpected error: {exc}")
