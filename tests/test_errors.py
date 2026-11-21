import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
from account_storage import StorageError
from models import AccountEntry
from ui.main_window import AccountManagerWindow

FAKE_PASSWORD = "Hunter2-fake-pw"


def _failing_slot():
    acc = AccountEntry("someone", FAKE_PASSWORD)
    raise RuntimeError(f"boom while handling {acc!r}")


class ExceptHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "error.log"
        mock.patch.object(main, "DATA_DIR", Path(self.tmp.name)).start()
        self.box = mock.patch.object(main, "QMessageBox").start()
        self.addCleanup(mock.patch.stopall)

    def _raise_and_hook(self):
        try:
            _failing_slot()
        except RuntimeError:
            main._excepthook(*sys.exc_info())

    def test_log_has_date_and_trace_but_no_password(self):
        self._raise_and_hook()
        text = self.log.read_text(encoding="utf-8")
        self.assertRegex(text, r"\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\]")
        self.assertIn("RuntimeError: boom while handling", text)
        self.assertIn("_failing_slot", text)
        self.assertNotIn(FAKE_PASSWORD, text)

    def test_message_box_shown_without_password(self):
        with mock.patch.object(main.QApplication, "instance", return_value=object()):
            self._raise_and_hook()
        self.box.critical.assert_called_once()
        self.assertNotIn(FAKE_PASSWORD, str(self.box.critical.call_args))

    def test_log_is_capped(self):
        self.log.write_text("x" * (main.LOG_MAX_BYTES + 1), encoding="utf-8")
        self._raise_and_hook()
        self.assertLess(self.log.stat().st_size, main.LOG_MAX_BYTES)
        self.assertIn("RuntimeError", self.log.read_text(encoding="utf-8"))

    def test_log_appends_below_cap(self):
        self._raise_and_hook()
        self._raise_and_hook()
        self.assertEqual(self.log.read_text(encoding="utf-8").count("RuntimeError: boom"), 2)


class StorageErrorInUiTests(unittest.TestCase):
    def test_save_shows_error_and_saves_nothing(self):
        win = mock.MagicMock()
        win.username_field.text.return_value = "user"
        win.password_field.text.return_value = FAKE_PASSWORD
        win.group_combo.currentData.return_value = ""
        error = StorageError("accounts.json is unreadable or corrupt")
        win.storage.load_accounts.side_effect = error
        AccountManagerWindow._save_account(win)
        win._storage_failed.assert_called_once_with(error)
        win.storage.save_accounts.assert_not_called()

    def test_storage_failed_shows_message(self):
        win = mock.MagicMock()
        AccountManagerWindow._storage_failed(win, StorageError("disk says no"))
        win._notify.assert_called_once_with("disk says no", error=True, auto_hide=False)


class PasswordSpacesTests(unittest.TestCase):
    def _win(self, username, password):
        win = mock.MagicMock()
        win.username_field.text.return_value = username
        win.password_field.text.return_value = password
        win.note_field.text.return_value = "  note  "
        win.group_combo.currentData.return_value = ""
        win.game_combo.currentText.return_value = "Valorant"
        win.storage.load_accounts.return_value = []
        win._selected_acc_idx.return_value = -1
        return win

    def test_save_keeps_password_spaces_and_strips_username(self):
        win = self._win("  user  ", " abc ")
        AccountManagerWindow._save_account(win)
        saved = win.storage.save_accounts.call_args.args[0]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].username, "user")
        self.assertEqual(saved[0].password, " abc ")
        self.assertEqual(saved[0].note, "note")

    def test_login_keeps_password_spaces_and_strips_username(self):
        win = self._win("  user  ", " abc ")
        AccountManagerWindow._login_account(win)
        win._start_login.assert_called_once_with("user", " abc ", win.disconnect_chk.isChecked())

    def test_blank_password_refused(self):
        for password in ("", "   "):
            win = self._win("user", password)
            AccountManagerWindow._save_account(win)
            win.storage.save_accounts.assert_not_called()
            win._set_status.assert_called_once_with("Username and password are required.", error=True)
            AccountManagerWindow._login_account(win)
            win._start_login.assert_not_called()


if __name__ == "__main__":
    unittest.main()
