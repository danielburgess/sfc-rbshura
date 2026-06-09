<#
.SYNOPSIS
  One-shot environment setup for Rushing Beat Shura (Windows).

.DESCRIPTION
  Installs everything needed to build the ROM and run the script editor:
    1. Installs `uv` (Astral's Python toolchain manager) if it is missing.
    2. Creates the project virtual environment (.venv) with a matching CPython
       (uv downloads it if needed).
    3. Installs retrotool + its bundled-binary toolchains and Pillow FROM PyPI:
       `retrotool[all]` pulls in libsfx / asar / bass / xdelta.

  Everything comes from PyPI — nothing is sourced from a local checkout. (The
  project's pyproject.toml pins an editable local retrotool via
  [tool.uv.sources] for the maintainer's own machine; this script deliberately
  uses `uv pip install`, which ignores that, so contributors get the published
  package.)

  Run this ONCE per machine (or after dependencies change). After it succeeds,
  use scripts\win\run-editor.cmd and scripts\win\build.cmd.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Repo root = two levels up from this script (scripts\win\..\..).
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $RepoRoot
Write-Host "==> Project: $RepoRoot" -ForegroundColor Cyan

# retrotool[all] = build engine + bundled libsfx/asar/bass/xdelta binaries.
# >=0.9.3 is required for the `build_lang` selector this project's project.toml
# uses. Pillow (separate) is used by the script editor + the PNG encoders.
$RetrotoolSpec = 'retrotool[all]>=0.9.3'
$PyVersion = '3.13'                       # matches pyproject requires-python

# --- 1. Ensure uv is installed --------------------------------------------
function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command 'uv')) {
    Write-Host "==> Installing uv (Python toolchain manager)..." -ForegroundColor Cyan
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        throw "Failed to install uv automatically. Install it from https://docs.astral.sh/uv/ and re-run this script. ($_)"
    }
    # The installer adds uv to %USERPROFILE%\.local\bin for future shells; add it
    # to this session's PATH so the rest of the script can use it now.
    $uvBin = Join-Path $env:USERPROFILE '.local\bin'
    if (Test-Path (Join-Path $uvBin 'uv.exe')) { $env:Path = "$uvBin;$env:Path" }
    if (-not (Test-Command 'uv')) {
        throw "uv was installed but is not on PATH in this session. Close and reopen your terminal, then re-run setup."
    }
}
Write-Host ("==> uv: " + (uv --version)) -ForegroundColor Green

# --- 2. Create the virtual environment (.venv) ----------------------------
# uv downloads CPython $PyVersion if the machine doesn't have it.
Write-Host "==> Creating .venv (CPython $PyVersion)..." -ForegroundColor Cyan
uv venv --python $PyVersion
if ($LASTEXITCODE -ne 0) { throw "uv venv failed (exit $LASTEXITCODE)." }

# --- 3. Install dependencies FROM PyPI ------------------------------------
# `uv pip install <pkg>` installs the named packages from PyPI into .venv — it
# does NOT read pyproject.toml's [tool.uv.sources], so no local/editable
# checkout is used.
Write-Host "==> Installing $RetrotoolSpec + pillow from PyPI..." -ForegroundColor Cyan
uv pip install $RetrotoolSpec pillow
if ($LASTEXITCODE -ne 0) { throw "uv pip install failed (exit $LASTEXITCODE)." }

# --- 4. Verify ------------------------------------------------------------
$retro = Join-Path $RepoRoot '.venv\Scripts\retrotool.exe'
if (Test-Path $retro) {
    Write-Host "==> OK. Environment ready (.venv created, retrotool[all] + pillow installed from PyPI)." -ForegroundColor Green
    Write-Host "    Next:  scripts\win\run-editor.cmd   (script editor)" -ForegroundColor Green
    Write-Host "           scripts\win\build.cmd        (build the ROM)" -ForegroundColor Green
} else {
    throw ".venv\Scripts\retrotool.exe is missing after install — check the output above."
}
