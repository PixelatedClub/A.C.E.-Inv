# A.C.E. Inventory System

A.C.E. is a portable AFROTC clothing and equipment inventory system built for simple cadet use. It supports WINGS-ready imports and exports, searchable equipment records, compact barcode labels, scanner-based checkout and return, cadet history, reports, backups, and flash-drive deployment on Windows.

## Current release

The clean executable package is stored locally in `release/A.C.E_Email_Ready.zip`. Git ignores this file so it can be uploaded separately as a GitHub Release asset without placing a generated executable in the source history.

The application starts with:

- No inventory records
- No cadet records
- No checkout history
- The permanent cadre administrator code `Det005`
- The WINGS-oriented equipment index and military terminology

## Main capabilities

- Smart equipment search with item-specific sizes and configurations
- WINGS inventory import and ordered Excel export
- Compact barcode generation for 1 x 2-inch labels
- Scanner-based checkout and return
- Cadet records and complete transaction history
- Inventory, readiness, and accountability reports
- Automatic compressed backups with retention controls
- Portable, relative data paths for flash-drive use
- Built-in index management for WINGS and custom items

## Run the packaged application

1. Download `A.C.E_Email_Ready.zip` from the GitHub Releases page.
2. Extract the ZIP to a normal folder or approved flash drive.
3. Double-click `A.C.E.exe`.
4. Sign in with the cadre administrator code `Det005`.

Do not run the executable from inside the ZIP.

## Run from source

Python 3.10 or newer is recommended.

```powershell
py -3 -m pip install -r requirements.txt
py -3 .\main.py
```

The included `Launch A.C.E.cmd` starts the executable when one is present, or falls back to the Python source version.

## Data and privacy

Operational data is stored locally in `portable_data/inventory.db`. Backups, exports, and generated labels are also written under `portable_data`. These paths are excluded by `.gitignore` because they may contain cadet or inventory information.

Never upload an operational database, backup, export, or completed cadet report to a public repository.

## Documentation

- `docs/A.C.E_Complete_Walkthrough_Brief_Style.pptx` - complete user walkthrough
- `docs/A.C.E_Tera_Scanner_Test_Labels.pdf` - physical scanner acceptance sheet
- `CATALOG_SOURCES.md` - equipment catalog source notes

## Barcode acceptance note

The application now generates compact labels designed for 1 x 2-inch stock. The PDF layout and barcode encoding have been verified in software. A final physical print-and-scan test with the Tera Model 5100 is still required before operational use.

