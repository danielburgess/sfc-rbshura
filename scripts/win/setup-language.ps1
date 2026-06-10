<#
.SYNOPSIS
  Stage the project for a NEW translation language (Windows).

.DESCRIPTION
  Thin wrapper around tools\setup_language.py (the cross-platform engine):
  asks which language to stage assets from (default: en) and the new language
  code, copies data\<src> -> data\<new>, forks the toml-pointed language
  assets (encoding tables, font bins, art PNGs) next to their originals with
  a _<lang> postfix, and repoints project.toml + the DataDef tomls — printing
  the full plan and asking for confirmation first.

  Requires that scripts\win\setup.ps1 has been run first (so .venv exists).
  All arguments are forwarded:  --from en --to fr --dry-run --yes --fork-all
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $RepoRoot

# --- dev-environment check (before any action) ------------------------------
# (setup_language.py re-checks too; this just gives a friendlier message when
# there is no venv python to run it with.)
$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    throw "No virtual environment found (.venv\Scripts\python.exe). Run scripts\win\setup.ps1 first."
}

& $py (Join-Path $RepoRoot 'tools\setup_language.py') --project $RepoRoot @Rest
exit $LASTEXITCODE
