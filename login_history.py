from __future__ import annotations

import json
from datetime import datetime

from account_storage import DATA_DIR, write_json_atomic

HISTORY_FILE = DATA_DIR / "history.json"
MAX_ENTRIES = 500


def add_login(username: str, game: str = "") -> None:
    entries = _load_raw()
    entries.append({
        "username": username,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "game": game,
    })
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    write_json_atomic(HISTORY_FILE, entries)


def load_history() -> list[dict]:
    return list(reversed(_load_raw()))


def clear_history() -> None:
    write_json_atomic(HISTORY_FILE, [])


def _load_raw() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []
