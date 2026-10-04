<#
.SYNOPSIS
    Builds the ESFA Mail Backup Windows installer end to end.

.DESCRIPTION
    Runs every step needed to go from source to a working installer:
      1. Install Python dependencies (requirements-dev.txt) into the project's venv.
      2. Run the test suite (skip with -SkipTests).
      3. Package the app with PyInstaller (EsfaMailBackup.spec).
      4. Compile the installer with Inno Setup, passing the version read from VERSION
         (the single source of truth; see VERSION, mailbackup/__init__.py, EsfaMailBackup.spec
         and installer.iss) so the exe and the installer always agree on the version number.

    Run it from anywhere; it locates the repo root from its own location.

.PARAMETER SkipTests
    Skip the pytest run. Use for a quick rebuild while iterating; leave it off before a release.

.PARAMETER NoClean
    Keep previous build/, dist/ and Output/ folders instead of removing them first. Faster, but
    can leave stale files in the package; the default (clean) matches what CI does.

.EXAMPLE
    .\tools\build-installer.ps1
    Full, clean release build: tests, PyInstaller, installer.

.EXAMPLE
    .\tools\build-installer.ps1 -SkipTests -NoClean
    Fast rebuild after a small change, while developing this script or the spec/iss files.
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$NoClean
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Find-Iscc {
    # Newest first; Inno Setup historically installs under Program Files (x86), but newer
    # releases (7+) default to Program Files.
    $candidates = @(
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    $onPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

# ---------------------------------------------------------------------------------------------

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    $VersionFile = Join-Path $RepoRoot 'VERSION'
    if (-not (Test-Path $VersionFile)) { throw "VERSION file not found at $VersionFile" }
    $Version = (Get-Content $VersionFile -Raw).Trim()
    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        throw "VERSION file does not contain a plain x.y.z version: '$Version'"
    }
    Write-Host "ESFA Mail Backup - building installer for version $Version" -ForegroundColor Green

    $VenvPython = Join-Path $RepoRoot 'venv\Scripts\python.exe'
    if (-not (Test-Path $VenvPython)) {
        Write-Step "No venv found at venv\; creating one"
        python -m venv (Join-Path $RepoRoot 'venv')
        if (-not (Test-Path $VenvPython)) { throw "Failed to create the venv at $VenvPython" }
    }

    Write-Step "Installing dependencies (requirements-dev.txt)"
    & $VenvPython -m pip install --quiet --upgrade pip
    & $VenvPython -m pip install --quiet -r (Join-Path $RepoRoot 'requirements-dev.txt')
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }

    if ($SkipTests) {
        Write-Step "Skipping tests (-SkipTests)"
    } else {
        Write-Step "Running tests"
        & $VenvPython -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "Tests failed (exit $LASTEXITCODE); fix them or pass -SkipTests to build anyway" }
    }

    if (-not $NoClean) {
        Write-Step "Cleaning previous build output"
        foreach ($dir in 'build', 'dist', 'Output') {
            $path = Join-Path $RepoRoot $dir
            if (Test-Path $path) { Remove-Item -Recurse -Force $path }
        }
    }

    Write-Step "Packaging the app with PyInstaller"
    & $VenvPython -m PyInstaller (Join-Path $RepoRoot 'EsfaMailBackup.spec') --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }
    $BuiltExe = Join-Path $RepoRoot 'dist\EsfaMailBackup\EsfaMailBackup.exe'
    if (-not (Test-Path $BuiltExe)) { throw "PyInstaller did not produce $BuiltExe" }

    Write-Step "Locating Inno Setup"
    $Iscc = Find-Iscc
    if (-not $Iscc) {
        Write-Host "Inno Setup was not found. Install it, e.g.:" -ForegroundColor Yellow
        Write-Host "  choco install innosetup -y" -ForegroundColor Yellow
        Write-Host "or download it from https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
        throw "ISCC.exe not found"
    }
    Write-Host "Using $Iscc"

    Write-Step "Compiling the installer (AppVersion=$Version)"
    & $Iscc "/DMyAppVersion=$Version" (Join-Path $RepoRoot 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw "ISCC failed (exit $LASTEXITCODE)" }

    $Installer = Join-Path $RepoRoot 'Output\ESFA-Mail-Backup-Setup.exe'
    if (-not (Test-Path $Installer)) { throw "Installer was not produced at $Installer" }

    $ExeVersion = (Get-Item $BuiltExe).VersionInfo.ProductVersion
    $SetupVersion = (Get-Item $Installer).VersionInfo.ProductVersion
    Write-Step "Done"
    Write-Host "  App exe version:      $ExeVersion" -ForegroundColor Green
    Write-Host "  Installer version:    $SetupVersion" -ForegroundColor Green
    Write-Host "  Installer: $Installer" -ForegroundColor Green
}
finally {
    Pop-Location
}
