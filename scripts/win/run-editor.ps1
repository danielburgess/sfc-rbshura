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

$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    throw "No virtual environment found (.venv\Scripts\python.exe). Run scripts\win\setup.ps1 first."
}

Write-Host "==> Launching script editor..." -ForegroundColor Cyan
& $py (Join-Path $RepoRoot 'script_editor.py')
