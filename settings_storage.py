from __future__ import annotations

import json
import subprocess
import sys
import winreg
from dataclasses import asdict, dataclass
from pathlib import Path

from account_storage import DATA_DIR

SETTINGS_FILE = DATA_DIR / "settings.json"
_STARTUP_KEY   = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_VALUE = "RiotAccountManager"

_COMMON_PATHS = [
    r"C:\Riot Games\Riot Client\RiotClientServices.exe",
    r"C:\Program Files\Riot Games\Riot Client\RiotClientServices.exe",
    r"C:\Program Files (x86)\Riot Games\Riot Client\RiotClientServices.exe",
]


@dataclass
class AppSettings:
    riot_client_path: str = ""
    launch_on_startup: bool = False
    start_minimized: bool = False
    minimize_to_tray_on_close: bool = True
    auto_minimize_after_login: bool = False
    disconnect_first_default: bool = False


def load_settings() -> AppSettings:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        valid = set(AppSettings.__dataclass_fields__)
        return AppSettings(**{k: v for k, v in data.items() if k in valid})
    except Exception:
        return AppSettings()


def save_settings(s: AppSettings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")


def auto_detect_riot_client() -> str:
    for p in _COMMON_PATHS:
        if Path(p).exists():
            return p
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Riot Games, Inc\Riot Client",
        )
        loc, _ = winreg.QueryValueEx(key, "InstallLocation")
        winreg.CloseKey(key)
        candidate = Path(loc) / "RiotClientServices.exe"
        if candidate.exists():
            return str(candidate)
    except OSError:
        pass
    return ""


def set_startup(enabled: bool, exe_path: str) -> None:
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        _STARTUP_KEY,
        access=winreg.KEY_SET_VALUE,
    )
    try:
        if enabled:
            winreg.SetValueEx(key, _STARTUP_VALUE, 0, winreg.REG_SZ, f'"{exe_path}" --minimized')
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_VALUE)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def open_data_folder() -> None:
    subprocess.Popen(["explorer", str(DATA_DIR)])
