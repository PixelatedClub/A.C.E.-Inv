# GitHub Upload Guide

## Repository

Recommended repository name: `ACE-Inventory-System`

Recommended visibility for the first upload: **Private**

Use this description:

> A.C.E. is a portable AFROTC clothing and equipment inventory system built for simple cadet use. It supports WINGS-ready imports and exports, searchable equipment records, compact barcode labels, scanner-based checkout and return, cadet history, reports, backups, and flash-drive deployment on Windows.

## Upload the source

Open PowerShell in this folder and run:

```powershell
git init
git add .
git commit -m "Initial A.C.E. inventory system release"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/ACE-Inventory-System.git
git push -u origin main
```

Create the empty repository on GitHub before adding the remote. Do not add a GitHub-generated README or `.gitignore`, because this folder already contains both.

## Upload the executable

1. Open the repository's **Actions** tab.
2. Select **Windows release (unverified publisher)**.
3. Select **Run workflow** and enter a tag matching the application version, such as `v1.6.5`.
4. Wait for the tests, build, metadata checks, ZIP packaging, and release publication to finish.
5. Download `A.C.E.zip` from the resulting Release page and extract it before running.

The executable carries Team Shapes product metadata but is intentionally unsigned. Windows may display **Unknown publisher** or a SmartScreen warning.

The release ZIP is intentionally ignored by git. It should be attached to the Release page, not committed to the repository.
