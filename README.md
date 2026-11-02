# A.C.E. Inventory System

**Microsoft CIC branch: `feature/cic-sharepoint` (1.9.0-cic.5).** Optional Microsoft Forms / SharePoint intake feeds the existing staff approval queue through a read-only OneDrive-synced inbox. This requires deployment-specific Microsoft resources; it is not enabled by default and is separate from the general `main` build. [Setup and limitations](docs/CIC_MICROSOFT.md).

A.C.E. is a portable AFROTC clothing and equipment inventory system built for simple cadet use. It supports WINGS-ready imports and exports, searchable equipment records, compact barcode labels, scanner-based checkout and return, cadet history, reports, backups, and flash-drive deployment on Windows.

Optional **Set Up A.C.E.exe** on the USB creates a desktop launcher that finds the correct USB even when its drive letter changes, checks inventory health and configures this computer’s backups and CIC inbox. [USB setup](docs/USB_SETUP.md).

A.C.E. is developed and published under the **Team Shapes** brand.

**Current source version: 1.9.0-cic.5 (October 26, 2026)**

Search Items, Index and Barcode Generator using ordinary terms such as `OCP pants medium regular` or `cover 7.5`. Case, size abbreviations, equivalent fractions/decimals and common item names are normalized across fields and linked catalog information. Tags are optional search aids. Summer/all-weather alternatives remain separate; searching never changes item records.

**CIC intake:** Cadets use the Microsoft-hosted form. Power Automate writes cards to the dedicated SharePoint library, OneDrive syncs them, and ACE receives them for staff approval. Use **Copy Form Link** in Cadet Inventory Cards. The local phone server, LAN links and session codes have been removed. [Setup and limitations](docs/CIC_MICROSOFT.md).

Routine editor, detail, report, tag and loan windows are non-blocking. New cadet checkout tabs created with the + button stay in the background until selected. Stale inventory/count/loan forms must be reopened rather than overwrite newer changes. Authentication and irreversible approval confirmations remain protected.

Generate Full Report and Previous Week Report now produce the same self-contained HTML browser report, with the full catalog, checkout, fitting, cadet, loan, data-quality and current inventory sections plus uniform charts. Reports can be printed from the browser and no longer include a COA section. Choose an end date of today to include today's saved activity. Explicit WINGS spreadsheet and CSV exports remain available.

Middle initials are optional for cadet checkout and record creation. Existing saved initials are retained when the same cadet is checked out using only first and last name. Checkout draft tabs reuse the lowest available tab number.

Visible WINGS and size-specific local catalog entries automatically appear in Items with zero stock and a unique barcode when the app starts. Existing inventory and checkouts are preserved. Hidden or superseded catalog entries are excluded. New catalog items also receive an inventory barcode automatically.

Items shows **Counting Status** and filters for **Not counted**, **Counted**, and **Counted zero**. Use **Record Physical Count** for the available units on the shelf. The total includes existing cadet checkouts. Recording 0 confirms a completed zero count. Adding stock marks that inventory as counted. Baseline placeholder creation does not inflate weekly receipts or new counted catalog activity.

Checkout supports multiple cadet draft tabs through **+ New Cadet Checkout**. Each tab keeps its own identity, queued units and notes. Drafts are saved locally beside the database in `checkout_drafts.json` and restored on the next launch. Units queued in other tabs are included in stock checks. Checkout and loan submission still require the normal approval and availability checks.

The Index has **Generate Selected Barcode**, and Add Custom Item / Add WINGS Item offers **Generate a barcode after adding this item**. Enter 0 for a label with no stock, or the quantity to add. A matching barcode is reused.

In Cadets, select a cadet and use **Undo Last Acquired / Purchased** to reopen the most recent acquisition batch. Stock totals are restored while the items remain checked out. New acquisitions save their original records for undo across restarts. Older acquisitions require their pre-acquisition backup.

Rows highlight on hover without changing the clicked selection. Shortcut instructions are available in Settings > Keyboard Shortcuts. Direct shortcuts are Ctrl+G (generator), Ctrl+L (loans), Ctrl+M (fittings/measurements), Ctrl+I (index), Ctrl+R (returns), and Ctrl+T (selected item's tags/image in Items). Ctrl+F remains Items search. No Ctrl+K prefix is needed. Shortcuts do not finalize inventory transactions.

Drag the raised dividers in Items, Barcode Generator, Returns, Cadets, or Cadet Fitting to resize adjacent panels. The Barcode Generator also has a horizontal divider above its label library. Double-click a divider to reset it. Panel positions last for the current session. The Items detail panel scrolls when its controls do not fit vertically.

### Item shortcuts, tags, and photos

Right-click an item or a row in the barcode label library and choose **Add to checkout list**. Multi-selection queues one unit per barcode, subject to stock availability. This does not complete a checkout or change inventory. The cadet and approval workflow remains in Checkout.

- Ctrl+Enter in either inventory list: queue selected barcodes.
- Ctrl+F or Ctrl+1: Items search. Ctrl+2: Checkout. Ctrl+3: Reports.
- Delete in the checkout list: remove selected queued rows, not inventory records.
- **Tags / View or Add Image**: manage case-insensitive tags with suggestions and removable chips, set family/season, or attach a PNG. Images are stored within the database, up to 2 MB and 4096 pixels per side.
- **Tags** filter: enter comma-separated tags to require all tags. Case and repeated spaces are ignored. Existing category/type fields are retained and also exposed as normalized search tags.

**Generate Full Report** and **Previous Week Report** use the same HTML browser-report engine. They include the original activity sections, current inventory, and embedded pie charts for uniform family and season. Each chart counts recorded units once within its own dimension; do not add the family and season charts together. Family defaults are inferred from item descriptions and can be overridden. Seasons require explicit assignment and otherwise remain Unclassified. Available units exclude Lost/Retired records. These are current-stock views, separate from the report's date-filtered activity. CSV remains a single-table export. No database backup or item images are automatically attached to an outgoing report.

**Shared-save development beta 0.2.0:** An isolated desktop/API prototype is available
in [shared_beta](shared_beta/README.md). Run `python -m shared_beta.launch` to try it
with synthetic data. It does not migrate or replace the operational application.
Entra sign-in, Azure SQL hosting adapters, SharePoint publishing, and migration code
are implemented. University configuration, deployment, and live acceptance remain
pending; see [deployment instructions](shared_beta/DEPLOYMENT.md).

Checkout can issue the current queued barcodes as either a normal checkout or a temporary loan. Loan Queued Items asks for a custom return date or offers two-, three-, and four-week presets. Returns > Temporary Loans shows due dates and overdue status; opening the app and hourly checks while it remains open remind the signed-in administrator about overdue items. Reminders require A.C.E. to be running. Returns and permanent dispositions close the original checkout and remove it from outstanding reminders.

Full activity reports use the same browser format: a summary with BLUF, key metrics, daily activity and major activities, followed by navigable detail sections. COA is omitted. The Previous Week Report automatically selects the prior Monday-Sunday; Date-Range Report uses the dates you choose. Reports are generated on demand; no email is sent automatically.

The consolidated Items workspace displays every barcode with category and item type, selected-item details, stock controls, editing, printing, clipboard copying, manual creation, and WINGS export tools.

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
- Targeted PLS892 label exports with selectable barcodes and per-barcode print quantities
- In-place editing of existing barcode records and their total quantities
- Lowest-unused-number allocation for new A.C.E. barcodes
- Single-instance startup protection: repeated clicks keep one A.C.E. window and database session
- Scanner-based checkout plus a cadet-centered Returns tab
- Explicit returning-cadet selection with individual or all-held-item returns
- Permanent-issue and purchase disposition from each cadet's checked-out inventory
- Cadet records and complete transaction history
- Inventory, readiness, and accountability reports with inclusive start/end date filters
- One-click current-week and trailing-seven-day report presets with filtered CSV export
- One-click consolidated weekly HTML report with a popup for BLUF and MAs
- Automatic weekly detail tabs for inventory changes, new catalog items, transactions, fittings, cadet records, and data-quality checks
- Inventory-change reports show who recorded each addition, edit, restock, and deletion
- Dedicated Cadet Fitting Index for recording uniform sizes and measurements by cadet
- Dedicated acquired/purchased-items report with CSV export
- Dual-location compressed backups with retention controls
- Portable, relative data paths for flash-drive use
- Built-in index management for WINGS and custom items
- Official WINGS items without a listed size use `ONE SIZE`, allowing items such as duffel bags to be cataloged normally
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
If A.C.E. is already running, another launch exits instead of opening a competing inventory window. When the authenticated main window is visible, the additional launch attempts to bring it forward.

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

## Windows publisher and releases

Windows file properties identify **Team Shapes** as the product company. Current releases are intentionally unsigned, so Team Shapes is an unverified product brand rather than a Windows "Verified publisher." Windows may display **Unknown publisher** or a Microsoft Defender SmartScreen warning when a newly downloaded executable is opened.

The release workflow runs the complete automated test suite, builds the standalone executable, verifies its Team Shapes metadata and version, and publishes `A.C.E.zip` with SHA-256 checksums. A self-signed certificate is not used because Windows does not publicly trust self-signed publishers.

See `CHANGELOG.md` for version-specific changes.

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
