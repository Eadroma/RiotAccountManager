from __future__ import annotations

import base64
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
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
        subprocess.run(
            ["taskkill", "/F", "/IM", name],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    time.sleep(1)


def launch_riot_client(exe_path: str) -> None:
    if not Path(exe_path).exists():
        raise FileNotFoundError(f"Riot Client not found at: {exe_path}")
    subprocess.Popen([exe_path])


# (Riot product id, process that shows the game started). Wild Rift is mobile-only;
# TFT runs inside the League client.
GAME_PRODUCTS = {
    "League of Legends": ("league_of_legends", "LeagueClient.exe"),
    "TFT": ("league_of_legends", "LeagueClient.exe"),
    "Valorant": ("valorant", "VALORANT.exe"),
}


_LOCKFILE = Path(os.getenv("LOCALAPPDATA", "")) / "Riot Games" / "Riot Client" / "Config" / "lockfile"
_LAUNCH_TIMEOUT = 120.0     # leaves time for captcha / 2FA prompts
_LAUNCH_CONFIRM_WAIT = 15.0  # how long a Play request gets to show a game process


def _client_api(path: str, *, method: str = "GET", timeout: float = 3.0) -> int:
    """Call the Riot Client's local API (the one its own UI uses). Returns the HTTP status."""
    _name, _pid, port, password, _proto = _LOCKFILE.read_text(encoding="utf-8").split(":")
    token = base64.b64encode(f"riot:{password}".encode()).decode()
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}{path}", method=method, headers={"Authorization": f"Basic {token}"}
    )
    # The client serves a self-signed certificate, on 127.0.0.1 only.
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def launch_game(game: str) -> bool:
    """Press Play once the Riot Client has signed in. False if this game can't be launched.

    Right after sign-in the client reports "signed in" but still ignores Play
    requests for a few seconds, so keep asking until the game process appears.
    """
    if game not in GAME_PRODUCTS:
        return False
    product, process = GAME_PRODUCTS[game]

    deadline = time.monotonic() + _LAUNCH_TIMEOUT
    last_status = 0
    while time.monotonic() < deadline:
        if _process_running(process):
            return True
        if _try_api("/rso-auth/v1/authorization") == 200:
            last_status = _try_api(
                f"/product-launcher/v1/products/{product}/patchlines/live", method="POST"
            )
            confirm_until = time.monotonic() + _LAUNCH_CONFIRM_WAIT
            while time.monotonic() < confirm_until:
                if _process_running(process):
                    return True
                time.sleep(1.0)
        else:
            time.sleep(1.0)
    detail = f" (last answer: HTTP {last_status})" if last_status >= 400 else ""
    raise RiotUIError(f"Signed in, but {game} did not start{detail}. Press Play in the Riot Client.")


def _try_api(path: str, *, method: str = "GET") -> int:
    # The lockfile and port change while the client restarts; treat that as "not ready yet".
    try:
        return _client_api(path, method=method)
    except TimeoutError:
        return 200  # a Play request stays open while the game starts
    except (OSError, ValueError):
        return 0


def _process_running(image_name: str) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout
    return image_name.lower() in out.lower()


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
