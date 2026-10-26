# A.C.E. Shared Save Beta 0.2.0

This is a working, isolated development beta. It has its own desktop interface,
API, synthetic records, and database in `beta_data`. The existing A.C.E. 1.7.6
application and operational inventory are not migrated or replaced.

Version 0.2 adds university connection settings, Microsoft Entra desktop sign-in,
server token validation, managed-identity Azure SQL, a hosted API/container package,
SharePoint report publication, Windows-encrypted pending requests, and reconciled
legacy migration. See [DEPLOYMENT.md](DEPLOYMENT.md) for configuration, validation
limits, and the approval-dependent deployment procedure.

## Start

Run `python -m shared_beta.launch` from the source directory. First launch creates
synthetic inventory and three random test credentials. The API binds only to
127.0.0.1:8765. The launcher starts it without an extra console window.

For a second test session, run:

```
python -m shared_beta.client --profile beta_data/test_operator_two.json
```

For read-only testing, use `beta_data/test_viewer.json`. Test identities are
clearly labeled and are not actual administrator sign-ins. No production admin
password is used. The server remains available after closing a client.

## Try it

1. Create an item and a cadet using the separate New buttons.
2. Open Checkouts and Loans, choose Issue items / loan, select the cadet and item,
   and enter a quantity and loan deadline in YYYY-MM-DD format.
3. Refresh the second session. Both sessions show the same saved records.
4. Save in one session, then try saving from the second without refreshing. The
   stale change is rejected; refresh, review the latest data, and enter it again.
5. Return part of a loan, permanently issue part, or convert it to checkout.
6. Record fitting sizes and export a dated Audit report. Reports include readable
   field changes and the authenticated test actor. Report dates are UTC.

## Save guarantees implemented

- API-only changes; clients never open the beta database.
- All changes, before/after audit records, and retry receipts commit together.
- Database-wide revision check prevents silent lost updates. This intentionally
  rejects concurrent changes even when they affect different records in v0.1.
- Unique request IDs make retries safe across timeouts and server restarts.
- Client keeps one unresolved request on disk; reopen and click Retry after an
  interrupted connection. A rejected request must be reviewed and re-entered.
- Availability checks, duplicate email/item checks, partial returns, acquisition
  accounting, loan conversion, and read-only authorization run on the server.
- SQLite backup API produces a verified startup recovery snapshot. Restore was
  tested, including saved retry receipts.

## Current development limits

This build is for synthetic data on this laptop. Test bearer credentials and the
pending request file are local, unencrypted development files. This is not an
Entra deployment or an encrypted offline cache. Do not expose the server through
a tunnel, change its bind address, or load operational cadet data into this beta.

The interface refreshes on demand. It reports overdue loans while open; email
notifications and background reminders are not implemented. WINGS/local item
numbers can be entered, but the official WINGS catalog, production migration,
barcode PDF generation, existing full reporting suite, and legacy UI integration
are not all connected to the interface. The beta generates test barcodes prefixed B;
migration retains original inventory barcodes and archives full legacy records.

Campus deployment now has integration code, but still requires university
hosting, Entra application configuration, approved SQL access, site permissions,
retention controls, automated backup retention, and an authorized migration
and acceptance review. Hosted pending requests are encrypted; a full offline
cache is not implemented. The GitHub repository must remain private.

## Verification

`.venv-beta\Scripts\python -m unittest discover -s tests -p "test_shared*.py" -v`

Tests cover competing saves, safe retries, rejected payload reuse, partial loans,
permanent issue totals, duplicate prevention, transaction rollback, authorization,
HTTP authentication, date validation, and backup restoration.

`beta_data/` is ignored by Git and must never be included in a release archive.
