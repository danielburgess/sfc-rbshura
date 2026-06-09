<#
.SYNOPSIS
  One-shot environment setup for Rushing Beat Shura (Windows).

.DESCRIPTION
  Installs everything needed to build the ROM and run the script editor:
    1. Installs `uv` (Astral's Python project manager) if it is missing.
    2. Uses uv to download a matching CPython (per `requires-python` in
       pyproject.toml) — no separate Python install needed.
    3. Creates the project virtual environment (.venv) and installs all
       dependencies via `uv sync`.

  Run this ONCE per machine (or after dependencies change). After it succeeds,
  use scripts\win\run-editor.cmd and scripts\win\build.cmd.

  NOTE: pyproject.toml currently pins `retrotool` (the build engine) to a local
  editable checkout. If you are not the original author, you must have a
  retrotool checkout available and point `[tool.uv.sources]` in pyproject.toml
  at it (or pass -RetrotoolPath here) — otherwise `uv sync` cannot resolve it.

.PARAMETER RetrotoolPath
  Optional path to a local retrotool checkout. When given, the script rewrites
  the `[tool.uv.sources]` retrotool paths in pyproject.toml to point at it
  before syncing (a backup is written to pyproject.toml.bak).
#>
[CmdletBinding()]
param(
    [string]$RetrotoolPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Repo root = two levels up from this script (scripts\win\..\..).
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $RepoRoot
Write-Host "==> Project: $RepoRoot" -ForegroundColor Cyan

# --- 1. Ensure uv is installed --------------------------------------------
function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command 'uv')) {
    Write-Host "==> Installing uv (Python toolchain manager)..." -ForegroundColor Cyan
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        throw "Failed to install uv automatically. Install it manually from https://docs.astral.sh/uv/ and re-run this script. ($_)"
    }
    # The installer adds uv to %USERPROFILE%\.local\bin for the *future* shells;
    # add it to this session's PATH so the rest of the script can use it.
    $uvBin = Join-Path $env:USERPROFILE '.local\bin'
    if (Test-Path (Join-Path $uvBin 'uv.exe')) { $env:Path = "$uvBin;$env:Path" }
    if (-not (Test-Command 'uv')) {
        throw "uv was installed but is not on PATH in this session. Close and reopen your terminal, then re-run setup."
    }
}
Write-Host ("==> uv: " + (uv --version)) -ForegroundColor Green

# --- 2. Optional: repoint retrotool source at a local checkout -------------
if ($RetrotoolPath) {
    $rt = (Resolve-Path $RetrotoolPath).Path
    if (-not (Test-Path $rt)) { throw "RetrotoolPath not found: $rt" }
    $pyproj = Join-Path $RepoRoot 'pyproject.toml'
    Copy-Item $pyproj "$pyproj.bak" -Force
    Write-Host "==> Pointing [tool.uv.sources] retrotool at $rt (backup: pyproject.toml.bak)" -ForegroundColor Cyan
    # Replace the hard-coded /mnt/crucial/projects/retrotool prefix with the
    # supplied checkout. Forward slashes are valid in TOML on Windows.
    $rtFwd = $rt -replace '\\','/'
    (Get-Content $pyproj -Raw) `
        -replace '/mnt/crucial/projects/retrotool', $rtFwd `
        | Set-Content $pyproj -NoNewline
}

# --- 3. Sync the environment (downloads Python + installs deps) ------------
Write-Host "==> uv sync (downloads CPython, creates .venv, installs deps)..." -ForegroundColor Cyan
try {
    uv sync
} catch {
    Write-Host ""
    Write-Host "uv sync failed." -ForegroundColor Red
    Write-Host "The most common cause is the `retrotool` dependency: pyproject.toml's" -ForegroundColor Yellow
    Write-Host "[tool.uv.sources] points it at a local checkout that doesn't exist here." -ForegroundColor Yellow
    Write-Host "Re-run with:  scripts\win\setup.ps1 -RetrotoolPath C:\path\to\retrotool" -ForegroundColor Yellow
    throw
}

# --- 4. Verify ------------------------------------------------------------
$retro = Join-Path $RepoRoot '.venv\Scripts\retrotool.exe'
if (Test-Path $retro) {
    Write-Host "==> OK. Environment ready (.venv created, retrotool installed)." -ForegroundColor Green
    Write-Host "    Next:  scripts\win\run-editor.cmd   (script editor)" -ForegroundColor Green
    Write-Host "           scripts\win\build.cmd        (build the ROM)" -ForegroundColor Green
} else {
    Write-Host "==> uv sync completed but .venv\Scripts\retrotool.exe is missing." -ForegroundColor Yellow
    Write-Host "    Check that the retrotool dependency resolved correctly." -ForegroundColor Yellow
}
