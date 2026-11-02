# Optional USB setup

Place **Set Up A.C.E.exe** beside **A.C.E.exe**, `app_settings.json`, and `portable_data` on the USB. On each Windows computer, run the setup utility, choose a computer backup folder, optionally select that computer's synchronized Microsoft CIC inbox, and click **Set Up This Computer**. Use the **ACE USB** desktop shortcut afterwards.

Setup checks the existing database in read-only mode, saves a verified database backup, installs only a small launcher under `%LOCALAPPDATA%/A.C.E./USB Launcher`, and creates the shortcut. Python and additional packages do not need to be installed. It uses the existing Windows user's access without changing network or security settings.

The working application and inventory stay on the USB. Existing application archives and laptop inventory copies are retained. The laptop copy is a separate snapshot; users should start the working inventory through **ACE USB**.

## Drive identity and missing-drive behavior

The package gets an `ace_usb.json` identity marker. This computer's registration records its package ID, USB volume serial, relative folder and backup/intake preferences. The local launcher scans mounted drive letters for that identity. A changed drive letter is supported. A renamed package folder requires setup again.

A missing drive, mismatched identity, missing database, invalid settings, failed database check or duplicate matching package blocks launch. The launcher never falls back to the laptop database. It passes the expected package identity to A.C.E., which checks it again before reading settings or creating application directories. Marked USB packages also refuse to create a new empty inventory when their database is absent. The user must close a running A.C.E. copy before switching inventory.

## Computer-specific settings

Backups must go outside the USB volume. Setup creates a ZIP containing only a consistent SQLite snapshot, not historical executables. Existing settings and an overwritten A.C.E. shortcut are copied to a recovery folder before changes. Unrelated shortcuts are preserved.

Microsoft intake stays optional. When enabled, setup validates the form profile already on the USB and an existing synchronized inbox folder on that computer. It grants no cloud permissions and does not create or move SharePoint files. Drive-letter changes rebase the local database/profile paths only for the same package identity; the OneDrive inbox stays computer-specific. Staff approval remains required for submitted cards.

Close A.C.E. and safely eject the USB before removing it. Keep the computer backup folder available. A.C.E. reports backup problems without substituting a different inventory.

## Validation

Tests cover missing and corrupt databases, incorrect paths, changed drive letters, wrong/duplicate package identities, volume identity, startup validation before fallback, per-device preference preservation, consistent backup creation, CIC rebasing, and setup UI construction. The packaged utility supports a read-only health check with `--diagnose PACKAGE_FOLDER --report OUTPUT_JSON` for deployment verification.
