# A.C.E. Changelog

## 1.9.0-beta.1 - 2026-10-26

- Add an ACE-hosted Python CIC phone session with a quantity-first bag-drag questionnaire, later size allocation, explicit None answers and a private submission receipt.
- Add durable Pending/Held/Approved/Rejected cards, desktop notifications, explicit profile confirmation, item correction and an atomic reconciliation preview.
- Reuse current holdings and preserve acquired/purchased records. Add only missing held units and matching checkouts, without changing available shelf stock. Replayed approval cannot duplicate stock.
- Block unresolved items and block official WINGS exports for local/unverified IDs. Provide individual card copies and approved, identity-labeled WINGS workbooks for cadre review.
- Sessions default to localhost, require explicit trusted-LAN enablement, expire within eight hours, support supplied TLS certificates, and stop on ACE exit. No cloud service or automatic email/official WINGS issue is enabled.

## 1.8.8 - 2026-10-19

- Generate Full Report and Previous Week Report share a self-contained HTML report with navigable detail sections and embedded uniform charts.
- Remove COA from the report and report-generation dialog. Keep optional BLUF and Major Activities context.
- Preserve inclusive date filtering and current inventory snapshots. Explicit WINGS spreadsheet and CSV exports remain unchanged.

## 1.8.7 - 2026-10-14

- Reuse available checkout tab numbers after a tab closes.
- Allow checkout and cadet creation without a middle initial. Preserve existing initials when identifying the same cadet by email, first and last name.
- Include conservative local uniform naming helpers, with unknown boot sex, width and garment fabric explicitly retained.

## 1.8.6 - 2026-10-14

- Populate Items from the visible size-specific catalog with zero stock and unique barcodes, preserving existing stock and checkout records.
- Add counting status, pending-count filters, confirmed zero counts and physical available-count entry. Totals preserve units held by cadets.
- Newly added catalog entries create their inventory row automatically. Items offers Add Custom Item directly.
- Keep zero-stock baseline creation out of weekly receipts and new counted item activity.

## 1.8.5 - 2026-10-14

- Added multiple cadet checkout tabs with independent queues, names, emails and notes. Drafts persist locally across restarts, and stock checks account for units queued in other tabs.
- Moved Temporary Loans to Returns. Loan Queued Items remains in each checkout draft. Ctrl+L opens loan management and Ctrl+R opens Return Items.
- Added barcode generation directly from catalog entries, including the Add Custom Item and Add WINGS Item dialogs. Zero quantity creates a label with no stock, and existing matching barcodes are reused.

## 1.8.4 - 2026-10-05

- Added Undo Last Acquired / Purchased in Cadets. Reopens the original checkout batch and restores stock totals with an audit trail.
- Saved acquisition snapshots persist across restarts. Older actions can use their matching pre-acquisition backup.
- Corrected Windows Num Lock handling for direct letter shortcuts.

## 1.8.3 - 2026-09-30

- Replaced Ctrl+K sequences with direct Ctrl+G/L/M/I/R/T shortcuts.
- Kept Ctrl+F for Items search; Ctrl+M opens fittings/measurements.
- Direct navigation is handled before text-field bindings and remains disabled in modal dialogs. Shortcut documentation stays in Settings.

## 1.8.2 - 2026-09-30

- Hover highlighting across table rows preserves real selection, keyboard focus, and existing status tags.
- Moved shortcut hints out of Items and its right-click menu into Settings > Keyboard Shortcuts.
- Added Ctrl+K multi-key navigation with a two-second timeout, Escape cancellation, and modal-dialog protection. No sequence finalizes a checkout.
- Includes the 1.8.1 draggable-panel changes.

## 1.8.1 - 2026-09-29

- Added draggable panel dividers in Items, Barcode Generator, Returns, Cadets, and Cadet Fitting. Double-click a divider to reset it. Positions last for the current session.
- Barcode Generator also has a vertical divider above the label library.
- Item details scroll vertically, and item toolbar actions occupy their own row to reduce horizontal crowding.
- Initial window size fits the screen, with a smaller 1000 by 640 minimum. Some dense forms still need wider panels.

## 1.8.0 - 2026-09-29

- Right-click Items or the barcode label library to stage one unit of each selected barcode in Checkout. Ctrl+Enter does the same. Stock checks apply; final checkout still requires approval.
- Ctrl+F searches Items; Ctrl+1, Ctrl+2, and Ctrl+3 open Items, Checkout, and Reports. Delete removes selected checkout queue rows.
- Added reusable, case-insensitive custom tags, suggestions, removable tag chips, and match-all tag filtering. Original WINGS IDs and category/type values are preserved.
- Added editable family and season classification. Unassigned seasons remain Unclassified.
- Added item PNG upload, preview, and removal. Images are embedded in the database and included in database backups (up to 2 MB, 4096 pixels per side).
- Generate Full Report uses the same consolidated report workflow as Previous Week Report. CSV remains a filtered table export.
- Full reports include current inventory, uniform-family and season summaries, and native Excel pie charts by recorded unit quantity, not barcode count.
- Excluded barcode/mapping repairs from daily receipt/removal totals to match summary classification. Original audit rows remain in Catalog Activity.

The metadata and image feature is implemented for the local desktop database. Shared beta deployment remains a separate, unapproved workflow.

## 1.7.6 - 2026-09-08

- Fixed Save New Cadet after using Cadets search by clearing the stale filter and selecting the saved profile.
- Fixed Barcode Generator Enter searches so they rebuild results from the current query instead of reusing an older selection.
- Fixed Quick Find selections so item type/subcategory always comes from the newly selected WINGS catalog row.

## 1.7.5 - 2026-09-08

- Removed the obsolete standalone Barcode Directory tab.
- Moved barcode copying, visible-list copying, category and item-type columns, and WINGS export access into Items.
- Enabled multi-row selection in Items while retaining first-selected item management.

## 1.7.4 - 2026-09-08

- Added Convert to Standard Checkout in the Temporary Loans menu.
- Conversion preserves the cadet assignment, original checkout, and inventory quantities while removing the deadline and loan purpose.
- Added an audit event for every loan converted to a standard checkout.

## 1.7.3 - 2026-09-08

- Unified previous-week, date-range, and individual report exports under one polished Excel report design.
- Added an Executive Summary with BLUF, key metrics, daily activity, major activities, and course of action / validation.
- Replaced the separate Monday HTML report with the same formatted Excel workbook used by all other A.C.E. activity reports.
- Improved report labels and detail sheets for easier review and printing.

## 1.7.2 - 2026-09-08

- Added Loan Queued Items beside the standard checkout action so the same barcode queue and cadet fields can create a temporary loan.
- The loan confirmation asks only for the return deadline and purpose before issuing the queued items.

## 1.7.1 - 2026-09-08

- Moved temporary-loan management inside the Checkout tab.

## 1.7.0 - 2026-09-08

- Added temporary-loan checkout, custom deadlines, two-/three-/four-week presets, due-date editing, and overdue status.
- Added administrator reminders on startup and hourly while the app is open; returns and acquisitions clear outstanding reminders.
- Added a printable Monday report with prior-week activity and a dated current loan register.
- Added audited conversion of existing checkouts to loans without changing inventory counts.
- Added transactional profile merging with preserved history and conflict checks for fittings.
- Retained the compact Items workspace from local version 1.6.9 and corrected item-number retrieval for its details panel.

## 1.6.8 - 2026-09-01

- Added Windows single-instance protection. Repeated launches no longer open competing A.C.E. windows or database sessions.
- Added safe foreground behavior for an already visible A.C.E. window without exposing the hidden pre-authentication interface.

## 1.6.7 - 2026-09-01

- Changed automatic inventory audit attribution to `Admin code 3 - Williams`, including migration of earlier `Automatic audit` rows and triggers.
- Added the `Recorded By` field to Inventory Changes reports and spreadsheet exports.

## 1.6.6 - 2026-09-01

- Added `ONE SIZE` handling for official WINGS items whose catalog size is blank.
- Fixed creation and restocking of size-free catalog items such as duffel bags.

## 1.6.5 - 2026-08-31

- Published the Team Shapes unverified-publisher release workflow and associated Windows metadata.
