#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Rushing Beat Shura: The Eternal Conflict — English patch launcher (Linux)
# ---------------------------------------------------------------------------
# Convenience wrapper around the bundled cross-platform patcher apply_patch.py
# (which embeds the IPS — diff data only, no copyrighted ROM bytes). Requires
# Python 3.9+ (standard library only; the file dialog needs Tk — see readme.md).
#
# Usage:
#   ./apply_patch.sh                       # opens a file dialog to pick your ROM
#   ./apply_patch.sh /path/to/your_rom.sfc # patch a specific ROM
#
# If the file is not executable yet:  chmod +x apply_patch.sh   (or: bash apply_patch.sh)
# ---------------------------------------------------------------------------
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/apply_patch.py"

if [ ! -f "$script" ]; then
    echo "error: apply_patch.py not found next to this script ($here)." >&2
    echo "Keep apply_patch.sh and apply_patch.py together (as shipped in the zip)." >&2
    exit 1
fi

py="$(command -v python3 || command -v python || true)"
if [ -z "$py" ]; then
    echo "error: Python 3.9+ is required but was not found on PATH." >&2
    echo "Install Python 3, then re-run this script." >&2
    exit 1
fi

exec "$py" "$script" "$@"
