#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Canonical build for the Rushing Beat Shura: The Eternal Conflict EN patch.
# ---------------------------------------------------------------------------
# Builds the English ROM from the pristine Japanese ROM, then runs the
# write-provenance audit GATE. The audit fails the build if any byte changed
# vs pristine is not attributable to an intentional insertion — collisions,
# stray writes, a freespace pool that isn't actually free, or a section's
# footprint growing into adjacent game data. See tools/audit_writes.py.
#
# Requires roms/rbshura.sfc (the pristine JP ROM — gitignored for copyright).
#
# Usage:
#   scripts/build.sh                 # build + audit gate
#   scripts/build.sh --patcher       # also regenerate dist/ patches + apply_patch.py
#   scripts/build.sh --update-audit  # re-bless the write footprint (after an
#                                    #   intentional change), then build + audit
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

VENV=./.venv/bin
[ -x "$VENV/retrotool" ] || { echo "error: no $VENV/retrotool — run scripts/setup.sh first (maintainers: 'uv sync')"; exit 1; }
[ -f roms/rbshura.sfc ]  || { echo "error: place the pristine JP ROM at roms/rbshura.sfc"; exit 1; }

do_patcher=0
do_update=0
for arg in "$@"; do
    case "$arg" in
        --patcher)      do_patcher=1 ;;
        --update-audit) do_update=1 ;;
        *) echo "unknown arg: $arg"; exit 2 ;;
    esac
done

echo "==> Building ROM (retrotool, ips+xdelta)"
$VENV/retrotool build project.toml -j 1 --no-cache --diff both

if [ "$do_update" = 1 ]; then
    echo "==> Re-blessing write footprint (--update-audit)"
    $VENV/python tools/audit_writes.py --update
fi

echo "==> Write-provenance audit gate"
$VENV/python tools/audit_writes.py

if [ "$do_patcher" = 1 ]; then
    echo "==> Regenerating dist/ patcher + patches"
    $VENV/python tools/make_patcher.py
fi

echo "==> OK: out/rbshura_en.sfc built and audited."
