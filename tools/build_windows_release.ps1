param(
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $projectRoot "build_release"
$distRoot = Join-Path $buildRoot "dist"
$workRoot = Join-Path $buildRoot "work"
$specRoot = Join-Path $buildRoot "spec"
$releaseRoot = Join-Path $projectRoot "release"

if (Test-Path -LiteralPath $buildRoot) {
    $resolvedBuildRoot = [System.IO.Path]::GetFullPath($buildRoot)
    $resolvedProjectRoot = [System.IO.Path]::GetFullPath($projectRoot)
    if (-not $resolvedBuildRoot.StartsWith($resolvedProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a build directory outside the project."
    }
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $distRoot, $workRoot, $specRoot, $releaseRoot -Force | Out-Null

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "A.C.E",
    "--distpath", $distRoot,
    "--workpath", $workRoot,
    "--specpath", $specRoot,
    "--icon", (Join-Path $projectRoot "portable_data\app_icon.ico"),
    "--version-file", (Join-Path $projectRoot "tools\windows_version_info.txt"),
    "--add-data", "$(Join-Path $projectRoot 'app_settings.json');.",
    "--add-data", "$(Join-Path $projectRoot 'portable_data\app_icon.ico');portable_data",
    "--add-data", "$(Join-Path $projectRoot 'portable_data\window_icon.png');portable_data",
    "--add-data", "$(Join-Path $projectRoot 'portable_data\startup_assets');portable_data\startup_assets",
    "--add-data", "$(Join-Path $projectRoot 'portable_data\suit_icons');portable_data\suit_icons",
    (Join-Path $projectRoot "main.py")
)

& $PythonPath @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$builtExe = Join-Path $distRoot "A.C.E.exe"
if (-not (Test-Path -LiteralPath $builtExe)) {
    throw "PyInstaller did not create A.C.E.exe."
}

Copy-Item -LiteralPath $builtExe -Destination (Join-Path $releaseRoot "A.C.E.exe") -Force
Write-Host "Built unsigned release executable: $releaseRoot\A.C.E.exe"
