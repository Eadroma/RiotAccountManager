from __future__ import annotations

import ctypes
import ctypes.wintypes

from PyQt6.QtCore import QThread, pyqtSignal

MOD_ALT     = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT   = 0x0004
MOD_WIN     = 0x0008

_HOTKEY_ID = 0xBEEF
_WM_HOTKEY = 0x0312
_WM_QUIT   = 0x0012

_MOD_NAMES = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}


def parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """Parse 'Ctrl+Shift+A' → (win_modifiers, vk_code). Returns (0, 0) on failure."""
    if not hotkey_str.strip():
        return (0, 0)
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    modifiers = 0
    vk = 0
    for part in parts:
        if part in _MOD_NAMES:
            modifiers |= _MOD_NAMES[part]
        elif len(part) == 1 and part.isalpha():
            vk = ord(part.upper())
        elif len(part) == 1 and part.isdigit():
            vk = ord(part)
        elif part.startswith("f") and part[1:].isdigit():
            n = int(part[1:])
            if 1 <= n <= 24:
                vk = 0x6F + n  # VK_F1=0x70
    return (modifiers, vk)


class GlobalHotkeyThread(QThread):
    triggered = pyqtSignal()

    def __init__(self, hotkey_str: str, parent=None) -> None:
        super().__init__(parent)
        self._modifiers, self._vk = parse_hotkey(hotkey_str)
        self._thread_id: int = 0

    def run(self) -> None:
        if not self._modifiers or not self._vk:
            return
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, _HOTKEY_ID, self._modifiers, self._vk):
            return
        self._thread_id = int(self.currentThreadId())
        msg = ctypes.wintypes.MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                self.triggered.emit()
        user32.UnregisterHotKey(None, _HOTKEY_ID)

    def stop_thread(self) -> None:
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
