<#
.SYNOPSIS
  Build the English ROM + run the write-provenance audit gate (Windows).

.DESCRIPTION
  Windows equivalent of scripts/build.sh. Builds out\rbshura_br_pt.sfc (+ .ips and
  .xdelta) from the pristine Japanese ROM via retrotool, then runs the
  write-provenance audit gate (tools/audit_writes.py), which fails the build on
  any byte change not attributable to an intentional insertion.

  Requires:
    - scripts\win\setup.ps1 has been run (so .venv exists), and
    - the pristine JP ROM at roms\rbshura.sfc (gitignored for copyright).

.PARAMETER Patcher
  Also regenerate dist\ patcher + patches (release artifacts).

.PARAMETER UpdateAudit
  Re-bless the write footprint after an INTENTIONAL change to what bytes are
  written, then build + audit. Review the manifest diff before committing.
#>
[CmdletBinding()]
param(
    [switch]$Patcher,
    [switch]$UpdateAudit
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $RepoRoot

$venv  = Join-Path $RepoRoot '.venv\Scripts'
$retro = Join-Path $venv 'retrotool.exe'
$py    = Join-Path $venv 'python.exe'

if (-not (Test-Path $retro)) {
    throw "No virtual environment found ($retro). Run scripts\win\setup.ps1 first."
}
if (-not (Test-Path (Join-Path $RepoRoot 'roms\rbshura.sfc'))) {
    throw "Place the pristine JP ROM at roms\rbshura.sfc (gitignored for copyright)."
}

Write-Host "==> Building ROM (retrotool, ips+xdelta)" -ForegroundColor Cyan
& $retro build project.toml -j 1 --no-cache --diff both
if ($LASTEXITCODE -ne 0) { throw "retrotool build failed (exit $LASTEXITCODE)." }

if ($UpdateAudit) {
    Write-Host "==> Re-blessing write footprint (--update-audit)" -ForegroundColor Cyan
    & $py 'tools\audit_writes.py' --update
    if ($LASTEXITCODE -ne 0) { throw "audit --update failed (exit $LASTEXITCODE)." }
}

Write-Host "==> Write-provenance audit gate" -ForegroundColor Cyan
& $py 'tools\audit_writes.py'
if ($LASTEXITCODE -ne 0) { throw "Write-provenance audit FAILED (exit $LASTEXITCODE)." }

if ($Patcher) {
    Write-Host "==> Regenerating dist\ patcher + patches" -ForegroundColor Cyan
    & $py 'tools\make_patcher.py'
    if ($LASTEXITCODE -ne 0) { throw "make_patcher failed (exit $LASTEXITCODE)." }
}

Write-Host "==> OK: out\rbshura_br_pt.sfc built and audited." -ForegroundColor Green
