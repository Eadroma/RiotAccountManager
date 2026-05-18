from __future__ import annotations

import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from account_storage import AccountStorage
from exporter import export_accounts, import_accounts
from settings_storage import (
    AppSettings,
    auto_detect_riot_client,
    open_data_folder,
    set_startup,
)

# Palette (duplicated here to avoid circular import with main_window)
BG      = "#1a1a1f"
BG_DARK = "#14141a"
BTN     = "#25252d"
BTN_HV  = "#2f2f39"
RED     = "#D13639"
GOLD    = "#C89B3C"
BORDER  = "#2a2a32"
TEXT    = "#ffffff"
GRAY4   = "#9ca3af"
GRAY5   = "#6b7280"


class HotkeyCaptureField(QLineEdit):
    hotkey_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hotkey = ""
        self.setReadOnly(True)
        self.setFixedHeight(32)
        self.setPlaceholderText("Click then press a key combination…")
        self.setStyleSheet(f"""
            QLineEdit {{
                background:{BG_DARK}; border:1px solid {BORDER};
                border-radius:5px; padding:0 10px;
                color:{TEXT}; font-size:12px;
            }}
            QLineEdit:focus {{ border-color:{GOLD}; }}
        """)

    def set_hotkey(self, hotkey: str) -> None:
        self._hotkey = hotkey
        self.setText(hotkey)

    def mousePressEvent(self, e) -> None:
        self.setText("Press keys…")
        self.setFocus()
        super().mousePressEvent(e)

    def keyPressEvent(self, e) -> None:
        key = e.key()
        if key in (
            Qt.Key.Key_Control, Qt.Key.Key_Shift,
            Qt.Key.Key_Alt, Qt.Key.Key_Meta,
        ):
            return
        if key == Qt.Key.Key_Escape:
            self.setText(self._hotkey)
            self.clearFocus()
            return

        parts = []
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")

        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            parts.append(chr(key))
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            parts.append(chr(key))
        elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            parts.append(f"F{key - Qt.Key.Key_F1 + 1}")
        else:
            self.setText(self._hotkey)
            self.clearFocus()
            return

        hotkey = "+".join(parts)
        self._hotkey = hotkey
        self.setText(hotkey)
        self.clearFocus()
        self.hotkey_changed.emit(hotkey)


def _sec(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{GRAY4}; font-size:10px; font-weight:500; letter-spacing:1px; background:transparent;"
    )
    return lbl


def _chk(text: str) -> QCheckBox:
    cb = QCheckBox(text)
    cb.setStyleSheet(f"""
        QCheckBox {{ color:{GRAY4}; font-size:12px; background:transparent; }}
        QCheckBox::indicator {{
            width:15px; height:15px;
            border:1px solid {BORDER}; border-radius:3px; background:{BG_DARK};
        }}
        QCheckBox::indicator:checked {{ background:{RED}; border-color:{RED}; }}
    """)
    return cb


def _radio(text: str) -> QRadioButton:
    r = QRadioButton(text)
    r.setStyleSheet(f"""
        QRadioButton {{ color:{GRAY4}; font-size:12px; background:transparent; }}
        QRadioButton::indicator {{
            width:14px; height:14px;
            border:1px solid {BORDER}; border-radius:7px; background:{BG_DARK};
        }}
        QRadioButton::indicator:checked {{ background:{RED}; border-color:{RED}; }}
    """)
    return r


def _field(placeholder: str = "") -> QLineEdit:
    f = QLineEdit()
    f.setPlaceholderText(placeholder)
    f.setFixedHeight(32)
    f.setStyleSheet(f"""
        QLineEdit {{
            background:{BG_DARK}; border:1px solid {BORDER};
            border-radius:5px; padding:0 10px;
            color:{TEXT}; font-size:12px;
        }}
        QLineEdit:focus {{ border-color:{RED}; }}
    """)
    return f


def _btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(32)
    b.setStyleSheet(f"""
        QPushButton {{
            background:{BTN}; border:1px solid {BORDER}; border-radius:5px;
            color:{GRAY4}; font-size:12px; padding:0 12px;
        }}
        QPushButton:hover {{ background:{BTN_HV}; color:{TEXT}; }}
    """)
    return b


class SettingsTab(QWidget):
    settings_changed = pyqtSignal()

    def __init__(self, s: AppSettings, storage: AccountStorage, parent=None) -> None:
        super().__init__(parent)
        self._storage = storage

        inner = QWidget()
        inner.setStyleSheet(f"background:{BG};")
        form = QVBoxLayout(inner)
        form.setContentsMargins(20, 16, 20, 20)
        form.setSpacing(6)

        # ── RIOT CLIENT ──────────────────────────────────────────────
        form.addWidget(_sec("RIOT CLIENT"))
        form.addSpacing(4)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self._path_field = _field("Path to RiotClientServices.exe")
        self._browse_btn = _btn("Browse…")
        self._detect_btn = _btn("Auto-detect")
        path_row.addWidget(self._path_field, 1)
        path_row.addWidget(self._browse_btn)
        path_row.addWidget(self._detect_btn)
        form.addLayout(path_row)

        self._path_status = QLabel("")
        self._path_status.setStyleSheet(
            f"color:{GRAY5}; font-size:11px; background:transparent;"
        )
        form.addWidget(self._path_status)

        form.addSpacing(14)

        # ── BEHAVIOR ─────────────────────────────────────────────────
        form.addWidget(_sec("BEHAVIOR"))
        form.addSpacing(6)
        self._startup_chk  = _chk("Launch on Windows startup")
        self._minimized_chk = _chk("Start minimized (tray only)")
        form.addWidget(self._startup_chk)
        form.addSpacing(4)
        form.addWidget(self._minimized_chk)

        form.addSpacing(14)

        # ── CLOSE BEHAVIOR ───────────────────────────────────────────
        form.addWidget(_sec("CLOSE BEHAVIOR"))
        form.addSpacing(6)
        self._tray_radio = _radio("Minimize to tray")
        self._quit_radio = _radio("Quit app")
        self._close_group = QButtonGroup(self)
        self._close_group.addButton(self._tray_radio, 0)
        self._close_group.addButton(self._quit_radio, 1)
        form.addWidget(self._tray_radio)
        form.addSpacing(4)
        form.addWidget(self._quit_radio)

        form.addSpacing(14)

        # ── LOGIN ────────────────────────────────────────────────────
        form.addWidget(_sec("LOGIN"))
        form.addSpacing(6)
        self._auto_min_chk        = _chk("Auto-minimize after login")
        self._disconnect_def_chk  = _chk("Default: Disconnect current account first")
        form.addWidget(self._auto_min_chk)
        form.addSpacing(4)
        form.addWidget(self._disconnect_def_chk)

        form.addSpacing(14)

        # ── GLOBAL HOTKEY ────────────────────────────────────────
        form.addWidget(_sec("GLOBAL HOTKEY"))
        form.addSpacing(6)
        self._hotkey_field = HotkeyCaptureField()
        form.addWidget(self._hotkey_field)

        form.addSpacing(20)

        # ── DATA ─────────────────────────────────────────────────────
        form.addWidget(_sec("DATA"))
        form.addSpacing(6)
        self._open_btn = _btn("Open data folder")
        self._open_btn.setFixedWidth(150)
        form.addWidget(self._open_btn)
        form.addSpacing(6)

        data_row = QHBoxLayout()
        data_row.setSpacing(6)
        self._export_btn = _btn("Export accounts…")
        self._import_btn = _btn("Import accounts…")
        data_row.addWidget(self._export_btn)
        data_row.addWidget(self._import_btn)
        data_row.addStretch()
        form.addLayout(data_row)

        self._data_status = QLabel("")
        self._data_status.setStyleSheet(
            f"color:{GRAY5}; font-size:11px; background:transparent;"
        )
        form.addWidget(self._data_status)

        form.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border:none; background:{BG}; }}
            QScrollBar:vertical {{ background:{BG}; width:4px; border:none; margin:0; }}
            QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:2px; min-height:20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self._loading = True
        self.populate(s)
        self._loading = False

        self._browse_btn.clicked.connect(self._on_browse)
        self._detect_btn.clicked.connect(self._on_detect)
        self._open_btn.clicked.connect(open_data_folder)
        self._export_btn.clicked.connect(self._on_export)
        self._import_btn.clicked.connect(self._on_import)
        self._startup_chk.toggled.connect(self._on_startup_toggled)
        self._minimized_chk.toggled.connect(self._emit)
        self._tray_radio.toggled.connect(self._emit)
        self._quit_radio.toggled.connect(self._emit)
        self._auto_min_chk.toggled.connect(self._emit)
        self._disconnect_def_chk.toggled.connect(self._emit)
        self._path_field.textChanged.connect(self._emit)
        self._hotkey_field.hotkey_changed.connect(self._emit)

    def populate(self, s: AppSettings) -> None:
        self._path_field.setText(s.riot_client_path)
        self._startup_chk.setChecked(s.launch_on_startup)
        self._minimized_chk.setChecked(s.start_minimized)
        self._tray_radio.setChecked(s.minimize_to_tray_on_close)
        self._quit_radio.setChecked(not s.minimize_to_tray_on_close)
        self._auto_min_chk.setChecked(s.auto_minimize_after_login)
        self._disconnect_def_chk.setChecked(s.disconnect_first_default)
        self._hotkey_field.set_hotkey(s.global_hotkey)

    def collect(self) -> AppSettings:
        return AppSettings(
            riot_client_path=self._path_field.text().strip(),
            launch_on_startup=self._startup_chk.isChecked(),
            start_minimized=self._minimized_chk.isChecked(),
            minimize_to_tray_on_close=self._tray_radio.isChecked(),
            auto_minimize_after_login=self._auto_min_chk.isChecked(),
            disconnect_first_default=self._disconnect_def_chk.isChecked(),
            global_hotkey=self._hotkey_field._hotkey,
        )

    def _emit(self) -> None:
        if not self._loading:
            self.settings_changed.emit()

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Riot Client executable", "", "Executables (*.exe)"
        )
        if path:
            self._path_field.setText(path)
            self._path_status.setText("")

    def _on_detect(self) -> None:
        path = auto_detect_riot_client()
        if path:
            self._path_field.setText(path)
            self._path_status.setStyleSheet(
                f"color:{GOLD}; font-size:11px; background:transparent;"
            )
            self._path_status.setText(f"Detected: {path}")
        else:
            self._path_status.setStyleSheet(
                "color:#f87171; font-size:11px; background:transparent;"
            )
            self._path_status.setText("Not found — enter path manually.")

    def _on_startup_toggled(self, checked: bool) -> None:
        try:
            set_startup(checked, sys.executable)
        except OSError as exc:
            self._startup_chk.blockSignals(True)
            self._startup_chk.setChecked(not checked)
            self._startup_chk.blockSignals(False)
            self._path_status.setStyleSheet(
                "color:#f87171; font-size:11px; background:transparent;"
            )
            self._path_status.setText(f"Startup error: {exc}")
            return
        self._emit()

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export accounts", "", "AccountManager Backup (*.ambak)"
        )
        if not path:
            return
        pw, ok = QInputDialog.getText(
            self, "Export — set password", "Password:", QLineEdit.EchoMode.Password
        )
        if not ok or not pw:
            self._data_status.setStyleSheet("color:#f87171; font-size:11px; background:transparent;")
            self._data_status.setText("Export cancelled — password is required.")
            return
        pw2, ok2 = QInputDialog.getText(
            self, "Export — confirm password", "Confirm password:", QLineEdit.EchoMode.Password
        )
        if not ok2 or pw != pw2:
            self._data_status.setStyleSheet("color:#f87171; font-size:11px; background:transparent;")
            self._data_status.setText("Passwords do not match.")
            return
        try:
            export_accounts(self._storage.load_accounts(), path, pw)
            self._data_status.setStyleSheet(f"color:{GOLD}; font-size:11px; background:transparent;")
            self._data_status.setText("Export successful.")
        except Exception as exc:
            self._data_status.setStyleSheet("color:#f87171; font-size:11px; background:transparent;")
            self._data_status.setText(f"Export failed: {exc}")

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import accounts", "", "AccountManager Backup (*.ambak)"
        )
        if not path:
            return
        pw, ok = QInputDialog.getText(
            self, "Import — enter password", "Password:", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        try:
            accounts = import_accounts(path, pw)
            for a in accounts:
                self._storage.add_or_update(a.username, a.password, a.note, a.game)
            self._data_status.setStyleSheet(f"color:{GOLD}; font-size:11px; background:transparent;")
            self._data_status.setText(f"Imported {len(accounts)} account(s).")
            self.settings_changed.emit()
        except ValueError as exc:
            self._data_status.setStyleSheet("color:#f87171; font-size:11px; background:transparent;")
            self._data_status.setText(str(exc))
        except Exception as exc:
            self._data_status.setStyleSheet("color:#f87171; font-size:11px; background:transparent;")
            self._data_status.setText(f"Import failed: {exc}")
