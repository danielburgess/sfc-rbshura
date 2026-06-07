#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Rushing Beat Shura: The Eternal Conflict — English patch launcher (macOS)
# ---------------------------------------------------------------------------
# A double-clickable launcher (.command opens in Terminal) around the bundled
# cross-platform patcher apply_patch.py (which embeds the IPS — diff data only,
# no copyrighted ROM bytes). Requires Python 3.9+.
#
# Usage:
#   Double-click apply_patch.command in Finder           # file dialog to pick your ROM
#   ./apply_patch.command /path/to/your_rom.sfc          # patch a specific ROM (Terminal)
#
# First-run notes (macOS):
#   * Gatekeeper may block it: right-click -> Open the first time, or run
#       xattr -d com.apple.quarantine apply_patch.command
#   * If not executable yet:  chmod +x apply_patch.command
#   * The file dialog needs Tk. With Homebrew Python:  brew install python-tk
#     (or skip the dialog by passing the ROM path on the command line).
# ---------------------------------------------------------------------------
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/apply_patch.py"

if [ ! -f "$script" ]; then
    echo "error: apply_patch.py not found next to this script ($here)." >&2
    echo "Keep apply_patch.command and apply_patch.py together (as shipped in the zip)." >&2
    exit 1
fi

py="$(command -v python3 || command -v python || true)"
if [ -z "$py" ]; then
    echo "error: Python 3.9+ is required but was not found on PATH." >&2
    echo "Install Python 3 (https://www.python.org/downloads/ or 'brew install python')," >&2
    echo "then re-run this launcher." >&2
    exit 1
fi

exec "$py" "$script" "$@"
