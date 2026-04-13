from datetime import datetime
from pathlib import Path

import win32gui
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from account_storage import AccountStorage
from riot_ui_login import RiotUIError, login

_ICON_PATH = str(Path(__file__).parent.parent / "icon.ico")


def _format_last_used(iso: str) -> str:
    if not iso:
        return "Never"
    delta = datetime.now() - datetime.fromisoformat(iso)
    s = int(delta.total_seconds())
    if s < 60:
        return "Just now"
    if s < 3600:
        return f"{s // 60} minute{'s' if s // 60 != 1 else ''} ago"
    if s < 86400:
        return f"{s // 3600} hour{'s' if s // 3600 != 1 else ''} ago"
    return f"{s // 86400} day{'s' if s // 86400 != 1 else ''} ago"


class AccountManagerWindow(QWidget):
    """Main application window: account list on the left, form on the right."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AccountManager")
        self.storage = AccountStorage()
        self.accounts = self.storage.load_accounts()
        self._build_ui()
        self._refresh_account_list()
        self._start_tray()
        self._start_riot_client_watcher()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.account_list = QListWidget()
        self.account_list.currentRowChanged.connect(self._on_row_changed)
        self.account_list.itemDoubleClicked.connect(lambda: self._login_account())

        up_button = QPushButton("▲")
        down_button = QPushButton("▼")
        up_button.setFixedWidth(32)
        down_button.setFixedWidth(32)
        up_button.clicked.connect(self._move_up)
        down_button.clicked.connect(self._move_down)

        order_layout = QVBoxLayout()
        order_layout.addWidget(up_button)
        order_layout.addWidget(down_button)
        order_layout.addStretch()

        list_layout = QHBoxLayout()
        list_layout.addWidget(self.account_list)
        list_layout.addLayout(order_layout)

        self.username_field = QLineEdit()
        self.username_field.setPlaceholderText("Username")

        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_field.setPlaceholderText("Password")

        self.toggle_pw_button = QPushButton("👁")
        self.toggle_pw_button.setFixedWidth(30)
        self.toggle_pw_button.setCheckable(True)
        self.toggle_pw_button.clicked.connect(self._toggle_password_visibility)

        pw_row = QHBoxLayout()
        pw_row.addWidget(self.password_field)
        pw_row.addWidget(self.toggle_pw_button)

        self.note_field = QLineEdit()
        self.note_field.setPlaceholderText("Note (optional)")

        self.last_used_label = QLabel("Last used: —")
        self.last_used_label.setStyleSheet("color: gray; font-size: 11px;")

        self.save_button = QPushButton("Save account")
        self.remove_button = QPushButton("Remove account")
        self.login_button = QPushButton("Login")

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        self.save_button.clicked.connect(self._save_account)
        self.remove_button.clicked.connect(self._remove_account)
        self.login_button.clicked.connect(self._login_account)

        form_layout = QVBoxLayout()
        form_layout.addWidget(QLabel("Username"))
        form_layout.addWidget(self.username_field)
        form_layout.addWidget(QLabel("Password"))
        form_layout.addLayout(pw_row)
        form_layout.addWidget(QLabel("Note"))
        form_layout.addWidget(self.note_field)
        form_layout.addWidget(self.last_used_label)
        form_layout.addWidget(self.save_button)
        form_layout.addWidget(self.remove_button)
        form_layout.addWidget(self.login_button)
        form_layout.addWidget(self.status_label)
        form_layout.addStretch()

        main_layout = QHBoxLayout(self)
        main_layout.addLayout(list_layout, 1)
        main_layout.addLayout(form_layout, 0)

        self.setMinimumSize(560, 360)

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _start_tray(self) -> None:
        self._tray = QSystemTrayIcon(QIcon(_ICON_PATH), self)
        self._tray.setToolTip("AccountManager")

        menu = QMenu()
        show_action = menu.addAction("Show")
        menu.addSeparator()
        quit_action = menu.addAction("Quit")

        show_action.triggered.connect(self._show_window)
        quit_action.triggered.connect(QApplication.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # single click
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        """Minimize to tray instead of quitting."""
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "AccountManager",
            "Running in the background. Click the tray icon to reopen.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    # ------------------------------------------------------------------
    # Riot Client watcher
    # ------------------------------------------------------------------

    def _start_riot_client_watcher(self) -> None:
        self._riot_client_was_open = bool(win32gui.FindWindow(None, "Riot Client"))
        self._watcher = QTimer(self)
        self._watcher.timeout.connect(self._check_riot_client)
        self._watcher.start(2000)

    def _check_riot_client(self) -> None:
        is_open = bool(win32gui.FindWindow(None, "Riot Client"))
        if is_open and not self._riot_client_was_open:
            self._show_window()
        self._riot_client_was_open = is_open

    # ------------------------------------------------------------------
    # List helpers
    # ------------------------------------------------------------------

    def _label(self, account) -> str:
        if account.note:
            return f"{account.username} - {account.note}"
        return account.username

    def _refresh_account_list(self, keep_row: int = -1) -> None:
        self.accounts = self.storage.load_accounts()
        self.account_list.blockSignals(True)
        self.account_list.clear()
        for account in self.accounts:
            self.account_list.addItem(self._label(account))
        self.account_list.blockSignals(False)

        if 0 <= keep_row < self.account_list.count():
            self.account_list.setCurrentRow(keep_row)
        elif self.account_list.count() > 0:
            self.account_list.setCurrentRow(0)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.accounts):
            self.username_field.clear()
            self.password_field.clear()
            self.note_field.clear()
            self.last_used_label.setText("Last used: —")
            return

        account = self.accounts[row]
        self.username_field.setText(account.username)
        self.password_field.setText(account.password)
        self.note_field.setText(account.note)
        self.last_used_label.setText(f"Last used: {_format_last_used(account.last_used)}")

    def _toggle_password_visibility(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.password_field.setEchoMode(mode)

    def _move_up(self) -> None:
        row = self.account_list.currentRow()
        if row <= 0:
            return
        accounts = self.storage.load_accounts()
        accounts[row - 1], accounts[row] = accounts[row], accounts[row - 1]
        self.storage.save_accounts(accounts)
        self._refresh_account_list(keep_row=row - 1)

    def _move_down(self) -> None:
        row = self.account_list.currentRow()
        accounts = self.storage.load_accounts()
        if row < 0 or row >= len(accounts) - 1:
            return
        accounts[row], accounts[row + 1] = accounts[row + 1], accounts[row]
        self.storage.save_accounts(accounts)
        self._refresh_account_list(keep_row=row + 1)

    def _save_account(self) -> None:
        username = self.username_field.text().strip()
        password = self.password_field.text().strip()
        note = self.note_field.text().strip()
        if not username or not password:
            self._set_status("Username and password are required.", error=True)
            return

        self.storage.add_or_update(username, password, note)
        self.accounts = self.storage.load_accounts()
        row = next((i for i, a in enumerate(self.accounts) if a.username.lower() == username.lower()), 0)
        self._refresh_account_list(keep_row=row)
        self._set_status(f"Account '{username}' saved.")

    def _remove_account(self) -> None:
        row = self.account_list.currentRow()
        if row < 0:
            self._set_status("Select an account to remove.", error=True)
            return

        username = self.accounts[row].username
        self.storage.remove(username)
        self._refresh_account_list(keep_row=max(0, row - 1))
        self.username_field.clear()
        self.password_field.clear()
        self.note_field.clear()
        self.last_used_label.setText("Last used: —")
        self._set_status(f"Account '{username}' removed.")

    def _login_account(self) -> None:
        username = self.username_field.text().strip()
        password = self.password_field.text().strip()
        if not username or not password:
            self._set_status("Select an account or enter credentials first.", error=True)
            return

        try:
            login(username, password)
            self.storage.update_last_used(username)
            # Refresh label immediately
            row = self.account_list.currentRow()
            if 0 <= row < len(self.accounts):
                self.last_used_label.setText("Last used: Just now")
            self._set_status(f"Credentials sent to Riot Client for '{username}'.")
        except RiotUIError as exc:
            self._set_status(str(exc), error=True)
        except Exception as exc:
            self._set_status(f"Unexpected error: {exc}", error=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, message: str, *, error: bool = False) -> None:
        color = "red" if error else "green"
        self.status_label.setText(f'<span style="color:{color}">{message}</span>')
