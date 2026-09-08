# A.C.E. Changelog

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
