#!/usr/bin/env bash
# Launch the translation script editor (Linux / macOS) using the project venv.
#
# Runs script_editor.py — a desktop (pywebview) editor for the translation
# scripts, with a live in-game-font preview. Requires that scripts/setup.sh
# has been run first (so .venv exists), and a built ROM in out/ (the editor
# extracts the text palettes from it — run scripts/build.sh once).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- dev-environment check (before any action) ------------------------------
PY="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
    echo "error: no virtual environment (.venv/bin/python)." >&2
    echo "       Run scripts/setup.sh first." >&2
    exit 1
fi
if ! "$PY" -c 'import webview, PIL' >/dev/null 2>&1; then
    echo "error: the editor's dependencies (pywebview / Pillow) are missing from .venv." >&2
    echo "       Re-run scripts/setup.sh." >&2
    exit 1
fi
if ! ls out/*.sfc >/dev/null 2>&1; then
    echo "error: no built ROM in out/ — the editor reads the text palettes from it." >&2
    echo "       Run scripts/build.sh once, then retry." >&2
    exit 1
fi

echo "==> Launching script editor..."
exec "$PY" "$REPO_ROOT/script_editor.py"
