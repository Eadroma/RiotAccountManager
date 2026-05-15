from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from login_history import clear_history, load_history

BG      = "#1a1a1f"
BG_DARK = "#14141a"
BTN     = "#25252d"
BTN_HV  = "#2f2f39"
BORDER  = "#2a2a32"
TEXT    = "#ffffff"
GRAY4   = "#9ca3af"
GRAY5   = "#6b7280"
ITEM    = "#1e1e26"

GAME_PILLS = {
    "League of Legends": ("#0bc4e3", "LoL"),
    "Valorant":          ("#ff4655", "VAL"),
    "TFT":               ("#c69b3a", "TFT"),
    "Wild Rift":         ("#0ac8b9", "WR"),
}


def _fmt_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return f"{dt.day} {dt.strftime('%b')} {dt.strftime('%H:%M')}"
    except Exception:
        return iso


class HistoryTab(QWidget):
    history_cleared = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(8)

        # Header row
        sec_row = QHBoxLayout()
        sec_row.setSpacing(8)
        sec_lbl = QLabel("RECENT LOGINS")
        sec_lbl.setStyleSheet(
            f"color:{GRAY4}; font-size:10px; font-weight:500; letter-spacing:1px; background:transparent;"
        )
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedHeight(24)
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background:{BTN}; border:1px solid {BORDER}; border-radius:4px;
                color:{GRAY4}; font-size:11px; padding:0 10px;
            }}
            QPushButton:hover {{ background:{BTN_HV}; color:{TEXT}; }}
        """)
        self._clear_btn.clicked.connect(self._on_clear)
        sec_row.addWidget(sec_lbl)
        sec_row.addStretch()
        sec_row.addWidget(self._clear_btn)
        root.addLayout(sec_row)

        # Scroll area for entries
        self._entries_widget = QWidget()
        self._entries_widget.setStyleSheet("background:transparent;")
        self._entries_layout = QVBoxLayout(self._entries_widget)
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self._entries_layout.setSpacing(4)
        self._entries_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._entries_widget)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border:none; background:transparent; }}
            QScrollArea > QWidget > QWidget {{ background:transparent; }}
            QScrollBar:vertical {{ background:{BG}; width:4px; border:none; margin:0; }}
            QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:2px; min-height:20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        root.addWidget(scroll, 1)

        self._empty_lbl = QLabel("No login history yet.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"color:{GRAY5}; font-size:13px; background:transparent;")
        self._empty_lbl.hide()
        root.addWidget(self._empty_lbl)

        self.refresh()

    def refresh(self) -> None:
        while self._entries_layout.count() > 1:
            item = self._entries_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        entries = load_history()

        if not entries:
            self._empty_lbl.show()
            return

        self._empty_lbl.hide()
        for entry in entries:
            row = self._make_row(entry)
            self._entries_layout.insertWidget(self._entries_layout.count() - 1, row)

    def _make_row(self, entry: dict) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(38)
        frame.setStyleSheet(
            f"QFrame {{ background:{ITEM}; border-radius:5px; border:none; }}"
        )
        hl = QHBoxLayout(frame)
        hl.setContentsMargins(12, 0, 12, 0)
        hl.setSpacing(8)

        game = entry.get("game", "")
        if game in GAME_PILLS:
            color, abbr = GAME_PILLS[game]
            pill = QLabel(abbr)
            pill.setStyleSheet(
                f"color:{color}; background:transparent;"
                f"border:1px solid {color}; border-radius:3px;"
                f"font-size:10px; padding:1px 5px;"
            )
            hl.addWidget(pill)

        uname = QLabel(entry.get("username", ""))
        uname.setStyleSheet(f"color:{TEXT}; font-size:13px; font-weight:500; background:transparent;")
        hl.addWidget(uname)
        hl.addStretch()

        ts_str = _fmt_ts(entry.get("timestamp", ""))
        ts_lbl = QLabel(ts_str)
        ts_lbl.setStyleSheet(f"color:{GRAY5}; font-size:11px; background:transparent;")
        hl.addWidget(ts_lbl)

        return frame

    def _on_clear(self) -> None:
        clear_history()
        self.refresh()
        self.history_cleared.emit()
