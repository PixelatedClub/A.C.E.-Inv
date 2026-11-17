# Microsoft CIC branch

Optional CIC intake uses a Microsoft-hosted form, Power Automate, a dedicated SharePoint document library, and OneDrive. Each detachment configures its own resources. A.C.E. reads the synchronized local copy and stores its working inventory locally.

## Cadet workflow

Enter last name, optional middle initial, first name and email. Each uniform family (OCP, PTG, blues, service dress and other uniforms) has a Yes/No gateway. No skips that family's items. Each item has a possession gateway: No skips its quantity and size/type follow-ups. Ties and tie tabs are distinct. Applicable fields are required; skipped answers become explicit zeros during import.

For possessed items, enter quantity, then one line per type/size as `full catalog name or item ID | exact label size | quantity`. Include sex, season and other distinguishing descriptions in the type. Exact and unambiguous matches are required. Microsoft Forms cannot query the laptop's live catalog, so missing, ambiguous or misspelled answers are Held in A.C.E. until corrected by staff.

## Deployment

1. Generate an import source with `tools/build_cic_form.py` and Microsoft Forms Quick Import. Review every converted question: the importer can merge questions or mistake option text for section headings. No import-success message substitutes for validation.
2. Configure and preview the family and item No branches. Restrict response access to the approved organization. Confirm the intended group has access to stored records; organizational form access and SharePoint group access are separate controls.
3. Create a dedicated A.C.E. library at the approved SharePoint site. Synchronize only that library with OneDrive. Do not move, delete or modify existing team resources.
4. Configure a Power Automate flow with Forms **When a new response is submitted**, Forms **Get response details**, and SharePoint **Create file**. Use the same form ID in both Forms steps and the trigger's response ID for response details.
5. Create one immutable envelope per response named `cic-RESPONSE_ID.json`. Include `schema: ace.cic.forms.v1`, the exact `form_id`, `response_id`, original `submitted_at` (or empty string), and the complete raw response object in `answers`. Do not generate a different timestamp during retry.
6. Save a local JSON profile with that schema, form ID and a `field_map` mapping every key in `inventory_app.cic_sharepoint.FIELDS` to its actual Microsoft question ID. The profile contains no Microsoft credentials. Keep deployment profiles outside Git and release bundles.
7. Open **Cadet Inventory Cards → Microsoft Intake**, choose the profile and the local synchronized library folder, then enable receiving. Configuration is per-device and tied to the inventory database.
8. Verify synthetic all-None and nonempty cards through the phone form, flow, SharePoint, local sync and a temporary inventory. Do not approve synthetic cards into the operational inventory.

## Staff review and recovery

Intake creates only Pending or Held CIC records. The existing explicit profile choice, reconciliation preview and atomic approval determine operational changes. Existing holdings and acquired/purchased records prevent duplicate recovered checkouts. Available shelf stock is preserved. Local or unresolved item IDs block official WINGS export.

Missing identity, malformed quantities, contradictory No answers and size-allocation mismatches remain Held. **Correct Microsoft Answers** provides labeled identity and uniform-family fields; original answers are retained with locally audited corrections. Corrections never approve a card and finalized cards cannot be changed through this dialog.

Each form/response key is imported once. Repeated scans, restarts and recovery after an interrupted import cannot duplicate the card. A changed response at an existing key produces a conflict and preserves the existing card. Invalid or partially downloaded JSON is reported and retried. Source files are never edited, moved, deleted or acknowledged by renaming.

## Limits

OneDrive must be signed in, running and synchronized. The application cannot infer cloud freshness from a successful local scan. Submissions can remain in Microsoft while the laptop is offline; they arrive locally when sync resumes. A.C.E. must be open to receive local cards. Disabled flows, sign-in problems, quotas and university restrictions can interrupt delivery.

The reader handles up to 50 changed files per scan, at most 10,000 files per inbox, 256 KB per card, 100 size lines and 500 items. No incoming firewall rule, tunnel, public endpoint, Microsoft password storage, raw database upload, automatic email or official WINGS transaction is added. OneDrive itself synchronizes in both directions, so manual local edits/deletions can affect SharePoint. Two staff computers with independent databases do not become one shared inventory.

Test cleanup is restricted to A.C.E.-created test forms, flows, lists and drafts. Use normal recoverable deletion and never empty shared recycle bins. Preserve test results before cleanup. The general `main` build remains separate from this deployment-specific branch.

## Human size matching

Item IDs are optional. Enter `7 3/8`, `Medium regular`, or `Small regular summer x2`. A single size applies to the entered quantity. Multiple unnumbered lines mean one each only when their number equals the declared count. Otherwise specify quantities with x2. Matching is case-insensitive and scoped to the question item type. Known aliases include SM/MED/LG, REG/LNG, hot/summer/IHWCU, cold/all weather, hard/metal, soft/cloth, and rank abbreviations. Missing gender, season or width distinctions remain held when ambiguous; there is no arbitrary fuzzy matching. Correct lines are retained on held cards. Staff can save corrections incrementally while remaining issues continue to block approval. Original Microsoft answers remain unchanged. Finalized or rejected cards are never automatically reopened.
