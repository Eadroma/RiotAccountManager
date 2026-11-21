import base64
import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet

import account_storage
import exporter
from account_storage import AccountStorage, StorageError
from exporter import export_accounts, import_accounts
from ui import settings_tab
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

    def test_export_is_atomic_and_versioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backup.ambak"
            with mock.patch.object(exporter, "write_json_atomic", wraps=exporter.write_json_atomic) as w:
                export_accounts([FULL], str(path), "secret12")
            w.assert_called_once()
            self.assertEqual(json.loads(path.read_text())["version"], 1)

    def test_file_without_version_still_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.ambak"
            _write_backup(path, [asdict(FULL)], "secret12", version=None)
            self.assertEqual(import_accounts(str(path), "secret12"), [FULL])

    def test_malformed_files_raise_value_error_without_password(self):
        good = _encrypt([asdict(FULL)], "secret12")
        cases = {
            "missing salt": {"version": 1, "data": good["data"]},
            "missing data": {"version": 1, "salt": good["salt"]},
            "bad base64": {"version": 1, "salt": good["salt"], "data": "!!not base64!!"},
            "not an object": [good],
            "bad version": {**good, "version": 2},
        }
        bad_items = {
            "no username": [{"password": "p@ss wörd"}],
            "empty password": [{"username": "user", "password": ""}],
            "not a dict": ["p@ss wörd"],
            "not a list": {"username": "user", "password": "p@ss wörd"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.ambak"
            for name, payload in cases.items():
                with self.subTest(name):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        import_accounts(str(path), "secret12")
            for name, items in bad_items.items():
                with self.subTest(name):
                    _write_backup(path, items, "secret12")
                    with self.assertRaises(ValueError) as ctx:
                        import_accounts(str(path), "secret12")
                    self.assertNotIn("p@ss", str(ctx.exception))
                    self.assertNotIn("secret12", str(ctx.exception))


def _encrypt(items, password, version=1):
    salt = os.urandom(16)
    token = Fernet(exporter._derive_key(password, salt)).encrypt(json.dumps(items).encode("utf-8"))
    payload = {"salt": base64.b64encode(salt).decode("ascii"), "data": base64.b64encode(token).decode("ascii")}
    if version is not None:
        payload["version"] = version
    return payload


def _write_backup(path, items, password, version=1):
    Path(path).write_text(json.dumps(_encrypt(items, password, version)), encoding="utf-8")


class SettingsTabDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "accounts.json"
        mock.patch.object(account_storage, "STORAGE_FILE", self.file).start()
        mock.patch.object(account_storage, "keyring", FakeKeyring()).start()
        self.dialogs = mock.patch.object(settings_tab, "QInputDialog").start()
        self.files = mock.patch.object(settings_tab, "QFileDialog").start()
        self.addCleanup(mock.patch.stopall)
        self.storage = AccountStorage()
        self.tab = mock.MagicMock()
        self.tab._storage = self.storage

    def _status(self):
        return self.tab._data_status.setText.call_args.args[0]

    def test_short_export_password_is_refused(self):
        path = Path(self.tmp.name) / "out.ambak"
        self.files.getSaveFileName.return_value = (str(path), "")
        self.dialogs.getText.return_value = ("1234567", True)
        settings_tab.SettingsTab._on_export(self.tab)
        self.assertFalse(path.exists())
        self.assertIn("at least 8 characters", self._status())
        self.assertNotIn("1234567", self._status())

    def test_import_merges_and_saves_once(self):
        self.storage.save_accounts([AccountEntry("User", "old", last_used="2026-01-01T00:00:00"), AccountEntry("other", "x")])
        path = Path(self.tmp.name) / "in.ambak"
        export_accounts([AccountEntry("user", "new"), AccountEntry("third", "y")], str(path), "secret12")
        self.files.getOpenFileName.return_value = (str(path), "")
        self.dialogs.getText.return_value = ("secret12", True)
        with mock.patch.object(self.storage, "save_accounts", wraps=self.storage.save_accounts) as save:
            settings_tab.SettingsTab._on_import(self.tab)
        save.assert_called_once()
        self.assertEqual(
            [(a.username, a.password, a.last_used) for a in self.storage.load_accounts()],
            [("user", "new", "2026-01-01T00:00:00"), ("other", "x", ""), ("third", "y", "")],
        )
        self.tab.accounts_changed.emit.assert_called_once()

    def test_malformed_import_changes_nothing(self):
        self.storage.save_accounts([FULL])
        before = self.file.read_bytes()
        path = Path(self.tmp.name) / "in.ambak"
        _write_backup(path, [{"username": "ok", "password": "fine"}, {"password": "p@ss wörd"}], "secret12")
        self.files.getOpenFileName.return_value = (str(path), "")
        self.dialogs.getText.return_value = ("secret12", True)
        settings_tab.SettingsTab._on_import(self.tab)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertIn("entry 2", self._status())
        self.assertNotIn("p@ss", self._status())
        self.tab.accounts_changed.emit.assert_not_called()


class HotkeyTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_hotkey("Ctrl+Shift+A"), (MOD_CONTROL | MOD_SHIFT, ord("A")))
        self.assertEqual(parse_hotkey("ctrl+F5"), (MOD_CONTROL, 0x74))
        self.assertEqual(parse_hotkey(""), (0, 0))


if __name__ == "__main__":
    unittest.main()
