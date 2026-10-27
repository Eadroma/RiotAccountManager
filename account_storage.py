import json
import os
from dataclasses import asdict
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


class StorageError(Exception):
    """accounts.json can't be read safely; it must not be overwritten."""


def write_json_atomic(path: Path, data) -> None:
    # Write a sibling file then swap it in, so a crash never leaves a half-written file.
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.replace(tmp, path)


class AccountStorage:
    def __init__(self) -> None:
        self._key = self._load_or_create_key()
        self._fernet = Fernet(self._key)

    def _load_or_create_key(self) -> bytes:
        stored_key = keyring.get_password(SERVICE_NAME, KEY_NAME)
        if stored_key:
            return stored_key.encode("utf-8")

        if self._read_raw():
            raise StorageError(
                "The encryption key is missing from Windows Credential Manager, so the saved "
                f"accounts in {STORAGE_FILE} can't be decrypted. The file was left untouched. "
                "Restore the key or import a backup (.ambak)."
            )
        key = Fernet.generate_key()
        keyring.set_password(SERVICE_NAME, KEY_NAME, key.decode("utf-8"))
        return key

    def _encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def _decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _read_raw() -> list:
        if not STORAGE_FILE.exists():
            return []
        try:
            with STORAGE_FILE.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            raise StorageError(f"{STORAGE_FILE} is unreadable or corrupt: {exc}") from exc
        if not isinstance(raw, list):
            raise StorageError(f"{STORAGE_FILE} has an unexpected format.")
        return raw

    def load_accounts(self) -> list[AccountEntry]:
        accounts = []
        for item in self._read_raw():
            try:
                accounts.append(
                    AccountEntry.from_dict({**item, "password": self._decrypt(item["password"])})
                )
            except Exception as exc:
                # Skipping would drop the account on the next save; stop instead.
                raise StorageError(
                    f"Could not decrypt account '{item.get('username', '?')}' in {STORAGE_FILE}. "
                    "The file was left untouched."
                ) from exc
        return accounts

    def save_accounts(self, accounts: list[AccountEntry]) -> None:
        write_json_atomic(
            STORAGE_FILE,
            [{**asdict(a), "password": self._encrypt(a.password)} for a in accounts],
        )

    def add_or_update(self, entry: AccountEntry) -> None:
        accounts = self.load_accounts()
        for i, account in enumerate(accounts):
            if account.username.lower() == entry.username.lower():
                entry.last_used = entry.last_used or account.last_used
                accounts[i] = entry
                break
        else:
            accounts.append(entry)
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
