# Cadet Inventory Cards: bag-drag beta

This is a Python feature inside ACE, not a second inventory database. A phone uses its normal browser; Python runs on the ACE computer. No phone installation is required.

## Run a session

1. Back up ACE, sign in, and open **Cadet Inventory Cards**.
2. Choose **Start Phone Session**. Localhost is the default for testing on this computer.
3. For phones, connect the ACE computer and phones to the same **trusted, isolated network or hotspot**, explicitly enable LAN access, and verify the computer's IPv4 address. The default port is 8766.
4. Set the session lifetime (at most eight hours). Optionally supply a TLS certificate and private key whose certificate is trusted by the phones. These files are not copied into the download or shared with phones.
5. Without TLS, HTTP is unencrypted. The confirmation dialog explains this. Do not use unencrypted intake on public/shared campus Wi-Fi, expose it through port forwarding, or treat this beta as university-approved hosting. Obtain the required approval for the records you collect. The app does not change firewall rules. Network policy, client isolation or a firewall may prevent phones connecting.
6. Share the `/det005` URL and six-digit session code shown by ACE. A fresh session rotates its code and bearer token. Keep ACE and the computer awake during intake. The Det005 label/path is not a DNS registration: a bare `http://det005` address would require approved network DNS setup. Neither naming change bypasses Wi-Fi isolation or firewall restrictions.
7. Stop the session when finished. Stopping or closing ACE revokes the network session; saved cards remain for staff review.

## Cadet workflow

- Enter last name, middle initial (optional), first name and email.
- Answer quantity questions for OCP items, PTGs, blues, service dress and other uniforms. Each category offers **I have no ... items**. Counts of zero are retained, not inferred from missing checkout history.
- Only after quantities are complete, enter exact sizes and uniform types for the reported items. Split a quantity across multiple sizes when necessary. For example, one OCP cover and None for all other categories leads to one cover-size selection.
- Boots/shoes are counted in pairs. Follow the issue unit displayed for the selected index item; staff must resolve discrepancies before approval.
- Missing sizes, misspelled descriptions or unknown IDs can be reported as unresolved lines. The card is saved **Held** and cannot be approved or exported as an official WINGS workbook until corrected.
- Review all counts, sizes and None answers and submit. An explicitly confirmed all-None card is allowed, with no stock or checkouts created.
- The private receipt can be refreshed in that browser tab. It reveals only that card, not a directory of cadets. Receipt access uses a separate random secret stored in session storage. Closing the browser/tab can lose this access; staff can provide the card copy later. The session must still be running for a phone to download its copy.

## Staff review and accounting

Notifications appear as a tab badge and status message without opening a popup or switching the active tab; no phone request changes operational inventory. Search cards by name/email. Review shows exact-email and same-first/last-name profile candidates. Confirm an existing profile or explicitly choose a new one. A saved email cannot be duplicated, and linking a card does not rename an existing cadet. Same-name people with distinct emails can remain separate after explicit staff confirmation.

Use **Map Selected Line** after correcting/creating its index entry in ACE. Every line must have a valid visible item ID and matching description/size. No fuzzy matching silently chooses a stock number. A local ID resolves ACE intake but is not an official WINGS mapping.

**Preview Reconciliation** compares each declared item/size with the selected cadet's current checkouts and recorded purchased/acquired items. Previously returned items do not count as current possession. Existing possessions are not duplicated or changed into a different disposition. If ACE already records more units than declared, a warning appears; nothing is automatically returned/deleted. Investigate those discrepancies separately.

For missing held units, approval increases inventory total and creates one checkout record per unit **in the same transaction**, leaving shelf availability unchanged. These records say the item was confirmed in pre-existing possession, with original issue date unknown. They are not shipment receipts or a new issue from the shelf. Card approval, mapping and rejection have a persistent audit trail. Concurrent or replayed approval is idempotent. A stale preview must be refreshed.

## Card and WINGS exports

**Card Copy** creates a readable individual HTML card, including None answers and hold reasons. **Approved WINGS Export** creates a workbook with a Cadet identity/approval sheet and a `WINGs Inventory` sheet using ACE's existing 13-column WINGS format. Quantities represent the approved card, not the entire detachment. Local, hidden, missing or unverified numeric IDs block the official export until corrected in ACE. No local number is presented as an official WINGS ID.

The file is for cadre review. ACE does not send an email, submit an official WINGS transaction, or independently authorize uniform issue. Staff chooses the appropriate sharing method. Save/download names include `.html` or `.xlsx` explicitly.

## Safeguards and limitations

- Only catalog lookup, join, submit and secret-protected own-card receipt/download routes exist on the phone host. No network approval, cadet-search or stock-management routes exist.
- Host/origin validation, random bearer/receipt tokens, join throttling, request/body/quantity limits, capped concurrent requests, no-store responses and frame/CSP protections are applied. HTTP access logs do not contain names or secrets.
- Catalog and quantity data are validated again before approval. SQLite writes use a single immediate transaction and existing stock audit triggers.
- TLS is optional in this local beta, not automatic certificate provisioning. An invitation code is not verified Auburn identity. Staff verifies the person before linking a profile.
- No university Wi-Fi connectivity, real-device certificate trust, production security review or official WINGS import acceptance is implied by local automated tests. Test a synthetic card on the actual approved network and phones before a live bag drag.
- Records live in the existing private `inventory.db` and its backups. No inventory data, tokens, exports, certificates or cadet records belong in GitHub.
