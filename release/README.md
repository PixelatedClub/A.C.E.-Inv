# Release Asset

`A.C.E.zip` contains the signed Windows executable. The signed-release GitHub workflow creates it only after Authenticode verification succeeds, then uploads it as a GitHub Release asset rather than committing it to the repository.

The workflow generates `SHA256SUMS.txt` from the final signed files.
