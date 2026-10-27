# CLAUDE.md

Windows-only PyQt6 desktop app that stores several Riot Games accounts locally, logs into the
Riot Client through Windows UI Automation, and can then start the account's game.
Single user, single machine. Version lives in `version.py`. The user mainly runs the built exe
(`dist\AccountManager.exe`), so rebuild after changes they want to try.

## Run / build / test

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py                 # add --minimized to start in tray
python -m unittest discover -s tests -t .
pyinstaller --noconfirm --onefile --windowed --icon=icon.ico --name=AccountManager --add-data "icon.ico;." main.py
```

Only one instance runs at a time: a second launch just raises the first and exits. Stop a running
`AccountManager.exe` before rebuilding or testing new code.

For a UI check without touching real data, run with `QT_QPA_PLATFORM=offscreen` and stub
`AccountStorage`, `login_history.add_login`, `UpdateChecker.start`, `GlobalHotkeyThread.start`
and `LoginWorker`.

CI (`.github/workflows/release.yml`): runs the tests, then every push to `master` rebuilds the exe
and replaces the `latest` prerelease; a `v*.*.*` tag attaches the exe to that versioned release.
Bump `version.py` before tagging, because the in-app update check compares against it.

## Layout

| File | Job |
|------|-----|
| `main.py` | Entry point, single-instance guard via `QLocalServer`; shows `StorageError` and exits |
| `models.py` | `AccountEntry` dataclass (plaintext in memory), `from_dict` |
| `account_storage.py` | `%APPDATA%\RiotAccountManager\accounts.json`; password Fernet-encrypted, key in Windows Credential Manager (`keyring`). Defines `DATA_DIR`, `write_json_atomic`, `StorageError` |
| `settings_storage.py` | `AppSettings` dataclass → `settings.json`; Riot Client auto-detect; startup registry key |
| `login_history.py` | `history.json`, last 500 logins |
| `exporter.py` | Password-protected `.ambak` backup (PBKDF2 + Fernet) |
| `riot_ui_login.py` | Fills the Riot Client sign-in form through UI Automation and presses Enter |
| `riot_process.py` | Kill / relaunch the Riot Client, wait for the login form, `launch_game` |
| `global_hotkey.py` | `RegisterHotKey` message loop in a `QThread` |
| `updater.py` | GitHub latest-release check in a `QThread` (stdlib `urllib`) |
| `ui/main_window.py` | Main window: account list (groups, drag reorder, filters), form, tray, key handling |
| `ui/login_worker.py` | `QThread` running login (+ optional game launch) so the UI stays responsive |
| `ui/settings_tab.py`, `ui/history_tab.py` | The other two tabs |
| `ui/theme.py` | Palette, `GAMES`, `GAME_PILLS`, `GROUP_COLORS` |
| `tests/test_core.py` | Storage, export/import and hotkey parsing tests (stdlib `unittest`) |

## Things to know before editing

- **Account indices**: list widgets keep `_idx` = position in `storage.load_accounts()`.
  `_selected_row` is a position in `_item_widgets` (display order, grouped), not an account index;
  use `_selected_acc_idx()`. `_refresh_list(keep_acc=<account index>)` reloads from disk and reselects.
- Storage is read-modify-write of the whole JSON file on every change; most UI actions reload
  from disk instead of trusting `self.accounts`. All JSON files are written with `write_json_atomic`.
- **Never let a load silently drop accounts**: any unreadable file or undecryptable entry raises
  `StorageError` so the next save can't overwrite the data. A missing keyring key with existing
  accounts also raises instead of generating a new key.
- Serialisation goes through `dataclasses.asdict` / `AccountEntry.from_dict`, so a new
  `AccountEntry` field is stored, exported and imported automatically.
- Saving with an account selected edits that account in place (rename allowed, name clash refused).
- All logins (window, double-click, Enter, tray) go through `_start_login`.
- The app-wide key filter only acts when this window is active and the Accounts tab is shown.
- An unhandled exception inside a Qt slot aborts the whole app under PyQt6. Keep slot code safe.
- Passwords must never be logged, shown in errors or written unencrypted.
- Riot Client window is found by exact title `"Riot Client"`. The sign-in inputs are found through
  UI Automation (pywinauto `uia` backend): the form must have exactly 2 `Edit` controls
  (username, password), filled with `ValuePattern.SetValue` and read back to confirm (the
  password only reports bullets, so its length is compared), then Enter is sent only if the Riot
  window has focus. No mouse positions, no clipboard. Chromium builds the accessibility tree
  lazily, so the first query can return nothing (hence the retry loop), and the window must not
  be minimized.
- `_form_fields` runs in `LoginWorker` threads and joins the COM multithreaded apartment
  (`sys.coinit_flags`) before pywinauto is first imported. Don't import pywinauto at module level
  or on the Qt main thread, which is an OLE single-threaded apartment.
- Game launch (`riot_process.launch_game`) uses the Riot Client's local API: port and password
  come from `%LOCALAPPDATA%\Riot Games\Riot Client\Config\lockfile`, Basic auth `riot:<password>`,
  self-signed HTTPS on 127.0.0.1. Once `GET /rso-auth/v1/authorization` returns 200 it sends
  `POST /product-launcher/v1/products/<id>/patchlines/live` (what the Play button does) and
  waits up to 15 s for the game process (`LeagueClient.exe` / `VALORANT.exe`), resending until
  120 s (captcha/2FA). Right after sign-in the client already answers 200 but ignores Play for a
  few seconds, so success is judged by the process, not the HTTP answer. That POST stays open
  while the game starts, so a read timeout counts as sent. Don't use `RiotClientServices.exe --launch-product`: on a running
  client it only opens the game tab. Product ids are in `riot_process.GAME_PRODUCTS` (TFT →
  `league_of_legends`; Wild Rift has no PC client). The worker emits `finished_ok` before the
  launch, so a failed launch doesn't undo the login. Controlled by
  `AppSettings.launch_game_after_login`.
- The Riot-Client watcher (auto-show when the client opens) is muted while a login runs.

## Known issues (not yet fixed)

1. Passwords are `.strip()`ped on save/login, so leading/trailing spaces are lost.
2. README claims no external requests, but `updater.py` calls GitHub.
3. `GlobalHotkeyThread.stop_thread` does nothing if called before the thread stored its id, and
   `_start_hotkey` then waits forever. Rare now that the hotkey restarts only when it changes.
