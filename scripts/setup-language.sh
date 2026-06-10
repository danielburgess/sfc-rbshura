#!/usr/bin/env bash
# Stage the project for a NEW translation language (Linux / macOS).
#
# Thin wrapper around tools/setup_language.py (the cross-platform engine):
# asks which language to stage assets from (default: en) and the new language
# code, copies data/<src> -> data/<new>, forks the toml-pointed language
# assets (encoding tables, font bins, art PNGs) next to their originals with
# a _<lang> postfix, and repoints project.toml + the DataDef tomls — printing
# the full plan and asking for confirmation first.
#
# All arguments are forwarded:  --from en --to fr --dry-run --yes --fork-all
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- dev-environment check (before any action) ------------------------------
# (setup_language.py re-checks too; this just gives a friendlier message when
# there is no venv python to run it with.)
PY="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
    echo "error: no virtual environment (.venv/bin/python)." >&2
    echo "       Run scripts/setup.sh first." >&2
    exit 1
fi

exec "$PY" "$REPO_ROOT/tools/setup_language.py" --project "$REPO_ROOT" "$@"
