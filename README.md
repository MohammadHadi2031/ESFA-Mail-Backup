# ESFA Mail Backup

**[فارسی](README.fa.md)** · English

A Windows desktop application that takes incremental backups of one or more mailboxes over IMAP. Every message is stored as a plain `.eml` file you can open with any mail client, and the whole archive can be exported to standard `.mbox` files.

It ships with a Persian, right-to-left interface. It is preconfigured for [Hetzner Mail](https://www.hetzner.com/mail/) but works with any standard IMAP server. This project is not affiliated with or endorsed by Hetzner Online GmbH.

## Features

- Multiple mail accounts in one place
- Backs up every folder, including Inbox, Sent, Drafts and custom folders
- Each message stored as a standard `.eml` file
- Incremental fetch based on `UIDVALIDITY` and `UIDNEXT` — only new messages are downloaded
- Messages already backed up are kept even after they are deleted from the server
- One-click export to `.mbox`, one file per mail folder, ready to import into Thunderbird
- Passwords encrypted with Windows DPAPI; only the same Windows user can decrypt them
- Daily schedule through Windows Task Scheduler
- Manual runs with live progress and a built-in log viewer
- Two backup runs can never overlap
- No telemetry, no auto-update, no network traffic other than IMAP

## Security posture

The whole point of this tool is to hold someone's entire mail archive, so it is written to be auditable. Everything below can be verified in the source:

- **The only network destination is the IMAP server the user types in**, over TLS with standard certificate validation ([`mailbackup/backup_engine.py`](mailbackup/backup_engine.py)). No other host appears anywhere in the code.
- **The UI is served on `127.0.0.1` only** and is not reachable from the network ([`app.py`](app.py)).
- **The mailbox is opened read-only.** Folders are selected with `readonly=True` and messages fetched with `BODY.PEEK[]`, so nothing on the server is ever deleted or even marked as read.
- **Only two locations are written to**: `%LOCALAPPDATA%\EsfaMailBackup` and the backup folder the user chooses.
- **Installs per-user, no Administrator rights** (`PrivilegesRequired=lowest`). No service, no driver, no kernel component.
- **The only system-level change** is a scheduled task named `ESFA Mail Backup`, which is removed on uninstall ([`mailbackup/scheduler.py`](mailbackup/scheduler.py), [`installer.iss`](installer.iss)).
- **Credentials never leave the machine.** `config.json` holds a DPAPI blob, not the password; copying it to another machine or another Windows account makes it useless.
- Releases are built by [GitHub Actions](.github/workflows/windows-installer.yml), so every installer is traceable to a specific commit.

## Running from source

Requires Python 3.11 or newer on Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

To run in a browser instead of a desktop window:

```powershell
python app.py --browser
```

## Building the Windows installer

Push a `v*` tag and the [workflow](.github/workflows/windows-installer.yml) packages the app with PyInstaller and builds the installer with Inno Setup on a Windows runner; the result is downloadable from the Actions tab.

Manual build:

```powershell
python -m pip install -r requirements-dev.txt
python -m PyInstaller EsfaMailBackup.spec --noconfirm
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

The installer is written to `Output\ESFA-Mail-Backup-Setup.exe`.

## Usage

1. Pick a destination folder and a daily run time under Settings.
2. Add your mail accounts. For Hetzner Mail the server is usually `mail.your-server.de:993`.
3. Use **Test connection** first.
4. Run **Start backup** once.
5. Then enable the schedule.

## MBOX export

The **MBOX export** button converts the stored `.eml` messages into standard MBOX files:

```text
<backup folder>\MBOX\<email address>\<mail folder>.mbox
```

- One `.mbox` file per mail folder, messages ordered by UID.
- Lines starting with `From ` inside a message body are escaped with `>` per the mboxrd convention.
- Each export is written from scratch, so re-running it is safe and never duplicates messages.
- The `.eml` files are left untouched; MBOX is a side export for importing into Thunderbird and similar tools.

## Where data lives

Settings and logs:

```text
%LOCALAPPDATA%\EsfaMailBackup
```

Backed-up messages go only into the folder chosen by the user. Uninstalling the application removes neither the backups nor the settings.

## Running the tests

```powershell
python -m pytest -q
```

## Reporting a security issue

See [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
