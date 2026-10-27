from __future__ import annotations

import json
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal

_LATEST_URL = "https://api.github.com/repos/Eadroma/RiotAccountManager/releases/latest"


class UpdateChecker(QThread):
    update_found = pyqtSignal(str, str)  # (new_version, html_url)

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                _LATEST_URL,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "AccountManager"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.load(resp)
            tag = data.get("tag_name", "").lstrip("v")
            url = data.get("html_url", "")
            if tag and url and _version_gt(tag, self._current):
                self.update_found.emit(tag, url)
        except Exception:
            pass


def _version_gt(a: str, b: str) -> bool:
    try:
        return tuple(int(x) for x in a.split(".")) > tuple(int(x) for x in b.split("."))
    except ValueError:
        return False
