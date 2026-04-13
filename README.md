# AccountManager

A lightweight Windows desktop app for switching between Riot Games accounts quickly.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## What it does

- Save multiple Riot Games accounts locally
- Switch accounts in one click — the app fills in your credentials on the Riot Client sign-in screen automatically
- Add a personal note to each account (e.g. `main`, `smurf`) displayed as `username - note` in the list
- Reorder accounts with ▲ / ▼ buttons

## Privacy & security

> **Your credentials never leave your machine.**

- Passwords are encrypted with [Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + HMAC) before being written to disk
- The encryption key is stored in the **Windows Credential Manager** via `keyring` — it is tied to your Windows user session and never stored in plain text
- Account data is saved in `%APPDATA%\RiotAccountManager\accounts.json` — only encrypted blobs, no plain-text passwords
- The app communicates **only with the local Riot Client process** on `127.0.0.1` — no external network requests are made

## How login works

The app uses **UI automation** to interact with the Riot Client window directly:

1. Finds the Riot Client window by title
2. Brings it to the foreground
3. Types your username and password into the sign-in fields
4. Presses Enter

The Riot Client then handles authentication normally, including hCaptcha and 2FA prompts.

## Requirements

- Windows 10 / 11
- Python 3.10+
- Riot Client installed and open on the sign-in screen when clicking Login

## Installation

```powershell
git clone https://github.com/your-username/RiotAccountManager.git
cd RiotAccountManager

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python main.py
```

## Build standalone executable

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --icon=icon.ico --name=AccountManager --add-data "icon.ico;." main.py
```

Output: `dist\AccountManager.exe` — no Python installation required on the target machine.

## Project structure

```
RiotAccountManager/
├── main.py              # Entry point
├── models.py            # AccountEntry dataclass
├── account_storage.py   # Encrypted local storage (keyring + Fernet)
├── riot_ui_login.py     # Riot Client UI automation
├── icon.ico             # App icon
├── requirements.txt
└── ui/
    └── main_window.py   # PyQt6 main window
```

## Usage

1. **Add an account** — type a username, password and optional note, then click **Save account**
2. **Login** — select an account from the list, make sure the Riot Client is on the sign-in screen, then click **Login**
3. **Reorder** — use ▲ / ▼ to change the order of accounts in the list
4. **Remove** — select an account and click **Remove account**

## Disclaimer

This project is not affiliated with or endorsed by Riot Games. Use it at your own risk and in accordance with Riot Games' Terms of Service.
