<#
.SYNOPSIS
  Launch the translation script editor (Windows) using the project venv.

.DESCRIPTION
  Runs script_editor.py — a desktop (pywebview) editor for the translation
  scripts, with a live in-game-font preview. Requires that scripts\win\setup.ps1
  has been run first (so .venv exists).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $RepoRoot

# --- dev-environment check (before any action) ------------------------------
$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    throw "No virtual environment found (.venv\Scripts\python.exe). Run scripts\win\setup.ps1 first."
}
# (EAP=Continue while probing: a failed import is the condition being tested,
# not a script error — PS 5.1 would otherwise throw on the redirected stderr.)
$ErrorActionPreference = 'Continue'
& $py -c 'import webview, PIL' 2>$null
$depsOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = 'Stop'
if (-not $depsOk) {
    throw "The editor's dependencies (pywebview / Pillow) are missing from .venv. Re-run scripts\win\setup.ps1."
}
if (-not (Get-ChildItem (Join-Path $RepoRoot 'out\*.sfc') -ErrorAction SilentlyContinue)) {
    throw "No built ROM in out\ — the editor reads the text palettes from it. Run scripts\win\build.cmd once, then retry."
}

Write-Host "==> Launching script editor..." -ForegroundColor Cyan
& $py (Join-Path $RepoRoot 'script_editor.py')
