from __future__ import annotations

import requests
from PyQt6.QtCore import QThread, pyqtSignal


class UpdateChecker(QThread):
    update_found = pyqtSignal(str, str)  # (new_version, html_url)

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def run(self) -> None:
        try:
            r = requests.get(
                "https://api.github.com/repos/Eadroma/RiotAccountManager/releases/latest",
                timeout=5,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            r.raise_for_status()
            data = r.json()
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
