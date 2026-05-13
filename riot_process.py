from __future__ import annotations

import subprocess
import time
from pathlib import Path

import win32gui

from riot_ui_login import RiotUIError

RIOT_PROCESSES = [
    "RiotClientServices.exe",
    "RiotClientUx.exe",
    "RiotClientUxRender.exe",
    "LeagueClient.exe",
    "LeagueClientUx.exe",
]

_LOGIN_FORM_MIN_WIDTH = 900
_POLL_INTERVAL   = 0.5
_POLL_TIMEOUT    = 45.0
_STABLE_POLLS    = 4     # consecutive polls at full size before we consider it stable (~2s)
_FORM_LOAD_WAIT  = 4.0   # extra seconds after stable for the login form to render inside Electron


def kill_riot_processes() -> None:
    for name in RIOT_PROCESSES:
        subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
    time.sleep(1)


def launch_riot_client(exe_path: str) -> None:
    if not Path(exe_path).exists():
        raise FileNotFoundError(f"Riot Client not found at: {exe_path}")
    subprocess.Popen([exe_path])


def wait_for_login_window(timeout: float = _POLL_TIMEOUT) -> int:
    """Poll until Riot Client shows the full-size login form (not the splash).

    The Electron window briefly appears at full size while still loading — we
    wait for it to stay at full size for several consecutive polls, then add
    extra time for the login form to finish rendering inside the web view.
    """
    deadline = time.monotonic() + timeout
    stable = 0
    while time.monotonic() < deadline:
        hwnd = win32gui.FindWindow(None, "Riot Client")
        if hwnd:
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            if (r - l) >= _LOGIN_FORM_MIN_WIDTH:
                stable += 1
                if stable >= _STABLE_POLLS:
                    time.sleep(_FORM_LOAD_WAIT)
                    return hwnd
            else:
                stable = 0
        else:
            stable = 0
        time.sleep(_POLL_INTERVAL)
    raise RiotUIError(
        "Timed out waiting for Riot Client login window. "
        "Make sure the Riot Client opened correctly."
    )
