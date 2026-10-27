"""UI automation for the Riot Client login screen.

The Riot Client is Electron-based. Chromium exposes the sign-in inputs through
UI Automation once a UIA client queries the window, so we set the field values
directly (no mouse clicks, no clipboard) and press Enter.
"""

import sys
import time
import warnings

import pythoncom
import win32api
import win32con
import win32gui

WINDOW_TITLE = "Riot Client"

_FIELDS_TIMEOUT = 10.0


class RiotUIError(Exception):
    pass


def _find_window() -> int:
    hwnd = win32gui.FindWindow(None, WINDOW_TITLE)
    if not hwnd:
        raise RiotUIError(
            "Riot Client window not found. Make sure the Riot Client is open "
            "and showing the sign-in screen."
        )
    return hwnd


def _bring_to_front_reliable(hwnd: int, retries: int = 3) -> None:
    for _ in range(retries):
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.35)
        if win32gui.GetForegroundWindow() == hwnd:
            return
    raise RiotUIError("Could not bring Riot Client to foreground.")


def _form_fields(hwnd: int):
    """Return the (username, password) UIA edit controls of the sign-in form."""
    # Runs in LoginWorker threads: use the MTA so the UIA object pywinauto
    # caches on first import stays usable from later worker threads.
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    sys.coinit_flags = pythoncom.COINIT_MULTITHREADED
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pywinauto warns that coinit_flags is set
        from pywinauto import Desktop

    window = Desktop(backend="uia").window(handle=hwnd)
    deadline = time.monotonic() + _FIELDS_TIMEOUT
    while True:
        # Chromium builds its accessibility tree lazily after the first query.
        edits = window.descendants(control_type="Edit")
        if len(edits) == 2:
            return edits[0], edits[1]
        if time.monotonic() >= deadline:
            raise RiotUIError(
                "Sign-in fields not found. Make sure the Riot Client shows the "
                "sign-in screen."
            )
        time.sleep(0.5)


def _set_field(edit, text: str, *, masked: bool = False) -> None:
    """Set a field's value and wait until Chromium reports it back."""
    for _ in range(3):
        edit.iface_value.SetValue(text)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            value = edit.iface_value.CurrentValue
            # Password fields only report bullets, so compare the length.
            if (len(value) == len(text)) if masked else (value == text):
                return
            time.sleep(0.05)
    raise RiotUIError("Could not fill the sign-in form. Try again.")


def login(username: str, password: str, *, hwnd: int | None = None) -> None:
    """Fill in the Riot Client sign-in form and submit it.

    Raises RiotUIError if the window or its fields can't be found or focused.
    Pass hwnd to skip window lookup (e.g. after wait_for_login_window).
    """
    if hwnd is None:
        hwnd = _find_window()
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    username_edit, password_edit = _form_fields(hwnd)
    _set_field(username_edit, username)
    _set_field(password_edit, password, masked=True)

    _bring_to_front_reliable(hwnd)
    password_edit.set_focus()
    # Only Enter goes through the keyboard; never send it to another window.
    if win32gui.GetForegroundWindow() != hwnd:
        raise RiotUIError("Riot Client lost focus before submitting.")
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
