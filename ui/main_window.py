from datetime import datetime
from pathlib import Path

import win32gui
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from account_storage import AccountStorage
from riot_ui_login import RiotUIError, login
from settings_storage import AppSettings, load_settings, save_settings
from ui.login_worker import LoginWorker
from ui.settings_tab import SettingsTab
from updater import UpdateChecker
from version import VERSION

_ICON_PATH = str(Path(__file__).parent.parent / "icon.ico")

# ── Palette ────────────────────────────────────────────────────────────────
BG       = "#1a1a1f"
BG_DARK  = "#14141a"
ITEM     = "#1e1e26"
ITEM_HV  = "#232329"
ITEM_SEL = "#25252d"
BTN      = "#25252d"
BTN_HV   = "#2f2f39"
RED      = "#D13639"
RED_HV   = "#e63e41"
GOLD     = "#C89B3C"
BORDER   = "#2a2a32"
TEXT     = "#ffffff"
GRAY4    = "#9ca3af"
GRAY5    = "#6b7280"


def _fmt_time(iso: str) -> str:
    if not iso:
        return "Never"
    s = int((datetime.now() - datetime.fromisoformat(iso)).total_seconds())
    if s < 60:    return "Just now"
    if s < 3600:  return f"{s // 60}m ago"
    if s < 86400: return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


# ── Account list item ──────────────────────────────────────────────────────
class AccountItemWidget(QFrame):
    item_clicked   = pyqtSignal(int)
    double_clicked = pyqtSignal(int)

    def __init__(self, account, index: int, parent=None):
        super().__init__(parent)
        self._idx = index
        self._sel = False
        self._hov = False
        self.setFixedHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoFillBackground(False)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(16, 8, 12, 8)
        hl.setSpacing(8)

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        uname = QLabel(account.username)
        uname.setStyleSheet(
            f"color:{TEXT}; font-size:13px; font-weight:500; background:transparent;"
        )
        col.addWidget(uname)

        if account.note:
            note = QLabel(account.note)
            note.setStyleSheet(
                f"color:{GRAY5}; font-size:11px; background:transparent;"
            )
            col.addWidget(note)

        hl.addLayout(col)
        hl.addStretch()

        has = bool(account.last_used)
        badge = QLabel(_fmt_time(account.last_used))
        if has:
            badge.setStyleSheet(
                f"color:{GOLD}; background:rgba(200,155,60,.12);"
                f"border:1px solid rgba(200,155,60,.25); border-radius:3px;"
                f"font-size:10px; padding:1px 5px;"
            )
        else:
            badge.setStyleSheet(
                f"color:{GRAY5}; background:rgba(107,114,128,.12);"
                f"border:1px solid rgba(107,114,128,.25); border-radius:3px;"
                f"font-size:10px; padding:1px 5px;"
            )
        hl.addWidget(badge)

    def set_selected(self, v: bool) -> None:
        self._sel = v
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(ITEM_SEL if self._sel else (ITEM_HV if self._hov else ITEM))
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 6, 6)
        p.fillPath(path, bg)
        if self._sel:
            p.fillRect(0, 6, 3, self.height() - 12, QColor(RED))
        p.end()

    def enterEvent(self, e) -> None:
        self._hov = True
        if not self._sel:
            self.update()

    def leaveEvent(self, e) -> None:
        self._hov = False
        if not self._sel:
            self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.item_clicked.emit(self._idx)
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._idx)
        super().mouseDoubleClickEvent(e)


# ── Main window ────────────────────────────────────────────────────────────
class AccountManagerWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AccountManager")
        self.setMinimumSize(660, 480)
        self.setStyleSheet(
            f"QWidget {{ background-color:{BG}; color:{TEXT}; font-family:'Segoe UI',system-ui,sans-serif; }}"
        )

        self.storage = AccountStorage()
        self.accounts: list = []
        self._selected_row = -1
        self._item_widgets: list[AccountItemWidget] = []
        self._login_worker: LoginWorker | None = None
        self._settings = load_settings()

        self._build_ui()
        self._refresh_list()
        self._start_tray()
        self._start_riot_client_watcher()
        self._start_update_checker()

    # ── UI construction ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background-color:{BG_DARK}; border:none; border-bottom:1px solid {BORDER}; }}"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 14, 24, 14)
        hl.setSpacing(0)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("Account Manager")
        title.setStyleSheet(
            f"color:{TEXT}; font-size:16px; font-weight:600; background:transparent;"
        )
        subtitle = QLabel("Manage multiple Riot Games accounts")
        subtitle.setStyleSheet(
            f"color:{GRAY5}; font-size:11px; background:transparent;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        hl.addLayout(title_col)
        hl.addStretch()
        root.addWidget(header)

        # Update banner (hidden until an update is detected)
        self._update_banner = QFrame()
        self._update_banner.setStyleSheet(
            f"QFrame {{ background:rgba(200,155,60,.10); border:none; "
            f"border-bottom:1px solid rgba(200,155,60,.25); }}"
        )
        bl = QHBoxLayout(self._update_banner)
        bl.setContentsMargins(24, 7, 12, 7)
        bl.setSpacing(8)
        self._update_lbl = QLabel()
        self._update_lbl.setStyleSheet(
            f"color:{GOLD}; font-size:12px; background:transparent; text-decoration:underline;"
        )
        self._update_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_lbl.mousePressEvent = lambda _: QDesktopServices.openUrl(
            QUrl(getattr(self, "_update_url", ""))
        )
        dismiss_btn = QPushButton("✕")
        dismiss_btn.setFixedSize(22, 22)
        dismiss_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; color:{GRAY5}; font-size:11px; }}"
            f"QPushButton:hover {{ color:{TEXT}; }}"
        )
        dismiss_btn.clicked.connect(self._update_banner.hide)
        bl.addWidget(self._update_lbl)
        bl.addStretch()
        bl.addWidget(dismiss_btn)
        self._update_banner.hide()
        root.addWidget(self._update_banner)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:none; background:{BG}; }}
            QTabBar::tab {{
                background:{BTN}; color:{GRAY4}; border:none;
                padding:7px 20px; font-size:12px; font-weight:500;
                border-top-left-radius:5px; border-top-right-radius:5px;
                margin-right:2px; margin-top:4px;
            }}
            QTabBar::tab:selected {{ background:{ITEM_SEL}; color:{TEXT}; margin-top:2px; }}
            QTabBar::tab:hover:!selected {{ background:{BTN_HV}; color:{TEXT}; }}
            QTabWidget > QWidget {{ background:{BG}; }}
        """)

        accounts_page = self._build_accounts_page()
        self._tabs.addTab(accounts_page, "Accounts")

        self._settings_tab = SettingsTab(self._settings)
        self._settings_tab.settings_changed.connect(self._on_settings_changed)
        self._tabs.addTab(self._settings_tab, "Settings")

        root.addWidget(self._tabs, 1)

    def _build_accounts_page(self) -> QWidget:
        page = QWidget()
        body_layout = QHBoxLayout(page)
        body_layout.setContentsMargins(20, 20, 20, 20)
        body_layout.setSpacing(20)

        # ── Left panel ──────────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(8)

        sec_row = QHBoxLayout()
        sec_row.setContentsMargins(0, 0, 0, 0)
        sec_row.setSpacing(4)

        sec_lbl = QLabel("ACCOUNTS")
        sec_lbl.setStyleSheet(
            f"color:{GRAY4}; font-size:10px; font-weight:500; letter-spacing:1px; background:transparent;"
        )
        self._up_btn   = _icon_btn("▲")
        self._down_btn = _icon_btn("▼")
        self._new_btn  = _icon_btn("+")
        self._up_btn.clicked.connect(self._move_up)
        self._down_btn.clicked.connect(self._move_down)
        self._new_btn.clicked.connect(self._new_account)
        self._new_btn.setToolTip("New account")

        sec_row.addWidget(sec_lbl)
        sec_row.addStretch()
        sec_row.addWidget(self._up_btn)
        sec_row.addWidget(self._down_btn)
        sec_row.addSpacing(4)
        sec_row.addWidget(self._new_btn)
        left.addLayout(sec_row)

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background:transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._list_container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border:none; background:transparent; }}
            QScrollArea > QWidget > QWidget {{ background:transparent; }}
            QScrollBar:vertical {{ background:{BG}; width:4px; border:none; margin:0; }}
            QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:2px; min-height:20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        scroll.setFixedWidth(240)

        left.addWidget(scroll, 1)
        body_layout.addLayout(left)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet(f"color:{BORDER}; background:{BORDER}; max-width:1px;")
        body_layout.addWidget(div)

        # ── Right panel ─────────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(0)
        right.setContentsMargins(0, 0, 0, 0)

        right.addWidget(_form_label("USERNAME"))
        right.addSpacing(5)
        self.username_field = _input("Username")
        right.addWidget(self.username_field)
        right.addSpacing(14)

        right.addWidget(_form_label("PASSWORD"))
        right.addSpacing(5)
        pw_row = QHBoxLayout()
        pw_row.setSpacing(6)
        pw_row.setContentsMargins(0, 0, 0, 0)
        self.password_field = _input("Password", password=True)
        self._toggle_pw = _icon_btn("👁")
        self._toggle_pw.setFixedSize(34, 34)
        self._toggle_pw.setCheckable(True)
        self._toggle_pw.clicked.connect(self._toggle_password)
        pw_row.addWidget(self.password_field, 1)
        pw_row.addWidget(self._toggle_pw)
        right.addLayout(pw_row)
        right.addSpacing(14)

        right.addWidget(_form_label("NOTE"))
        right.addSpacing(5)
        self.note_field = _input("Optional note")
        right.addWidget(self.note_field)
        right.addSpacing(10)

        self.last_used_lbl = QLabel("")
        self.last_used_lbl.setStyleSheet(
            f"color:{GRAY5}; font-size:11px; background:transparent;"
        )
        right.addWidget(self.last_used_lbl)
        right.addSpacing(6)

        # Disconnect checkbox
        self.disconnect_chk = QCheckBox("Disconnect current account first")
        self.disconnect_chk.setChecked(self._settings.disconnect_first_default)
        self.disconnect_chk.setStyleSheet(f"""
            QCheckBox {{ color:{GRAY4}; font-size:12px; background:transparent; }}
            QCheckBox::indicator {{
                width:15px; height:15px;
                border:1px solid {BORDER}; border-radius:3px; background:{BG_DARK};
            }}
            QCheckBox::indicator:checked {{ background:{RED}; border-color:{RED}; }}
        """)
        right.addWidget(self.disconnect_chk)

        right.addStretch()

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.save_btn   = _button("Save", "secondary")
        self.remove_btn = _button("Remove", "danger")
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.remove_btn)
        right.addLayout(btn_row)
        right.addSpacing(8)

        self.login_btn = _button("Login  →", "primary")
        right.addWidget(self.login_btn)
        right.addSpacing(8)

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.hide()
        right.addWidget(self.status_lbl)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self.status_lbl.hide)

        self.save_btn.clicked.connect(self._save_account)
        self.remove_btn.clicked.connect(self._remove_account)
        self.login_btn.clicked.connect(self._login_account)

        body_layout.addLayout(right, 1)
        return page

    # ── Account list ───────────────────────────────────────────────────

    def _refresh_list(self, keep_row: int = -1) -> None:
        self.accounts = self.storage.load_accounts()

        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._item_widgets.clear()

        for i, acc in enumerate(self.accounts):
            w = AccountItemWidget(acc, i)
            w.item_clicked.connect(self._on_item_clicked)
            w.double_clicked.connect(lambda _: self._login_account())
            self._item_widgets.append(w)
            self._list_layout.insertWidget(i, w)

        target = keep_row if 0 <= keep_row < len(self._item_widgets) else (0 if self._item_widgets else -1)
        self._set_selected(target)
        if hasattr(self, "_tray_menu"):
            self._rebuild_tray_menu()

    def _set_selected(self, row: int) -> None:
        if 0 <= self._selected_row < len(self._item_widgets):
            self._item_widgets[self._selected_row].set_selected(False)
        self._selected_row = row
        if 0 <= row < len(self._item_widgets):
            self._item_widgets[row].set_selected(True)
            self._populate_form(row)
        else:
            self._clear_form()

    def _on_item_clicked(self, index: int) -> None:
        self._set_selected(index)

    def _populate_form(self, row: int) -> None:
        acc = self.accounts[row]
        self.username_field.setText(acc.username)
        self.password_field.setText(acc.password)
        self.note_field.setText(acc.note)
        lu = _fmt_time(acc.last_used) if acc.last_used else "Never"
        self.last_used_lbl.setText(f"Last used: {lu}")

    def _clear_form(self) -> None:
        self.username_field.clear()
        self.password_field.clear()
        self.note_field.clear()
        self.last_used_lbl.setText("")

    def _new_account(self) -> None:
        self._set_selected(-1)
        self._clear_form()
        self.username_field.setFocus()

    # ── Slots ──────────────────────────────────────────────────────────

    def _toggle_password(self, checked: bool) -> None:
        self.password_field.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _move_up(self) -> None:
        row = self._selected_row
        if row <= 0:
            return
        accounts = self.storage.load_accounts()
        accounts[row - 1], accounts[row] = accounts[row], accounts[row - 1]
        self.storage.save_accounts(accounts)
        self._refresh_list(keep_row=row - 1)

    def _move_down(self) -> None:
        row = self._selected_row
        accounts = self.storage.load_accounts()
        if row < 0 or row >= len(accounts) - 1:
            return
        accounts[row], accounts[row + 1] = accounts[row + 1], accounts[row]
        self.storage.save_accounts(accounts)
        self._refresh_list(keep_row=row + 1)

    def _save_account(self) -> None:
        username = self.username_field.text().strip()
        password = self.password_field.text().strip()
        note     = self.note_field.text().strip()
        if not username or not password:
            self._set_status("Username and password are required.", error=True)
            return
        self.storage.add_or_update(username, password, note)
        self.accounts = self.storage.load_accounts()
        row = next(
            (i for i, a in enumerate(self.accounts) if a.username.lower() == username.lower()), 0
        )
        self._refresh_list(keep_row=row)
        self._set_status(f"Account '{username}' saved.")

    def _remove_account(self) -> None:
        row = self._selected_row
        if row < 0:
            self._set_status("Select an account to remove.", error=True)
            return
        username = self.accounts[row].username
        self.storage.remove(username)
        self._refresh_list(keep_row=max(0, row - 1))
        self._clear_form()
        self._set_status(f"Account '{username}' removed.")

    def _login_account(self) -> None:
        username = self.username_field.text().strip()
        password = self.password_field.text().strip()
        if not username or not password:
            self._set_status("Select an account or enter credentials first.", error=True)
            return
        if self._login_worker is not None:
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("Logging in…")

        worker = LoginWorker(
            username,
            password,
            disconnect_first=self.disconnect_chk.isChecked(),
            riot_client_path=self._settings.riot_client_path,
        )
        worker.progress.connect(lambda msg: self._set_status(msg, auto_hide=False))
        worker.finished_ok.connect(self._on_login_ok)
        worker.finished_err.connect(self._on_login_err)
        worker.finished.connect(self._clear_login_worker)
        self._login_worker = worker
        worker.start()

    def _clear_login_worker(self) -> None:
        if self._login_worker:
            self._login_worker.deleteLater()
            self._login_worker = None

    def _on_login_ok(self, username: str) -> None:
        self.storage.update_last_used(username)
        row = self._selected_row
        if 0 <= row < len(self.accounts):
            self.last_used_lbl.setText("Last used: Just now")
        self._set_status(f"Credentials sent for '{username}'.")
        self.login_btn.setEnabled(True)
        self.login_btn.setText("Login  →")
        if self._settings.auto_minimize_after_login:
            self.hide()

    def _on_login_err(self, msg: str) -> None:
        self._set_status(msg, error=True)
        self.login_btn.setEnabled(True)
        self.login_btn.setText("Login  →")

    def _set_status(self, msg: str, *, error: bool = False, auto_hide: bool = True) -> None:
        self._status_timer.stop()
        self.status_lbl.show()
        if error:
            self.status_lbl.setStyleSheet(
                "background:rgba(239,68,68,.10); border:1px solid rgba(239,68,68,.25);"
                "border-radius:5px; color:#f87171; font-size:12px; padding:6px 10px;"
            )
        else:
            self.status_lbl.setStyleSheet(
                "background:rgba(34,197,94,.10); border:1px solid rgba(34,197,94,.25);"
                "border-radius:5px; color:#4ade80; font-size:12px; padding:6px 10px;"
            )
        self.status_lbl.setText(msg)
        if auto_hide:
            self._status_timer.start(3000)

    def _on_settings_changed(self) -> None:
        self._settings = self._settings_tab.collect()
        save_settings(self._settings)
        self.disconnect_chk.setChecked(self._settings.disconnect_first_default)

    # ── System tray ────────────────────────────────────────────────────

    def _start_tray(self) -> None:
        self._tray = QSystemTrayIcon(QIcon(_ICON_PATH), self)
        self._tray.setToolTip("AccountManager")
        self._tray_menu = QMenu()
        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()
        self._rebuild_tray_menu()

    def _rebuild_tray_menu(self) -> None:
        self._tray_menu.clear()
        self._tray_menu.addAction("Show").triggered.connect(self._show_window)

        if self.accounts:
            self._tray_menu.addSeparator()
            login_menu = self._tray_menu.addMenu("Login as…")
            for acc in self.accounts:
                action = login_menu.addAction(acc.username)
                action.triggered.connect(
                    lambda checked, u=acc.username, p=acc.password: self._tray_login(u, p)
                )

        self._tray_menu.addSeparator()
        self._tray_menu.addAction("Quit").triggered.connect(QApplication.quit)

    def _tray_login(self, username: str, password: str) -> None:
        if self._login_worker is not None:
            self._tray.showMessage(
                "AccountManager",
                "A login is already in progress.",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
            return
        worker = LoginWorker(
            username,
            password,
            disconnect_first=self._settings.disconnect_first_default,
            riot_client_path=self._settings.riot_client_path,
        )
        worker.finished_ok.connect(self._on_tray_login_ok)
        worker.finished_err.connect(self._on_tray_login_err)
        worker.finished.connect(self._clear_login_worker)
        self._login_worker = worker
        worker.start()

    def _on_tray_login_ok(self, username: str) -> None:
        self.storage.update_last_used(username)
        self._refresh_list(keep_row=self._selected_row)
        self._tray.showMessage(
            "AccountManager",
            f"Logged in as {username}.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _on_tray_login_err(self, msg: str) -> None:
        self._tray.showMessage(
            "AccountManager",
            msg,
            QSystemTrayIcon.MessageIcon.Critical,
            4000,
        )

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        if self._settings.minimize_to_tray_on_close:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "AccountManager",
                "Running in the background. Click the tray icon to reopen.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            QApplication.quit()

    # ── Riot Client watcher ────────────────────────────────────────────

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

    # ── Update checker ─────────────────────────────────────────────────

    def _start_update_checker(self) -> None:
        self._updater = UpdateChecker(VERSION)
        self._updater.update_found.connect(self._on_update_found)
        self._updater.finished.connect(self._updater.deleteLater)
        self._updater.start()

    def _on_update_found(self, version: str, url: str) -> None:
        self._update_url = url
        self._update_lbl.setText(f"Version {version} available — click to download")
        self._update_banner.show()
        self._tray.showMessage(
            "AccountManager",
            f"Update available: v{version}. Open the app to download.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )


# ── Widget factory helpers ─────────────────────────────────────────────────

def _form_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{GRAY4}; font-size:10px; font-weight:500; letter-spacing:1px; background:transparent;"
    )
    return lbl


def _input(placeholder: str, *, password: bool = False) -> QLineEdit:
    f = QLineEdit()
    f.setPlaceholderText(placeholder)
    f.setFixedHeight(34)
    if password:
        f.setEchoMode(QLineEdit.EchoMode.Password)
    f.setStyleSheet(f"""
        QLineEdit {{
            background:{BG_DARK}; border:1px solid {BORDER};
            border-radius:5px; padding:0 10px;
            color:{TEXT}; font-size:13px;
        }}
        QLineEdit:focus {{ border-color:{RED}; }}
    """)
    return f


def _icon_btn(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedSize(28, 28)
    btn.setStyleSheet(f"""
        QPushButton {{
            background:{BTN}; border:none; border-radius:4px;
            color:{GRAY4}; font-size:12px;
        }}
        QPushButton:hover {{ background:{BTN_HV}; color:{TEXT}; }}
        QPushButton:disabled {{ color:{GRAY5}; }}
    """)
    return btn


def _button(text: str, style: str = "secondary") -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedHeight(36)
    if style == "primary":
        btn.setStyleSheet(f"""
            QPushButton {{
                background:{RED}; border:none; border-radius:6px;
                color:white; font-size:13px; font-weight:600; padding:0 16px;
            }}
            QPushButton:hover {{ background:{RED_HV}; }}
            QPushButton:disabled {{ background:rgba(209,54,57,.4); }}
        """)
    elif style == "danger":
        btn.setStyleSheet(f"""
            QPushButton {{
                background:{BTN}; border:1px solid {BORDER}; border-radius:6px;
                color:{TEXT}; font-size:13px; font-weight:500; padding:0 16px;
            }}
            QPushButton:hover {{
                background:rgba(239,68,68,.15); color:#f87171;
                border-color:rgba(239,68,68,.35);
            }}
            QPushButton:disabled {{ color:{GRAY5}; }}
        """)
    else:
        btn.setStyleSheet(f"""
            QPushButton {{
                background:{BTN}; border:1px solid {BORDER}; border-radius:6px;
                color:{TEXT}; font-size:13px; font-weight:500; padding:0 16px;
            }}
            QPushButton:hover {{ background:{BTN_HV}; }}
            QPushButton:disabled {{ color:{GRAY5}; }}
        """)
    return btn
