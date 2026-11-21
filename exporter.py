from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import asdict
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from account_storage import write_json_atomic
from models import AccountEntry

FORMAT_VERSION = 1


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def export_accounts(accounts: list[AccountEntry], path: str, password: str) -> None:
    plaintext = json.dumps([asdict(a) for a in accounts], indent=2).encode("utf-8")

    salt = os.urandom(16)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(plaintext)

    payload = {
        "version": FORMAT_VERSION,
        "salt": base64.b64encode(salt).decode("ascii"),
        "data": base64.b64encode(token).decode("ascii"),
    }
    write_json_atomic(Path(path), payload)


def _b64_field(payload: dict, name: str) -> bytes:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Invalid backup file: missing '{name}' field.")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"Invalid backup file: '{name}' is not valid base64.") from None


def _validate_items(items) -> None:
    # Messages only name the entry position, never its content (it holds passwords).
    if not isinstance(items, list):
        raise ValueError("Invalid backup file: account list expected.")
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid backup file: entry {i} is not an account.")
        for name in ("username", "password"):
            value = item.get(name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"Invalid backup file: entry {i} has no valid '{name}'.")


def import_accounts(path: str, password: str) -> list[AccountEntry]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except ValueError:
        raise ValueError("Invalid backup file: not a readable .ambak file.") from None
    if not isinstance(payload, dict):
        raise ValueError("Invalid backup file: unexpected format.")
    # Files written before the "version" field existed are read as version 1.
    if payload.get("version", FORMAT_VERSION) != FORMAT_VERSION:
        raise ValueError("Invalid backup file: unsupported version.")

    salt = _b64_field(payload, "salt")
    token = _b64_field(payload, "data")
    key = _derive_key(password, salt)

    try:
        plaintext = Fernet(key).decrypt(token)
    except InvalidToken:
        raise ValueError("Wrong password or corrupted file.") from None

    try:
        items = json.loads(plaintext.decode("utf-8"))
    except ValueError:
        raise ValueError("Invalid backup file: unreadable content.") from None
    _validate_items(items)
    return [AccountEntry.from_dict(item) for item in items]
