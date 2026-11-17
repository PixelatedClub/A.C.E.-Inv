# A.C.E. operator handoff

The [continuity PowerPoint](ACE_Continuity_Guide.pptx) walks through the Windows CIC edition using marked screenshots from a demo inventory.

## At the handoff

1. Identify the computer that holds the working inventory. Open **ACE Inventory** from its desktop shortcut and verify recent activity in **Dashboard**.
2. Confirm the incoming operator can sign in with an account authorized by cadre. Use **Settings > Switch Admin** to change operators.
3. Check the protected backup destination under **Settings**, then select **Create Backup Now**. Keep the snapshot in approved storage.
4. If the detachment transfers its working copy to a different computer, use the registered USB and **Settings > Update USB Copy**. Check the displayed destination, then follow [USB setup and recovery](USB_SETUP.md) on the receiving computer.
5. If the detachment uses Microsoft CIC intake, verify the inbox and form under **Cadet Inventory Cards > Microsoft Intake**. See [Microsoft CIC setup](CIC_MICROSOFT.md).

## Graduation cleanup

1. Open **Cadets** and select the correct profile.
2. Select **Graduation**. Enter the date and select **Expected to graduate** or **Already graduated**.
3. Select **Approve Schedule**, then check the name and dates before confirming. The cleanup date is the first calendar anniversary of graduation. A February 29 graduation uses February 28 the following year.
4. Reopen **Graduation** to revise or cancel a pending schedule. Return any physically received gear through **Returns** during the grace period.
5. Once the schedule is due, A.C.E. processes it after sign-in or during an hourly check while open. The app deducts only units still checked out, preserves the on-shelf count, and removes the affected cadet's live transaction records and associated loan and undo records. The profile and a cleanup summary remain.

Inventory change reports record the stock deduction as **Graduation Acquisition**. Existing backups, USB copies and exported reports can still contain earlier history. SQLite can reuse freed database pages.

## Repository and releases

The public repository contains application source and handoff documentation for all detachments. Keep live SQLite files, device credentials, signed-in accounts, detachment-specific Forms configuration, responses, exported cadet records, and backups outside Git. Build and test the Windows package using the release process documented in the [README](../README.md).
