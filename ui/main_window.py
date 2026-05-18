from datetime import datetime
from pathlib import Path

import win32gui
from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
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
from global_hotkey import GlobalHotkeyThread
from login_history import add_login
from riot_ui_login import RiotUIError, login
from settings_storage import AppSettings, load_settings, save_settings
from ui.history_tab import HistoryTab
from ui.login_worker import LoginWorker
from ui.settings_tab import SettingsTab
from updater import UpdateChecker
from version import VERSION

_ICON_PATH = str(Path(__file__).parent.parent / "icon.ico")

GROUP_COLORS = ["#C89B3C", "#0bc4e3", "#a78bfa", "#34d399", "#f97316", "#f472b6"]

# ── Game tags ─────────────────────────────────────────────────────────────
GAMES = ["", "League of Legends", "Valorant", "TFT", "Wild Rift"]
GAME_PILLS = {
    "League of Legends": ("#0bc4e3", "LoL"),
    "Valorant":          ("#ff4655", "VAL"),
    "TFT":               ("#c69b3a", "TFT"),
    "Wild Rift":         ("#0ac8b9", "WR"),
}

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
    drag_started   = pyqtSignal(int)
    drag_moved     = pyqtSignal(int, QPoint)
    drag_ended     = pyqtSignal(int, QPoint)

    _DRAG_THRESHOLD = 8

    def __init__(self, account, index: int, indented: bool = False, group_color: str = "", parent=None):
        super().__init__(parent)
        self._idx = index
        self._sel = False
        self._hov = False
        self._group_color = group_color
        self._drag_start: QPoint | None = None
        self._dragging = False
        self.setFixedHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoFillBackground(False)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(28 if indented else 12, 8, 12, 8)
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

        if account.game in GAME_PILLS:
            color, abbr = GAME_PILLS[account.game]
            pill = QLabel(abbr)
            pill.setStyleSheet(
                f"color:{color}; background:transparent;"
                f"border:1px solid {color}; border-radius:3px;"
                f"font-size:10px; padding:1px 5px;"
            )
            hl.addWidget(pill)

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
        elif self._group_color:
            p.fillRect(0, 6, 3, self.height() - 12, QColor(self._group_color))
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
            self._drag_start = e.globalPosition().toPoint()
            self._dragging = False
            self.item_clicked.emit(self._idx)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._drag_start is not None and e.buttons() & Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self._drag_start
            if not self._dragging and delta.manhattanLength() > self._DRAG_THRESHOLD:
                self._dragging = True
                self.grabMouse()
                self.drag_started.emit(self._idx)
            if self._dragging:
                self.drag_moved.emit(self._idx, e.globalPosition().toPoint())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self.releaseMouse()
                self.drag_ended.emit(self._idx, e.globalPosition().toPoint())
                self._dragging = False
            self._drag_start = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._idx)
        super().mouseDoubleClickEvent(e)


# ── Group header ───────────────────────────────────────────────────────────
class GroupHeaderWidget(QFrame):
    toggle_requested = pyqtSignal(str)

    def __init__(self, name: str, count: int, collapsed: bool, color: str = GOLD, parent=None) -> None:
        super().__init__(parent)
        self._group_name = name
        self._color = color
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QFrame { background:transparent; border:none; }")

        hl = QHBoxLayout(self)
        hl.setContentsMargins(6, 0, 8, 0)
        hl.setSpacing(5)

        self._arrow = QLabel("▶" if collapsed else "▼")
        self._arrow.setStyleSheet(f"color:{GRAY5}; font-size:9px; background:transparent;")

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color:{GRAY4}; font-size:11px; font-weight:500; letter-spacing:0.5px; background:transparent;"
        )

        count_lbl = QLabel(f"({count})")
        count_lbl.setStyleSheet(f"color:{GRAY5}; font-size:10px; background:transparent;")

        hl.addWidget(self._arrow)
        hl.addWidget(name_lbl)
        hl.addWidget(count_lbl)
        hl.addStretch()

    def set_collapsed(self, v: bool) -> None:
        self._arrow.setText("▶" if v else "▼")

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0, 4, 3, self.height() - 8, QColor(self._color))
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.toggle_requested.emit(self._group_name)
        super().mousePressEvent(e)


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
        self._group_header_widgets: list[GroupHeaderWidget] = []
        self._collapsed_groups: set[str] = set()
        self._dragging_acc_idx: int | None = None
        self._login_worker: LoginWorker | None = None
        self._hotkey_thread: GlobalHotkeyThread | None = None
        self._settings = load_settings()

        self._build_ui()
        self._refresh_list()
        self._start_tray()
        QApplication.instance().installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self._stop_hotkey)
        self._start_riot_client_watcher()
        self._start_update_checker()
        self._start_hotkey()

    # ── UI construction ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background-color:{BG_DARK}; border:none; }}"
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

        self._settings_tab = SettingsTab(self._settings, self.storage)
        self._settings_tab.settings_changed.connect(self._on_settings_changed)
        self._tabs.addTab(self._settings_tab, "Settings")

        self._history_tab = HistoryTab()
        self._tabs.addTab(self._history_tab, "History")

        self._tabs.currentChanged.connect(self._on_tab_changed)

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

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_row.setContentsMargins(0, 0, 0, 0)

        self._search_field = QLineEdit()
        self._search_field.setPlaceholderText("Search accounts…")
        self._search_field.setFixedHeight(28)
        self._search_field.setStyleSheet(f"""
            QLineEdit {{
                background:{BG_DARK}; border:1px solid {BORDER};
                border-radius:5px; padding:0 8px;
                color:{TEXT}; font-size:12px;
            }}
            QLineEdit:focus {{ border-color:{RED}; }}
        """)
        self._search_field.textChanged.connect(self._apply_filters)

        self._game_filter = QComboBox()
        self._game_filter.addItem("All", "")
        for game in GAMES[1:]:
            abbr = GAME_PILLS[game][1] if game in GAME_PILLS else game
            self._game_filter.addItem(abbr, game)
        self._game_filter.setFixedHeight(28)
        self._game_filter.setFixedWidth(80)
        self._game_filter.setStyleSheet(f"""
            QComboBox {{
                background:{BG_DARK}; border:1px solid {BORDER};
                border-radius:5px; padding:0 6px;
                color:{GRAY4}; font-size:11px;
            }}
            QComboBox:focus {{ border-color:{RED}; }}
            QComboBox::drop-down {{ border:none; width:16px; }}
            QComboBox::down-arrow {{ image:none; width:0; }}
            QComboBox QAbstractItemView {{
                background:{BG_DARK}; border:1px solid {BORDER};
                color:{TEXT}; selection-background-color:{ITEM_SEL};
                font-size:11px;
            }}
        """)
        self._game_filter.currentIndexChanged.connect(self._apply_filters)

        filter_row.addWidget(self._search_field, 1)
        filter_row.addWidget(self._game_filter)
        left.addLayout(filter_row)

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background:transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._drop_line = QFrame(self._list_container)
        self._drop_line.setFixedHeight(2)
        self._drop_line.setStyleSheet(f"background:{RED}; border:none; border-radius:1px;")
        self._drop_line.hide()

        self._list_scroll = QScrollArea()
        scroll = self._list_scroll
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
        right.addSpacing(14)

        right.addWidget(_form_label("GAME"))
        right.addSpacing(5)
        self.game_combo = QComboBox()
        self.game_combo.addItems(GAMES)
        self.game_combo.setFixedHeight(34)
        self.game_combo.setStyleSheet(f"""
            QComboBox {{
                background:{BG_DARK}; border:1px solid {BORDER};
                border-radius:5px; padding:0 10px;
                color:{TEXT}; font-size:13px;
            }}
            QComboBox:focus {{ border-color:{RED}; }}
            QComboBox::drop-down {{ border:none; width:24px; }}
            QComboBox::down-arrow {{ image:none; width:0; }}
            QComboBox QAbstractItemView {{
                background:{BG_DARK}; border:1px solid {BORDER};
                color:{TEXT}; selection-background-color:{ITEM_SEL};
            }}
        """)
        right.addWidget(self.game_combo)
        right.addSpacing(14)

        right.addWidget(_form_label("GROUP"))
        right.addSpacing(5)
        self.group_combo = QComboBox()
        self.group_combo.setFixedHeight(34)
        self.group_combo.setStyleSheet(f"""
            QComboBox {{
                background:{BG_DARK}; border:1px solid {BORDER};
                border-radius:5px; padding:0 10px;
                color:{TEXT}; font-size:13px;
            }}
            QComboBox:focus {{ border-color:{RED}; }}
            QComboBox::drop-down {{ border:none; width:24px; }}
            QComboBox::down-arrow {{ image:none; width:0; }}
            QComboBox QAbstractItemView {{
                background:{BG_DARK}; border:1px solid {BORDER};
                color:{TEXT}; selection-background-color:{ITEM_SEL};
            }}
        """)
        self.group_combo.currentIndexChanged.connect(self._on_group_combo_changed)
        right.addWidget(self.group_combo)
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

    def _refresh_list(self, keep_acc: int = -1) -> None:
        self.accounts = self.storage.load_accounts()

        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._item_widgets.clear()
        self._group_header_widgets.clear()

        # Collect groups preserving order of first appearance
        group_order: list[str] = []
        groups: dict[str, list[int]] = {}
        for i, acc in enumerate(self.accounts):
            g = acc.group or ""
            if g not in groups:
                groups[g] = []
                if g:
                    group_order.append(g)
            groups[g].append(i)

        pos = 0

        for color_idx, gname in enumerate(group_order):
            color = GROUP_COLORS[color_idx % len(GROUP_COLORS)]
            indices = groups[gname]
            collapsed = gname in self._collapsed_groups
            header = GroupHeaderWidget(gname, len(indices), collapsed, color=color)
            header.toggle_requested.connect(self._toggle_group)
            self._list_layout.insertWidget(pos, header)
            self._group_header_widgets.append(header)
            pos += 1
            for acc_idx in indices:
                w = AccountItemWidget(self.accounts[acc_idx], acc_idx, indented=True, group_color=color)
                w.item_clicked.connect(self._on_item_clicked)
                w.double_clicked.connect(lambda _: self._login_account())
                w.drag_started.connect(self._on_drag_started)
                w.drag_moved.connect(self._on_drag_moved)
                w.drag_ended.connect(self._on_drag_ended)
                w.setVisible(not collapsed)
                self._item_widgets.append(w)
                self._list_layout.insertWidget(pos, w)
                pos += 1

        for acc_idx in groups.get("", []):
            w = AccountItemWidget(self.accounts[acc_idx], acc_idx)
            w.item_clicked.connect(self._on_item_clicked)
            w.double_clicked.connect(lambda _: self._login_account())
            w.drag_started.connect(self._on_drag_started)
            w.drag_moved.connect(self._on_drag_moved)
            w.drag_ended.connect(self._on_drag_ended)
            self._item_widgets.append(w)
            self._list_layout.insertWidget(pos, w)
            pos += 1

        if keep_acc >= 0:
            widget_idx = next((i for i, w in enumerate(self._item_widgets) if w._idx == keep_acc), 0)
        else:
            widget_idx = 0 if self._item_widgets else -1

        self._set_selected(widget_idx)
        if hasattr(self, "group_combo"):
            self._rebuild_group_combo()
        if hasattr(self, "_tray_menu"):
            self._rebuild_tray_menu()

    def _set_selected(self, row: int) -> None:
        if 0 <= self._selected_row < len(self._item_widgets):
            self._item_widgets[self._selected_row].set_selected(False)
        self._selected_row = row
        if 0 <= row < len(self._item_widgets):
            self._item_widgets[row].set_selected(True)
            self._populate_form(self._item_widgets[row]._idx)
        else:
            self._clear_form()

    def _on_item_clicked(self, acc_idx: int) -> None:
        widget_idx = next((i for i, w in enumerate(self._item_widgets) if w._idx == acc_idx), -1)
        self._set_selected(widget_idx)

    def _populate_form(self, acc_idx: int) -> None:
        acc = self.accounts[acc_idx]
        self.username_field.setText(acc.username)
        self.password_field.setText(acc.password)
        self.note_field.setText(acc.note)
        self.game_combo.setCurrentText(acc.game)
        lu = _fmt_time(acc.last_used) if acc.last_used else "Never"
        self.last_used_lbl.setText(f"Last used: {lu}")
        self.group_combo.blockSignals(True)
        idx = self.group_combo.findData(acc.group)
        self.group_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.group_combo.blockSignals(False)

    def _clear_form(self) -> None:
        self.username_field.clear()
        self.password_field.clear()
        self.note_field.clear()
        self.game_combo.setCurrentIndex(0)
        self.group_combo.blockSignals(True)
        self.group_combo.setCurrentIndex(0)
        self.group_combo.blockSignals(False)
        self.last_used_lbl.setText("")

    def _new_account(self) -> None:
        self._set_selected(-1)
        self._rebuild_group_combo()
        self._clear_form()
        self.username_field.setFocus()

    def _apply_filters(self) -> None:
        q = self._search_field.text().lower()
        game_filter = self._game_filter.currentData()
        filter_active = bool(q or game_filter)

        acc_visible: dict[int, bool] = {}
        for w in self._item_widgets:
            acc = self.accounts[w._idx]
            text_match = (
                not q
                or q in acc.username.lower()
                or q in acc.note.lower()
                or q in acc.game.lower()
            )
            game_match = not game_filter or acc.game == game_filter
            acc_visible[w._idx] = text_match and game_match

        for w in self._item_widgets:
            acc = self.accounts[w._idx]
            if filter_active:
                w.setVisible(acc_visible[w._idx])
            else:
                w.setVisible(acc.group not in self._collapsed_groups)

        for header in self._group_header_widgets:
            gname = header._group_name
            if filter_active:
                has_visible = any(
                    acc_visible[w._idx]
                    for w in self._item_widgets
                    if self.accounts[w._idx].group == gname
                )
                header.setVisible(has_visible)
            else:
                header.setVisible(True)

    def _toggle_group(self, group_name: str) -> None:
        collapsed = group_name not in self._collapsed_groups
        if collapsed:
            self._collapsed_groups.add(group_name)
        else:
            self._collapsed_groups.discard(group_name)
        for h in self._group_header_widgets:
            if h._group_name == group_name:
                h.set_collapsed(collapsed)
                break
        for w in self._item_widgets:
            if self.accounts[w._idx].group == group_name:
                w.setVisible(not collapsed)

    # ── Drag-to-reorder ────────────────────────────────────────────────

    def _on_drag_started(self, acc_idx: int) -> None:
        self._dragging_acc_idx = acc_idx

    def _on_drag_moved(self, acc_idx: int, global_pos: QPoint) -> None:
        insert_before, _ = self._get_drop_target(global_pos)
        y = self._drop_line_y(insert_before)
        if y is not None:
            self._drop_line.setGeometry(8, y - 1, self._list_container.width() - 16, 2)
            self._drop_line.raise_()
            self._drop_line.show()

    def _on_drag_ended(self, acc_idx: int, global_pos: QPoint) -> None:
        self._drop_line.hide()
        insert_before, new_group = self._get_drop_target(global_pos)
        self._dragging_acc_idx = None
        is_noop = (
            (insert_before == acc_idx or insert_before == acc_idx + 1)
            and new_group == self.accounts[acc_idx].group
        )
        if not is_noop:
            self._perform_drop(acc_idx, insert_before, new_group)

    def _get_drop_target(self, global_pos: QPoint) -> tuple[int, str]:
        local_y = self._list_container.mapFromGlobal(global_pos).y()

        all_items: list[tuple[int, str, str, int | None]] = []  # (y, wtype, group, acc_idx)
        for h in self._group_header_widgets:
            if h.isVisible():
                all_items.append((h.y(), "header", h._group_name, None))
        for w in self._item_widgets:
            if w.isVisible() and w._idx != self._dragging_acc_idx:
                all_items.append((w.y(), "item", self.accounts[w._idx].group, w._idx))
        all_items.sort(key=lambda x: x[0])

        if not all_items:
            return (-1, "")

        for y, wtype, group, acc_idx in all_items:
            mid = y + (28 if wtype == "header" else 54) // 2
            if local_y <= mid:
                if wtype == "header":
                    first = next(
                        (w._idx for w in self._item_widgets
                         if self.accounts[w._idx].group == group and w._idx != self._dragging_acc_idx),
                        -1,
                    )
                    return (first, group)
                return (acc_idx, group)

        last = all_items[-1]
        return (-1, last[2])

    def _drop_line_y(self, insert_before: int) -> int | None:
        if insert_before >= 0:
            w = next((w for w in self._item_widgets if w._idx == insert_before), None)
            return w.y() if w else None
        visible = [w for w in self._item_widgets if w.isVisible() and w._idx != self._dragging_acc_idx]
        headers = [h for h in self._group_header_widgets if h.isVisible()]
        all_v = visible + headers  # type: ignore[operator]
        if not all_v:
            return 0
        last = max(all_v, key=lambda x: x.y() + x.height())
        return last.y() + last.height()

    def _perform_drop(self, dragged_acc_idx: int, insert_before: int, new_group: str) -> None:
        accounts = self.storage.load_accounts()
        dragged = accounts[dragged_acc_idx]
        dragged.group = new_group
        accounts.pop(dragged_acc_idx)
        if insert_before < 0:
            accounts.append(dragged)
            new_idx = len(accounts) - 1
        else:
            if insert_before > dragged_acc_idx:
                insert_before -= 1
            accounts.insert(insert_before, dragged)
            new_idx = insert_before
        self.storage.save_accounts(accounts)
        self._refresh_list(keep_acc=new_idx)

    def _rebuild_group_combo(self) -> None:
        prev = self.group_combo.currentData()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("(No group)", "")
        seen: set[str] = set()
        for acc in self.accounts:
            if acc.group and acc.group not in seen:
                self.group_combo.addItem(acc.group, acc.group)
                seen.add(acc.group)
        self.group_combo.addItem("New group…", "__new__")
        idx = self.group_combo.findData(prev)
        self.group_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.group_combo.blockSignals(False)

    def _on_group_combo_changed(self, _: int) -> None:
        if self.group_combo.currentData() != "__new__":
            return
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        self.group_combo.blockSignals(True)
        if ok and name.strip():
            name = name.strip()
            insert_at = self.group_combo.count() - 1
            self.group_combo.insertItem(insert_at, name, name)
            self.group_combo.setCurrentIndex(insert_at)
        else:
            self.group_combo.setCurrentIndex(0)
        self.group_combo.blockSignals(False)

    # ── Slots ──────────────────────────────────────────────────────────

    def _toggle_password(self, checked: bool) -> None:
        self.password_field.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _move_up(self) -> None:
        row = self._selected_row
        if row < 0 or not self._item_widgets:
            return
        acc_idx = self._item_widgets[row]._idx
        if acc_idx <= 0:
            return
        accounts = self.storage.load_accounts()
        accounts[acc_idx - 1], accounts[acc_idx] = accounts[acc_idx], accounts[acc_idx - 1]
        self.storage.save_accounts(accounts)
        self._refresh_list(keep_acc=acc_idx - 1)

    def _move_down(self) -> None:
        row = self._selected_row
        if row < 0 or not self._item_widgets:
            return
        acc_idx = self._item_widgets[row]._idx
        accounts = self.storage.load_accounts()
        if acc_idx >= len(accounts) - 1:
            return
        accounts[acc_idx], accounts[acc_idx + 1] = accounts[acc_idx + 1], accounts[acc_idx]
        self.storage.save_accounts(accounts)
        self._refresh_list(keep_acc=acc_idx + 1)

    def _save_account(self) -> None:
        username = self.username_field.text().strip()
        password = self.password_field.text().strip()
        note     = self.note_field.text().strip()
        group    = self.group_combo.currentData() or ""
        if group == "__new__":
            group = ""
        if not username or not password:
            self._set_status("Username and password are required.", error=True)
            return
        self.storage.add_or_update(username, password, note, self.game_combo.currentText(), group)
        self.accounts = self.storage.load_accounts()
        acc_idx = next(
            (i for i, a in enumerate(self.accounts) if a.username.lower() == username.lower()), 0
        )
        self._refresh_list(keep_acc=acc_idx)
        self._set_status(f"Account '{username}' saved.")

    def _remove_account(self) -> None:
        row = self._selected_row
        if row < 0 or not self._item_widgets:
            self._set_status("Select an account to remove.", error=True)
            return
        acc_idx = self._item_widgets[row]._idx
        username = self.accounts[acc_idx].username
        self.storage.remove(username)
        keep = max(0, acc_idx - 1) if len(self.accounts) > 1 else -1
        self._refresh_list(keep_acc=keep)
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
        add_login(username, game=self._get_account_game(username))
        if 0 <= self._selected_row < len(self._item_widgets):
            self.last_used_lbl.setText("Last used: Just now")
        self._set_status(f"Credentials sent for '{username}'.")
        self.login_btn.setEnabled(True)
        self.login_btn.setText("Login  →")
        game = self._get_account_game(username)
        tray_msg = f"Logged in as {username}" + (f"  ·  {game}" if game else "")
        self._tray.showMessage("AccountManager", tray_msg, QSystemTrayIcon.MessageIcon.Information, 3000)
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

    # ── Keyboard navigation ────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.isVisible():
            return False
        key = event.key()
        mods = event.modifiers()
        # Ctrl+F: focus search from anywhere
        if key == Qt.Key.Key_F and mods & Qt.KeyboardModifier.ControlModifier:
            self._search_field.setFocus()
            self._search_field.selectAll()
            return True
        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QComboBox)):
            return False
        # /: focus search when no input is active
        if key == Qt.Key.Key_Slash:
            self._search_field.setFocus()
            return True
        if key == Qt.Key.Key_Up:
            self._select_adjacent(-1)
            return True
        if key == Qt.Key.Key_Down:
            self._select_adjacent(1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._login_account()
            return True
        if key == Qt.Key.Key_Delete:
            self._remove_account()
            return True
        if key == Qt.Key.Key_Escape:
            self._set_selected(-1)
            return True
        return False

    def _select_adjacent(self, direction: int) -> None:
        visible = [w for w in self._item_widgets if w.isVisible()]
        if not visible:
            return
        if self._selected_row < 0 or self._selected_row >= len(self._item_widgets):
            target = visible[0] if direction > 0 else visible[-1]
        else:
            current = self._item_widgets[self._selected_row]
            if current not in visible:
                target = visible[0]
            else:
                i = visible.index(current)
                target = visible[max(0, min(i + direction, len(visible) - 1))]
        widget_idx = self._item_widgets.index(target)
        self._set_selected(widget_idx)
        self._list_scroll.ensureWidgetVisible(target)

    def _on_tab_changed(self, index: int) -> None:
        if self._tabs.widget(index) is self._history_tab:
            self._history_tab.refresh()

    def _get_account_game(self, username: str) -> str:
        for a in self.accounts:
            if a.username.lower() == username.lower():
                return a.game
        return ""

    def _on_settings_changed(self) -> None:
        self._settings = self._settings_tab.collect()
        save_settings(self._settings)
        self.disconnect_chk.setChecked(self._settings.disconnect_first_default)
        self._start_hotkey()

    def _start_hotkey(self) -> None:
        if self._hotkey_thread is not None:
            self._hotkey_thread.triggered.disconnect()
            self._hotkey_thread.stop_thread()
            self._hotkey_thread.wait()
            self._hotkey_thread = None
        hotkey = self._settings.global_hotkey
        if hotkey:
            self._hotkey_thread = GlobalHotkeyThread(hotkey, self)
            self._hotkey_thread.triggered.connect(self._show_window)
            self._hotkey_thread.start()

    def _stop_hotkey(self) -> None:
        if self._hotkey_thread is not None:
            self._hotkey_thread.stop_thread()
            self._hotkey_thread.wait()
            self._hotkey_thread = None

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
        add_login(username, game=self._get_account_game(username))
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
            self._stop_hotkey()
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
