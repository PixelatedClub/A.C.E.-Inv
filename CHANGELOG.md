# A.C.E. Changelog

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
