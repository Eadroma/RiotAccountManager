import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import account_storage
from account_storage import AccountStorage, StorageError
from exporter import export_accounts, import_accounts
from global_hotkey import MOD_CONTROL, MOD_SHIFT, parse_hotkey
from models import AccountEntry

FULL = AccountEntry("user", "p@ss wörd", note="main", last_used="2026-04-13T14:23:00", game="Valorant", group="g1")


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "accounts.json"
        self.keyring = FakeKeyring()
        mock.patch.object(account_storage, "STORAGE_FILE", self.file).start()
        mock.patch.object(account_storage, "keyring", self.keyring).start()
        self.addCleanup(mock.patch.stopall)

    def test_round_trip_keeps_every_field(self):
        AccountStorage().save_accounts([FULL])
        self.assertEqual(AccountStorage().load_accounts(), [FULL])
        self.assertNotIn("p@ss", self.file.read_text(encoding="utf-8"))

    def test_lost_key_refuses_instead_of_wiping(self):
        AccountStorage().save_accounts([FULL])
        before = self.file.read_bytes()
        self.keyring.store.clear()
        with self.assertRaises(StorageError):
            AccountStorage()
        self.assertEqual(self.file.read_bytes(), before)

    def test_wrong_key_refuses(self):
        AccountStorage().save_accounts([FULL])
        self.keyring.store.clear()
        self.keyring.set_password(account_storage.SERVICE_NAME, account_storage.KEY_NAME, "x" * 43 + "=")
        with self.assertRaises(StorageError):
            AccountStorage().load_accounts()

    def test_corrupt_file_refuses(self):
        self.file.write_text("{not json", encoding="utf-8")
        with self.assertRaises(StorageError):
            AccountStorage()


class ExportTests(unittest.TestCase):
    def test_round_trip_keeps_every_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "backup.ambak")
            export_accounts([FULL], path, "secret")
            self.assertEqual(import_accounts(path, "secret"), [FULL])
            with self.assertRaises(ValueError):
                import_accounts(path, "wrong")
            self.assertNotIn("p@ss", json.dumps(json.loads(Path(path).read_text())))


class HotkeyTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_hotkey("Ctrl+Shift+A"), (MOD_CONTROL | MOD_SHIFT, ord("A")))
        self.assertEqual(parse_hotkey("ctrl+F5"), (MOD_CONTROL, 0x74))
        self.assertEqual(parse_hotkey(""), (0, 0))


if __name__ == "__main__":
    unittest.main()
