import sys
import types
import unittest
from unittest import mock

import win32con

import riot_ui_login
from riot_ui_login import RiotUIError

FAKE_PASSWORD = "Hunter2-fake-pw"
HWND = 1234


def _edit(is_password: bool):
    """Fake UIA edit control whose value is stored by SetValue."""
    edit = mock.MagicMock()
    edit.element_info.element.CurrentIsPassword = int(is_password)
    state = {"value": ""}

    def set_value(text):
        state["value"] = "●" * len(text) if is_password else text
        edit.typed = text

    edit.typed = None
    edit.iface_value.SetValue.side_effect = set_value
    type(edit.iface_value).CurrentValue = mock.PropertyMock(side_effect=lambda: state["value"])
    return edit


class LoginFormTests(unittest.TestCase):
    def setUp(self):
        self.edits = []
        window = mock.MagicMock()
        window.descendants.side_effect = lambda control_type: list(self.edits)
        desktop = mock.MagicMock()
        desktop.return_value.window.return_value = window
        fake_pywinauto = types.ModuleType("pywinauto")
        fake_pywinauto.Desktop = desktop
        for patcher in (
            mock.patch.dict(sys.modules, {"pywinauto": fake_pywinauto}),
            mock.patch.object(sys, "coinit_flags", 0, create=True),
            mock.patch.object(riot_ui_login, "pythoncom"),
            mock.patch.object(riot_ui_login, "win32api"),
            mock.patch.object(riot_ui_login, "_bring_to_front_reliable"),
            mock.patch.object(riot_ui_login, "_FIELDS_TIMEOUT", 0.0),
            mock.patch.object(riot_ui_login.time, "sleep"),
        ):
            patcher.start()
        self.addCleanup(mock.patch.stopall)
        self.win32gui = mock.patch.object(riot_ui_login, "win32gui").start()
        self.win32gui.IsIconic.return_value = False
        self.win32gui.GetForegroundWindow.return_value = HWND

    def _login(self):
        riot_ui_login.login("someone", FAKE_PASSWORD, hwnd=HWND)

    def _enter_pressed(self):
        return any(
            c.args[0] == win32con.VK_RETURN
            for c in riot_ui_login.win32api.keybd_event.call_args_list
        )

    def test_fields_in_normal_order(self):
        user, pw = _edit(False), _edit(True)
        self.edits = [user, pw]
        self._login()
        self.assertEqual(user.typed, "someone")
        self.assertEqual(pw.typed, FAKE_PASSWORD)
        self.assertTrue(self._enter_pressed())

    def test_password_field_first(self):
        pw, user = _edit(True), _edit(False)
        self.edits = [pw, user]
        self._login()
        self.assertEqual(user.typed, "someone")
        self.assertEqual(pw.typed, FAKE_PASSWORD)

    def _assert_refused(self):
        with self.assertRaises(RiotUIError) as ctx:
            self._login()
        self.assertNotIn(FAKE_PASSWORD, str(ctx.exception))
        for edit in self.edits:
            edit.iface_value.SetValue.assert_not_called()
        self.assertFalse(self._enter_pressed())

    def test_two_fields_without_password_refused(self):
        self.edits = [_edit(False), _edit(False)]
        self._assert_refused()

    def test_two_password_fields_refused(self):
        self.edits = [_edit(True), _edit(True)]
        self._assert_refused()

    def test_three_fields_refused(self):
        self.edits = [_edit(False), _edit(True), _edit(False)]
        self._assert_refused()

    def test_no_fields_refused(self):
        self._assert_refused()

    def test_waits_until_form_is_ready(self):
        user, pw = _edit(False), _edit(True)
        answers = iter([[], [user, pw]])
        window = sys.modules["pywinauto"].Desktop.return_value.window.return_value
        window.descendants.side_effect = lambda control_type: next(answers)
        with mock.patch.object(riot_ui_login, "_FIELDS_TIMEOUT", 10.0):
            self._login()
        self.assertEqual(user.typed, "someone")

    def test_no_enter_without_focus(self):
        self.edits = [_edit(False), _edit(True)]
        self.win32gui.GetForegroundWindow.return_value = HWND + 1
        with self.assertRaises(RiotUIError) as ctx:
            self._login()
        self.assertNotIn(FAKE_PASSWORD, str(ctx.exception))
        self.assertFalse(self._enter_pressed())


if __name__ == "__main__":
    unittest.main()
