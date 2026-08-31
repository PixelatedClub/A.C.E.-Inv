# A.C.E. Inventory System

A.C.E. is a portable AFROTC clothing and equipment inventory system built for simple cadet use. It supports WINGS-ready imports and exports, searchable equipment records, compact barcode labels, scanner-based checkout and return, cadet history, reports, backups, and flash-drive deployment on Windows.

A.C.E. is developed and published under the **Team Shapes** brand.

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
- Complete 493-item official WINGS catalog, including the Auburn inventory workbook additions
- Compact barcode generation for 1 x 2-inch labels
- In-place editing of existing barcode records and their total quantities
- Lowest-unused-number allocation for new A.C.E. barcodes
- Scanner-based checkout plus a cadet-centered Returns tab
- Explicit returning-cadet selection with individual or all-held-item returns
- Permanent-issue and purchase disposition from each cadet's checked-out inventory
- Cadet records and complete transaction history
- Inventory, readiness, and accountability reports with inclusive start/end date filters
- One-click current-week and trailing-seven-day report presets with filtered CSV export
- Dedicated Cadet Fitting Index for recording uniform sizes and measurements by cadet
- Dedicated acquired/purchased-items report with CSV export
- Dual-location compressed backups with retention controls
- Portable, relative data paths for flash-drive use
- Built-in index management for WINGS and custom items
- Automatic item-number coverage: every inventory row has an official WINGS number or an explicit local A.C.E. number
- Separate complete-inventory Excel export that includes local-only items without putting them in the official WINGS import file
- Custom-item category and subcategory suggestions based on values already in use
- Official WINGS male/female officer cloth ranks (867-878) and senior mini-metal ranks (2348-2349), plus local ranks where no official WINGS match exists
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

## Libraries and build tools

- Python 3.10 or newer
- Tkinter/Tcl-Tk and SQLite from the Python standard library for the interface and database
- PyInstaller for the standalone Windows executable
- Python standard-library CSV, ZIP, XML, HTML, hashing, date/time, and filesystem modules for imports, exports, reports, backups, and generated files

A.C.E. has no third-party runtime dependencies. Image dimensions, GIF timing, ICO packaging, barcodes, PDFs, and Excel files are handled by local project code plus Python's standard library. PyInstaller is used only while producing the standalone Windows executable; end users do not need it.

## Windows publisher and signed releases

Windows file properties identify **Team Shapes** as the product company. A trusted Windows "Verified publisher" name comes from the Authenticode certificate, not editable file metadata. The signed-release workflow refuses to publish unless Azure Artifact Signing supplies a valid identity-verified signature and the final signature passes verification.

Configure the `release-signing` GitHub environment with these OIDC secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Configure these environment variables after the Artifact Signing account and certificate profile are approved:

- `AZURE_ARTIFACT_SIGNING_ENDPOINT`
- `AZURE_ARTIFACT_SIGNING_ACCOUNT`
- `AZURE_ARTIFACT_SIGNING_PROFILE`

The certificate identity may be an individual legal name until Team Shapes becomes a validated organization or DBA. Team Shapes remains the visible product brand either way.

## Data and privacy

Operational data is stored locally in `portable_data/inventory.db`. Portable backups, exports, and generated labels are also written under `portable_data`. On the first login on each Windows device, A.C.E. offers a protected backup location on another drive, the computer, or OneDrive. That device remembers the choice, so the setup screen does not appear on every launch. The newest 10 compressed backups are retained in both locations. A temporarily unavailable protected location never prevents the live USB database from opening.

The device marker is stored under the current Windows user's local app data. It contains only the backup-folder path and setup status, never inventory or cadet data.

These data paths are excluded by `.gitignore` because they may contain cadet or inventory information.

Never upload an operational database, backup, export, or completed cadet report to a public repository.

## Documentation

- `docs/A.C.E_Complete_Walkthrough_Brief_Style.pptx` - complete user walkthrough
- `docs/A.C.E_Tera_Scanner_Test_Labels.pdf` - complete 40-label PLS892 scanner acceptance sheet
- `CATALOG_SOURCES.md` - equipment catalog source notes

## Barcode acceptance note

The application generates Code 39 labels in the current `A` plus seven-digit format. Letter-size exports use the Premium Label Supply PLS892 geometry: four columns by ten rows, 2 x 1-inch labels, 0.25-inch left/right margins, 0.5-inch top/bottom margins, and no gaps. A 1,000-label export therefore produces exactly 25 sheets. Print at Actual Size or 100% with Fit To Page disabled. The page dimensions, quiet zones, and barcode module width are verified in software; a final physical print-and-scan test with the target printer and Tera scanner is still required before operational use.

Checkout scans and barcode selection in Returns automatically extract one valid A.C.E. or WINGS barcode from scanner-added timestamps and other prefix/suffix text. Returns first require selecting the cadet, then pull only that cadet's currently checked-out inventory so the exact checkout units can be returned. Inputs containing no valid barcode or multiple different barcodes are rejected.

## Alternate icons

Open **Settings > Credits** and click `@pixelatedclub` to toggle alternate icon mode for that Windows device. Normal mode gives a rare icon a 1-in-4,000 chance per launch. Alternate mode changes that chance to 1 in 4. Shift-clicking the creator name retains the original hidden Credits action when its matching quote appears.
