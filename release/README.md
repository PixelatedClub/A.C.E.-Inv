# Release Asset

`A.C.E.zip` contains the **unsigned** Windows application, setup utility, program manifest and generic settings. It contains no inventory or cadet data. A prepared USB supplies its initial inventory separately. The Windows release workflow builds and publishes these files after the automated tests and Team Shapes version-metadata checks succeed.

The executable is intentionally unsigned, so Windows may display **Unknown publisher** or a Microsoft Defender SmartScreen warning. Extract the ZIP before launching A.C.E.

The workflow generates `SHA256SUMS.txt` from the final release files.

Raw `A.C.E.exe` and `ace_release.json` assets support verified CIC program updates. Setup installs a prepared USB locally; later updates preserve the computer's working inventory and keep one previous managed program archive. See [installation instructions](../docs/USB_SETUP.md).
