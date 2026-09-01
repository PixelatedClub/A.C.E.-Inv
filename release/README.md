# Release Asset

`A.C.E.zip` contains the standalone **unsigned** Windows executable. The Windows release workflow creates it after the complete automated test suite and Team Shapes version-metadata checks succeed, then uploads it as a GitHub Release asset rather than committing it to the repository.

The executable is intentionally unsigned, so Windows may display **Unknown publisher** or a Microsoft Defender SmartScreen warning. Extract the ZIP before launching A.C.E.

The workflow generates `SHA256SUMS.txt` from the final release files.
