# Shared-save beta 0.2 integration and deployment

## Status

Integration code is implemented for Entra sign-in, protected API endpoints, Azure
SQL managed identity, SharePoint report upload, encrypted pending requests, and
legacy migration. Actual Auburn sign-in, Azure SQL, container deployment, and
SharePoint upload have not been exercised against university resources. They
require approved identifiers, permissions, hosting, and end-to-end acceptance.
The original A.C.E. application continues to use its operational local database.

The beta adds optional libraries in its own `.venv-beta` environment. The original
application's dependency-free runtime is unchanged. Use Microsoft's MSAL and
maintained JWT/cryptography libraries rather than custom token cryptography.

## Desktop setup

Open the Desktop beta shortcut and choose **University connection settings**.
Enter the HTTPS API origin, tenant ID, desktop app ID, and API app ID supplied by
campus IT. SharePoint drive and folder IDs are optional until publication is
approved. Saving opens the university client. Choose **Sign in with Auburn**.

Profiles contain public configuration, never a password or client secret. Access
tokens remain in memory. A pending save is encrypted with Windows DPAPI under the
current Windows user; it survives restart and can be retried with the original
operator identity. The beta retains one unresolved save, not a general offline
inventory cache. Refresh retrieves current state; it does not poll automatically.

## Entra registrations

Campus IT must register two single-tenant applications:

1. Desktop public client: desktop redirect URI `http://localhost`, no secret.
   MSAL uses browser authorization-code sign-in with PKCE.
2. Web API: `api://<API application ID>` application URI; delegated scope
   `access_as_user`; access-token version 2; user/group app roles `ACE.Operator`
   and `ACE.Viewer`. Require assignment to the enterprise application.

Grant the desktop application the delegated API scope and consent according to
university policy. Assign the API roles to the approved users/groups. The API
checks signature, expiration, not-before time, issuer, tenant, audience, authorized
desktop application ID, delegated scope, token version, and assigned role. Local
test tokens and local A.C.E. admin passwords cannot authenticate to the hosted API.
Audit actors use stable tenant/object IDs rather than editable display names.

For optional SharePoint publishing, grant the desktop application delegated
Microsoft Graph `Sites.Selected`, consent, and a site-specific write grant. Both
the application grant and signed-in user's rights must permit the destination.
Configure its drive and folder IDs. The user chooses a report to publish; upload
uses a unique name and verifies the returned file size. No background upload runs.

## Hosting package

Install/test locally with:

```
python -m venv .venv-beta
.venv-beta\Scripts\python -m pip install -r shared_beta/requirements.lock.txt
.venv-beta\Scripts\python -m unittest discover -s tests -p "test_shared*.py" -v
```

Build the server container from the source root:

```
docker build -f shared_beta/Dockerfile -t ace-shared-beta:0.2.0 .
```

`.dockerignore` includes only server/beta source and dependency requirements;
databases, profiles, credentials, pending requests, and the legacy application
are excluded. The process runs without root privileges. Docker and Azure CLI are
not installed on the current laptop, so container and Bicep builds are unverified.

`deploy.bicep` targets an existing approved Linux App Service plan and integration
subnet. Supply the university registry image, tenant/application IDs, existing
Azure SQL server FQDN, and database. It enables HTTPS-only access, TLS 1.2 minimum,
managed identity, private-network integration, and health checks. Campus IT must
provide private SQL routing/DNS, the approved container registry pull permission,
logging, access policies, and the chosen backup/retention policy. The template does
not create an Azure subscription, SQL server, network, registry, or Entra apps.

Hosted API environment variables:

| Variable | Value |
| --- | --- |
| ACE_TENANT_ID | Auburn directory GUID |
| ACE_API_CLIENT_ID | API application GUID; token audience |
| ACE_DESKTOP_CLIENT_ID | Authorized desktop application GUID |
| ACE_SQL_ODBC | ODBC Driver 18 connection string with server/database, Encrypt=yes, TrustServerCertificate=no; no credentials |

The API uses managed identity for SQL. A privileged provisioning identity creates
the schema once with `python -m shared_beta.admin --init-schema`. Runtime identity
needs SELECT on domain tables, beta_meta, receipts, and audit; INSERT/UPDATE on
items, cadets, issues, fittings, and beta_meta; INSERT on audit and receipts. It
does not need schema modification or audit UPDATE/DELETE. Grant rights explicitly
after creating the managed-identity database user. Verify sp_getapplock access.
Legacy import uses a separate privileged identity and an empty destination.

SQL transactions acquire a database application lock across API instances. Writes
hold an exclusive lock, snapshots hold a shared lock. Revision checks, mutations,
audit inserts, and retry receipts commit together. This beta serializes writes
across the whole inventory; per-record concurrency is a later scalability change.
Use Azure SQL point-in-time recovery and test a restore before activation.

## Migration

Read-only preview, including a consistency check:

```
python -m shared_beta.migrate "PATH_TO_LEGACY_INVENTORY.db"
```

After authorization, create a NEW isolated migration database:

```
python -m shared_beta.migrate "PATH_TO_LEGACY_INVENTORY.db" --apply-to-new "beta_data/reconciled.sqlite3"
```

The source is opened read-only in a consistent transaction. Migration rejects
unreconciled availability, ambiguous duplicate identity, missing item numbers,
invalid loan dates, and unresolved references. It preserves active and retired
stock, original barcodes, cadet IDs, transaction IDs, deadlines, permanent issue,
and distinct fitting labels. Non-secret legacy tables are archived in full,
including inventory changes, WINGS catalog, barcode aliases, and loan events.
Local administrator secrets are excluded. These archived tables are preserved for
historical access, but their legacy reports/catalog features are not all exposed
in the beta UI. Retired/lost records cannot be issued.

Verify the created database and totals. During the authorized cutover, pause writes
on the old application, repeat the migration from its final saved state, and then
load the reconciled database into an EMPTY SQL destination:

```
python -m shared_beta.admin --import-reconciled "beta_data/reconciled.sqlite3"
```

Import is transactional, preserves identities, compares resulting domain records,
and refuses a nonempty destination. This path needs Azure SQL integration testing.
Keep the original database and verified recovery copy until the pilot is accepted.
After shared writes begin, do not switch back to a stale local file without
reconciling new activity. No production migration or cloud upload was performed.

## Acceptance still requiring university resources

- Real Auburn sign-in, MFA/conditional access, assignment and revocation tests.
- Hosted HTTPS/API/SQL tests, including two-device contention and backup restore.
- SharePoint site-specific grant and successful report upload under an approved user.
- Final migration reconciliation and authorized pilot before public distribution.

References: [MSAL desktop token acquisition](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens),
[Graph selected permissions](https://learn.microsoft.com/en-us/graph/permissions-selected-overview),
[Azure SQL passwordless access](https://learn.microsoft.com/en-us/azure/azure-sql/database/azure-sql-passwordless-migration-python?view=azuresql).
