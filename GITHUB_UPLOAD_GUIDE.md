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

1. Open the repository on GitHub.
2. Select **Releases**, then **Draft a new release**.
3. Create a tag such as `v1.0.0`.
4. Title it `A.C.E. Inventory v1.0.0`.
5. Attach `release/A.C.E.zip`.
6. State that the physical Tera 5100 label scan remains the final acceptance check.

The release ZIP is intentionally ignored by git. It should be attached to the Release page, not committed to the repository.
