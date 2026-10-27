# Changelog

## 3.3.0 — 2026-10-27

### New
- **Auto-start the game after login.** League of Legends and TFT accounts start League,
  Valorant accounts start Valorant. The app waits for the Riot Client sign-in to finish
  (captcha / 2FA included), presses Play through the client's local API and checks the game
  really started. Toggle it in Settings → LOGIN → "Start the account's game after login".

### Changed
- **Reliable login form filling.** The username and password fields are now found through
  Windows UI Automation instead of clicking at fixed positions, so window size and display
  scaling no longer make it miss the inputs. Each value is read back before submitting.
- **Credentials no longer go through the clipboard**, so passwords stay out of Windows
  clipboard history (Win+V) and cloud clipboard sync.
- Enter is only sent when the Riot Client window has focus.
- Changing a username in the form now renames the account instead of creating a duplicate.
- ▲ / ▼ move an account within its own group.
- Removing an account asks for confirmation.
- Login errors stay on screen until the next action.

### Fixed
- Logging in from the tray menu crashed the app.
- A missing encryption key or an unreadable `accounts.json` could silently wipe every saved
  account on the next save. The app now shows an error and leaves the file untouched.
  All data files are written atomically, so a crash mid-save can't corrupt them.
- Import dropped account groups and didn't refresh the list until restart.
- Delete / Enter pressed on the Settings or History tab acted on the selected account.
- The app jumped in front of the Riot Client during a "disconnect first" login.
- Typing the Riot Client path rewrote the settings file and restarted the hotkey on every key.
- "Launch on Windows startup" started a bare Python when running from source.

### Internal
- Login from the window, Enter, double-click and tray share one code path.
- Account serialisation lives in one place (`AccountEntry.from_dict` / `asdict`).
- Shared palette in `ui/theme.py`.
- Unit tests (`tests/`), run by CI before every build.
- Dependencies removed: `pyautogui`, `pyperclip`, `requests`.

## 3.2.0 — 2026-05-18
- Global hotkey (default `Ctrl+Shift+A`, remappable in Settings) to bring the window to the front.
- `Ctrl+F` / `/` focus the search bar.

## 3.1.0 — 2026-05-15
- Game filter dropdown in the account list.

## 3.0.0 — 2026-05-15
- Game tags, search, encrypted export / import, login history.

## 2.2.0
- `+` button to create a new account.

## 2.1.0
- Tray quick-login and update checker.
