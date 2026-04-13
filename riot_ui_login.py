"""UI automation for the Riot Client login screen.

Since the Riot Client is Electron-based and doesn't expose its HTML input
fields via Windows accessibility APIs, we drive it by focusing the window
and simulating keyboard/mouse input.
"""

import time

import pyautogui
import pyperclip
import win32con
import win32gui

pyautogui.FAILSAFE = True  # move mouse to corner to abort
pyautogui.PAUSE = 0.05

WINDOW_TITLE = "Riot Client"

# Position of each field as a fraction of the window's width/height.
# These match the Riot Client's default sign-in layout.
_USERNAME_X_FRAC = 0.07
_USERNAME_Y_FRAC = 0.327
_PASSWORD_Y_FRAC = 0.400


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


def _bring_to_front(hwnd: int) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.35)


def _field_coords(hwnd: int) -> tuple[tuple[int, int], tuple[int, int]]:
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = r - l, b - t
    cx = l + int(w * _USERNAME_X_FRAC)
    username_pos = (cx, t + int(h * _USERNAME_Y_FRAC))
    password_pos = (cx, t + int(h * _PASSWORD_Y_FRAC))
    return username_pos, password_pos


def _fill_field(pos: tuple[int, int], text: str) -> None:
    """Click a field and paste text via clipboard (handles special characters)."""
    pyautogui.click(*pos)
    time.sleep(0.15)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.05)


def login(username: str, password: str) -> None:
    """Fill in the Riot Client sign-in form and submit it.

    Raises RiotUIError if the window can't be found.
    """
    hwnd = _find_window()
    _bring_to_front(hwnd)

    username_pos, password_pos = _field_coords(hwnd)

    _fill_field(username_pos, username)
    _fill_field(password_pos, password)

    # Submit with Enter
    pyautogui.press("enter")

    # Clear clipboard so the password doesn't linger
    pyperclip.copy("")
