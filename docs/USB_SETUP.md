# Install A.C.E. from a USB

On a prepared USB, run **Set Up A.C.E.exe**, select a computer backup folder and, if applicable, the existing OneDrive CIC inbox, then choose **Install / Update**. Start **ACE Inventory** from the desktop afterwards. The program and working inventory live under `%LOCALAPPDATA%/A.C.E/Installed/<package-id>`. You can remove the USB to connect your mouse and scanner. No Python installation is needed. Windows does not automatically run USB applications; setup must be opened once.

## Inventory safety

The first installation seeds a consistent copy of the USB inventory, profile and supporting files. Later setup runs update the program only. They never replace the computer's inventory with the USB snapshot. A missing or damaged installed database blocks launch instead of creating an empty inventory or falling back to another copy. A database backup is verified before installation and program updates.

Each computer has its own inventory after installation. Updating program versions does not synchronize inventory between computers. Microsoft CIC cards still arrive through the computer's configured OneDrive inbox and require staff approval. Existing laptop snapshots and unrelated files are preserved.

## Newer versions

The desktop launcher checks a connected matching USB for a newer program. Optionally it checks this private repository's published CIC releases on GitHub, at most once every six hours; setup checks immediately. Existing GitHub CLI or Git credential access is used without a sign-in prompt. Offline or unauthorized checks retain the installed version. No credentials are copied into the USB, settings, releases or downloads.

A release must match the CIC channel and pass version, size, manifest and SHA-256 checks. Downgrades are skipped. A release requiring a newer setup utility is held until the utility is upgraded. A verified newer online program also updates the matching connected USB program, leaving its seed inventory unchanged. Unfinished program replacements are recovered on the next launch.

## One previous program version

Updates archive the outgoing program in `program_backups`. Cleanup keeps the newest recognized archive for this package, deleting only older A.C.E.-managed program archives. **Clean Up Old Versions** applies this policy to the selected USB and its installed copy. The current program and one previous program archive remain. Inventory recovery backups are separate and are not deleted by program cleanup. Historical manually created archives are outside this policy.

## Package identity and configuration

`ace_usb.json` identifies the USB package; `ace_install.json` identifies its installed copy. Both retain the same package ID. Registrations use the USB's volume identity to find program updates even after its drive letter changes. The installed copy launches without the USB. This CIC build directs marked USB applications to setup rather than running from the USB.

The installer uses the current Windows account, preserves unrelated shortcuts, and replaces only its own ACE USB shortcut with ACE Inventory. It changes no firewall, network or antivirus settings. Backups must be outside the USB and managed installation. No Teams files are moved or deleted by installation. Setup recovery settings remain within the installed package.
