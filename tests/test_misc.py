import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import login_history
import riot_process
import settings_storage
from settings_storage import AppSettings, load_settings
from updater import _version_gt


class VersionTests(unittest.TestCase):
    def test_compare(self):
        self.assertTrue(_version_gt("3.4.0", "3.3.0"))
        self.assertTrue(_version_gt("3.10.0", "3.9.0"))
        self.assertFalse(_version_gt("3.9.0", "3.10.0"))
        self.assertFalse(_version_gt("3.4.0", "3.4.0"))

    def test_prerelease(self):
        self.assertTrue(_version_gt("3.4.0-beta", "3.3.0"))
        self.assertFalse(_version_gt("3.4.0-beta", "3.4.0"))
        self.assertTrue(_version_gt("3.4.0", "3.4.0-rc1"))
        self.assertFalse(_version_gt("3.3.0", "3.4.0-rc1"))

    def test_garbage_is_not_newer(self):
        self.assertFalse(_version_gt("latest", "3.3.0"))


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "settings.json"
        patcher = mock.patch.object(settings_storage, "SETTINGS_FILE", self.file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_file_gives_defaults(self):
        self.assertEqual(load_settings(), AppSettings())

    def test_invalid_json_gives_defaults(self):
        self.file.write_text("{not json", encoding="utf-8")
        self.assertEqual(load_settings(), AppSettings())

    def test_unknown_key_ignored_and_values_kept(self):
        self.file.write_text(json.dumps({
            "global_hotkey": "Ctrl+F5",
            "start_minimized": True,
            "launch_game_after_login": False,
            "removed_option": 1,
        }), encoding="utf-8")
        s = load_settings()
        self.assertEqual(s.global_hotkey, "Ctrl+F5")
        self.assertTrue(s.start_minimized)
        self.assertFalse(s.launch_game_after_login)
        self.assertFalse(hasattr(s, "removed_option"))


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(login_history, "HISTORY_FILE", Path(self.tmp.name) / "history.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_add_newest_first(self):
        login_history.add_login("a", "Valorant")
        login_history.add_login("b")
        entries = login_history.load_history()
        self.assertEqual([e["username"] for e in entries], ["b", "a"])
        self.assertEqual(entries[1]["game"], "Valorant")

    def test_limit(self):
        raw = [{"username": f"u{i}", "timestamp": "", "game": ""} for i in range(login_history.MAX_ENTRIES)]
        login_history.HISTORY_FILE.write_text(json.dumps(raw), encoding="utf-8")
        login_history.add_login("new")
        entries = login_history.load_history()
        self.assertEqual(len(entries), login_history.MAX_ENTRIES)
        self.assertEqual(entries[0]["username"], "new")
        self.assertEqual(entries[-1]["username"], "u1")

    def test_clear(self):
        login_history.add_login("a")
        login_history.clear_history()
        self.assertEqual(login_history.load_history(), [])


class ClientApiTests(unittest.TestCase):
    def test_timeout_counts_as_sent(self):
        with mock.patch.object(riot_process, "_client_api", side_effect=TimeoutError):
            self.assertEqual(riot_process._try_api("/x", method="POST"), 200)

    def test_os_error_means_not_ready(self):
        with mock.patch.object(riot_process, "_client_api", side_effect=OSError):
            self.assertEqual(riot_process._try_api("/x"), 0)


if __name__ == "__main__":
    unittest.main()
