# GitHub Upload Guide

## Repository

Current repository: `https://github.com/PixelatedClub/A.C.E.-Inv`

Use this description:

> A.C.E. is a portable AFROTC clothing and equipment inventory system built for simple cadet use. It supports WINGS-ready imports and exports, searchable equipment records, compact barcode labels, scanner-based checkout and return, cadet history, reports, backups, and flash-drive deployment on Windows.

## Upload the source

For an existing checkout, open PowerShell in this folder and run:

```powershell
git add .
git commit -m "Update A.C.E. source and documentation"
git push origin main
```

Never commit `portable_data/inventory.db`, operational backups, exports, generated labels, or cadet reports. Those paths are intentionally excluded by `.gitignore`.

## Upload the executable

1. Open the repository's **Actions** tab.
2. Select **Windows release (unverified publisher)**.
3. Select **Run workflow** and enter a tag matching the application version, such as `v1.6.8`.
4. Wait for the tests, build, metadata checks, ZIP packaging, and release publication to finish.
5. Download `A.C.E.zip` from the resulting Release page and extract it before running.

The executable carries Team Shapes product metadata but is intentionally unsigned. Windows may display **Unknown publisher** or a SmartScreen warning.

The release ZIP is intentionally ignored by git. It should be attached to the Release page, not committed to the repository.
