#!/usr/bin/env bash
# One-shot dev-environment setup (Linux / macOS).
#
# Installs everything needed to build the ROM and run the script editor:
#   1. Installs `uv` (Astral's Python toolchain manager) if it is missing.
#   2. Creates the project virtual environment (.venv) with a matching CPython
#      (uv downloads it if needed).
#   3. Installs retrotool + its bundled-binary toolchains, Pillow, and the
#      script editor's GUI runtime FROM PyPI:
#        retrotool[all]  -> build engine + libsfx / asar / bass / xdelta
#        pillow          -> script editor + PNG encoders
#        pywebview       -> script editor window (Linux adds the [qt] extra;
#                           macOS uses the native Cocoa backend)
#
# Everything comes from PyPI — nothing is sourced from a local checkout. (The
# project's pyproject.toml pins an editable local retrotool via
# [tool.uv.sources] for the maintainer's own machine; this script deliberately
# uses `uv pip install`, which ignores that, so contributors get the published
# package.)
#
# Run this ONCE per machine (or after dependencies change), then verify with
# the checklist it prints at the end. After it succeeds:
#   scripts/run-editor.sh   (script editor)
#   scripts/build.sh        (build the ROM)
set -euo pipefail

RETROTOOL_SPEC='retrotool[all]>=0.9.3'
PY_VERSION='3.13'                       # matches pyproject requires-python

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
echo "==> Project: $REPO_ROOT"

# --- sanity: are we in a retrotool project checkout? -----------------------
if [[ ! -f project.toml ]]; then
    echo "error: no project.toml in $REPO_ROOT — run this from the project checkout." >&2
    exit 1
fi

# --- 1. Ensure uv is installed ---------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    echo "==> Installing uv (Python toolchain manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer puts uv in ~/.local/bin for future shells; add it to this
    # session's PATH so the rest of the script can use it now.
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        echo "error: uv installed but not on PATH in this session." >&2
        echo "       Open a new terminal and re-run scripts/setup.sh." >&2
        exit 1
    fi
fi
echo "==> uv: $(uv --version)"

# --- 2. Create the virtual environment (.venv) -----------------------------
# uv downloads CPython $PY_VERSION if the machine doesn't have it.
echo "==> Creating .venv (CPython $PY_VERSION)..."
uv venv --python "$PY_VERSION"

# --- 3. Install dependencies FROM PyPI -------------------------------------
# `uv pip install <pkg>` installs the named packages from PyPI into .venv — it
# does NOT read pyproject.toml's [tool.uv.sources], so no local/editable
# checkout is used.
case "$(uname -s)" in
    Darwin) WEBVIEW_SPEC='pywebview' ;;        # native Cocoa backend
    *)      WEBVIEW_SPEC='pywebview[qt]' ;;    # Linux: Qt (PyQt6 + WebEngine)
esac
echo "==> Installing $RETROTOOL_SPEC + pillow + $WEBVIEW_SPEC from PyPI..."
uv pip install "$RETROTOOL_SPEC" pillow "$WEBVIEW_SPEC"

# --- 4. Verify the environment ---------------------------------------------
# The checklist below is the "is my dev environment set up properly?" answer
# every other script in scripts/ checks before doing anything.
echo
echo "==> Verifying the environment:"
fail=0
check() {  # check <label> <command...>
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✓ $label"
    else
        echo "  ✗ $label"
        fail=1
    fi
}
check ".venv python"        test -x .venv/bin/python
check "retrotool CLI"       test -x .venv/bin/retrotool
check "retrotool importable" .venv/bin/python -c 'import retrotool'
check "Pillow (PIL)"        .venv/bin/python -c 'import PIL'
check "pywebview (editor)"  .venv/bin/python -c 'import webview'

# The source ROM is a manual step (copyright — never distributed). Read its
# expected path from project.toml so this stays generic across projects.
ROM_PATH="$(.venv/bin/python - <<'EOF' 2>/dev/null || true
import tomllib
print(tomllib.load(open("project.toml","rb"))["rom"]["file"])
EOF
)"
if [[ -n "$ROM_PATH" ]]; then
    if [[ -f "$ROM_PATH" ]]; then
        echo "  ✓ source ROM ($ROM_PATH)"
    else
        echo "  ! source ROM MISSING — place your legally-obtained copy at: $ROM_PATH"
        echo "    (gitignored for copyright; the build and editor need it)"
    fi
fi

if [[ $fail -ne 0 ]]; then
    echo
    echo "Setup FAILED one or more checks — review the output above." >&2
    exit 1
fi
echo
echo "==> OK. Environment ready."
echo "    Next:  scripts/run-editor.sh       (script editor)"
echo "           scripts/build.sh            (build the ROM)"
echo "           scripts/setup-language.sh   (stage a new translation language)"
