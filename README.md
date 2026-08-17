# A.C.E. Inventory System

A.C.E. is a portable AFROTC clothing and equipment inventory system built for simple cadet use. It supports WINGS-ready imports and exports, searchable equipment records, compact barcode labels, scanner-based checkout and return, cadet history, reports, backups, and flash-drive deployment on Windows.

## Download A.C.E.

**[Download the current A.C.E. Windows application](https://github.com/PixelatedClub/A.C.E.-Inv/releases/latest/download/A.C.E.zip)**

The download is named `A.C.E.zip` and contains `A.C.E.exe`. Extract the ZIP before running the application. The files shown in the main repository are the application source code, documentation, icons, animation, and audio assets.

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
- In-place editing of existing barcode records and their total quantities
- Lowest-unused-number allocation for new A.C.E. barcodes
- Scanner-based checkout and return
- Cadet records and complete transaction history
- Inventory, readiness, and accountability reports
- Dual-location compressed backups with retention controls
- Portable, relative data paths for flash-drive use
- Built-in index management for WINGS and custom items
- Custom-item category and subcategory suggestions based on values already in use
- Preloaded Soft Blues, Hard Blues, and OCP rank entries from GMC 100 through C/Col
- Optional alternate app-icon mode hidden in the Credits screen

## Run the packaged application

1. Download `A.C.E.zip` from the GitHub Releases page.
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

Operational data is stored locally in `portable_data/inventory.db`. Portable backups, exports, and generated labels are also written under `portable_data`. On the first login on each Windows device, A.C.E. offers a protected backup location on another drive, the computer, or OneDrive. That device remembers the choice, so the setup screen does not appear on every launch. The newest 10 compressed backups are retained in both locations. A temporarily unavailable protected location never prevents the live USB database from opening.

The device marker is stored under the current Windows user's local app data. It contains only the backup-folder path and setup status, never inventory or cadet data.

These data paths are excluded by `.gitignore` because they may contain cadet or inventory information.

Never upload an operational database, backup, export, or completed cadet report to a public repository.

## Documentation

- `docs/A.C.E_Complete_Walkthrough_Brief_Style.pptx` - complete user walkthrough
- `docs/A.C.E_Tera_Scanner_Test_Labels.pdf` - exact-size direct-print scanner acceptance labels
- `CATALOG_SOURCES.md` - equipment catalog source notes

## Barcode acceptance note

The application generates Code 39 labels in the current `A` plus seven-digit format. The scanner test PDF places one label on each exact 2 x 1-inch PDF page so thermal-printer drivers do not have to shrink a letter-size sheet. Print at Actual Size or 100% with Fit To Page disabled. The page dimensions, quiet zones, and barcode module width are verified in software; a final physical print-and-scan test with the target Tera scanner and label printer is still required before operational use.

## Alternate icons

Open **Settings > Credits** and click `@pixelatedclub` to toggle alternate icon mode for that Windows device. Normal mode gives a rare icon a 1-in-4,000 chance per launch. Alternate mode changes that chance to 1 in 4. Shift-clicking the creator name retains the original hidden Credits action when its matching quote appears.
