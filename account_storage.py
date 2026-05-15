import json
import os
from pathlib import Path

import keyring
from cryptography.fernet import Fernet

from models import AccountEntry

SERVICE_NAME = "RiotAccountManager"
KEY_NAME = "account-encryption-key"

APPDATA = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
DATA_DIR = APPDATA / "RiotAccountManager"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_FILE = DATA_DIR / "accounts.json"


class AccountStorage:
    def __init__(self) -> None:
        self._key = self._load_or_create_key()
        self._fernet = Fernet(self._key)

    def _load_or_create_key(self) -> bytes:
        stored_key = keyring.get_password(SERVICE_NAME, KEY_NAME)
        if stored_key:
            return stored_key.encode("utf-8")

        key = Fernet.generate_key()
        keyring.set_password(SERVICE_NAME, KEY_NAME, key.decode("utf-8"))
        return key

    def _encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def _decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

    def load_accounts(self) -> list[AccountEntry]:
        if not STORAGE_FILE.exists():
            return []

        with STORAGE_FILE.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        accounts = []
        for item in raw:
            try:
                accounts.append(
                    AccountEntry(
                        username=item["username"],
                        password=self._decrypt(item["password"]),
                        note=item.get("note", ""),
                        last_used=item.get("last_used", ""),
                        game=item.get("game", ""),
                    )
                )
            except Exception:
                continue

        return accounts

    def save_accounts(self, accounts: list[AccountEntry]) -> None:
        data = [
            {
                "username": account.username,
                "password": self._encrypt(account.password),
                "note": account.note,
                "last_used": account.last_used,
                "game": account.game,
            }
            for account in accounts
        ]

        with STORAGE_FILE.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def add_or_update(self, username: str, password: str, note: str = "", game: str = "") -> None:
        accounts = self.load_accounts()
        found = False
        for account in accounts:
            if account.username.lower() == username.lower():
                account.password = password
                account.note = note
                account.game = game
                found = True
                break

        if not found:
            accounts.append(AccountEntry(username=username, password=password, note=note, game=game))

        self.save_accounts(accounts)

    def update_last_used(self, username: str) -> None:
        from datetime import datetime
        accounts = self.load_accounts()
        for account in accounts:
            if account.username.lower() == username.lower():
                account.last_used = datetime.now().isoformat(timespec="seconds")
                break
        self.save_accounts(accounts)

    def remove(self, username: str) -> None:
        accounts = [a for a in self.load_accounts() if a.username.lower() != username.lower()]
        self.save_accounts(accounts)
