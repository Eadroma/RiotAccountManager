from __future__ import annotations

import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from models import AccountEntry


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def export_accounts(accounts: list[AccountEntry], path: str, password: str) -> None:
    plaintext = json.dumps(
        [
            {
                "username": a.username,
                "password": a.password,
                "note": a.note,
                "last_used": a.last_used,
                "game": a.game,
                "group": a.group,
            }
            for a in accounts
        ],
        indent=2,
    ).encode("utf-8")

    salt = os.urandom(16)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(plaintext)

    payload = {
        "salt": base64.b64encode(salt).decode("ascii"),
        "data": base64.b64encode(token).decode("ascii"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def import_accounts(path: str, password: str) -> list[AccountEntry]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    salt = base64.b64decode(payload["salt"])
    token = base64.b64decode(payload["data"])
    key = _derive_key(password, salt)

    try:
        plaintext = Fernet(key).decrypt(token)
    except InvalidToken:
        raise ValueError("Wrong password or corrupted file.")

    items = json.loads(plaintext.decode("utf-8"))
    return [
        AccountEntry(
            username=item["username"],
            password=item["password"],
            note=item.get("note", ""),
            last_used=item.get("last_used", ""),
            game=item.get("game", ""),
            group=item.get("group", ""),
        )
        for item in items
    ]
