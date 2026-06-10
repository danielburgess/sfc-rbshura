#!/usr/bin/env python3
"""Validate the reconstructed assets/ title inputs: re-run both EN title
encoders against them and require byte-identical output vs the shipped v1.1
IPS (dist/rbshura_en.ips). Proves the reconstruction reproduces the exact
bytes the lost Mesen-dump originals produced.

Usage:  python tools/validate_title_assets.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.reconstruct_title_assets import ips_writes, extract
from tools import encode_title_logo, encode_title_kanji_meta


def cmp(name, got, want):
    if got == want:
        print(f"  OK  {name}: {len(got)} B byte-identical")
        return True
    diff = next(i for i in range(min(len(got), len(want))) if got[i] != want[i]) \
        if got[:min(len(got), len(want))] != want[:min(len(got), len(want))] else min(len(got), len(want))
    print(f"FAIL  {name}: first diff at +${diff:X} (got {len(got)} B, want {len(want)} B)")
    return False


def main():
    writes = ips_writes(ROOT / "dist/rbshura_en.ips")
    ok = True

    char, blob, *_ = encode_title_logo.encode(ROOT / "export/title_bg1_logo_en.png", ROOT)
    ok &= cmp("BG1 logo char  ($211000)", char, extract(writes, 0x211000, 0x4000))
    ok &= cmp("tilemap blob   ($217000)", blob, extract(writes, 0x217000, 0x3000))

    kchar, kmeta, *_ = encode_title_kanji_meta.encode(
        ROOT / "export/title_kanji_en_expanded.png", root=ROOT)
    ok &= cmp("OBJ kanji char ($215000)", kchar, extract(writes, 0x215000, 0x2000))
    ok &= cmp("metasprites    ($21A200)", kmeta, extract(writes, 0x21A200, len(kmeta)))

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
