#!/usr/bin/env python3
"""Generate dist/apply_patch.py and stage the release patch files in dist/.

`dist/apply_patch.py` is a self-contained, cross-platform IPS patcher with the
IPS embedded (gzip + base64) and the original/patched SHA-256 baked in. It is
generated from tools/apply_patch_template.py.

Inputs (produced by `./.venv/bin/retrotool build project.toml -j 1 --no-cache --diff both`):
  out/rbshura_en.sfc.ips, out/rbshura_en.sfc.xdelta
ROMs (for the identity hashes):
  roms/rbshura.sfc (original), out/rbshura_en.sfc (patched)

Outputs (TRACKED, distributable — diffs only, no copyrighted ROM data):
  dist/apply_patch.py, dist/rbshura_en.ips, dist/rbshura_en.xdelta

The Windows .exe is built from dist/apply_patch.py by
.github/workflows/release.yml. CI cannot build the ROM itself — the Japanese
source ROM is gitignored for copyright reasons — so the patcher + patches are
generated locally (here) and committed to dist/ for the release.

Repeatable: re-run after every `--patches` build.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import shutil
import sys

from _paths import ROOT, OUT, DIST, PRISTINE_ROM, BUILT_ROM

VERSION = "v1.2"
TITLE = "Rushing Beat Shura: The Eternal Conflict"
OUTPUT_NAME = "Rushing Beat Shura (English).sfc"

IPS_IN = OUT / "rbshura_en.sfc.ips"
XDELTA_IN = OUT / "rbshura_en.sfc.xdelta"
TEMPLATE = ROOT / "tools" / "apply_patch_template.py"


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    missing = [p for p in (PRISTINE_ROM, BUILT_ROM, IPS_IN) if not p.exists()]
    if missing:
        raise SystemExit(
            "missing input(s):\n  " + "\n  ".join(str(p) for p in missing) +
            "\nRun first:  ./.venv/bin/retrotool build project.toml -j 1 --no-cache --diff both"
        )
    DIST.mkdir(parents=True, exist_ok=True)

    ips_bytes = IPS_IN.read_bytes()
    blob = base64.b64encode(gzip.compress(ips_bytes, 9)).decode("ascii")

    repl = {
        "@@TITLE@@": TITLE,
        "@@VERSION@@": VERSION,
        "@@ORIG_SHA256@@": _sha256(PRISTINE_ROM),
        "@@ORIG_SIZE@@": str(PRISTINE_ROM.stat().st_size),
        "@@PATCHED_SHA256@@": _sha256(BUILT_ROM),
        "@@PATCHED_SIZE@@": str(BUILT_ROM.stat().st_size),
        "@@OUTPUT_NAME@@": OUTPUT_NAME,
        "@@PATCH_GZ_B64@@": blob,
    }
    src = TEMPLATE.read_text(encoding="utf-8")
    for token, value in repl.items():
        src = src.replace(token, value)
    leftover = [t for t in repl if t in src]
    if leftover:
        raise SystemExit(f"template tokens not filled: {leftover}")

    out_py = DIST / "apply_patch.py"
    out_py.write_text(src, encoding="utf-8")

    # Stage the raw patches with release-friendly names.
    shutil.copyfile(IPS_IN, DIST / "rbshura_en.ips")
    if XDELTA_IN.exists():
        shutil.copyfile(XDELTA_IN, DIST / "rbshura_en.xdelta")

    # Self-check: exec the generated patcher's apply path against the real ROMs.
    ns: dict = {}
    exec(compile(src, str(out_py), "exec"), ns)  # noqa: S102 - our own generated code
    patched = ns["apply_ips"](ns["_embedded_patch"](), PRISTINE_ROM.read_bytes())
    ok = hashlib.sha256(patched).hexdigest() == repl["@@PATCHED_SHA256@@"]

    print(f"wrote {out_py.relative_to(ROOT)}  ({len(src):,} B, embeds {len(ips_bytes):,} B IPS)")
    print(f"wrote {(DIST / 'rbshura_en.ips').relative_to(ROOT)}")
    if XDELTA_IN.exists():
        print(f"wrote {(DIST / 'rbshura_en.xdelta').relative_to(ROOT)}")
    print(f"self-check: embedded IPS applies to original → patched sha256 "
          f"{'MATCH' if ok else 'MISMATCH!!'}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
