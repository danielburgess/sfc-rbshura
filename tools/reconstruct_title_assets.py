#!/usr/bin/env python3
"""Reconstruct the three assets/ inputs the title encoders need at build time:

    assets/title_cgram.bin         512 B title-screen CGRAM
    assets/title_tilemap_orig.bin  12 KiB combined BG1|BG2|BG3 tilemap blob
    assets/title_flame.bin         384 B BG2 flame tiles (12 x 32 B)

These were originally one-time manual extractions from a Mesen SplitTrace
title-screen snapshot. They were never committed (despite project.toml saying
so) and the dumps are gone, so this rebuilds them from two files that ARE
tracked:

  * dist/rbshura_en.ips      — the v1.1 patch. retrotool emits IPS records at
    absolute (headerless) file offsets, so the built title char ($211000),
    OBJ kanji char ($215000) and combined tilemap blob ($217000) can be read
    straight out of the patch without any ROM.
  * export/title_palette.png — dump_title.py's 16x16-swatch render of the full
    256-color CGRAM. BGR555 -> RGB888 used (v = five<<3 | five>>2), so the top
    5 bits of each channel recover the CGRAM words exactly.

The flame tiles are recovered verbatim (the encoder bakes them into the built
char unchanged at FLAME_SLOTS). The tilemap blob's BG2/BG3 portions are
recovered by inverting encode_title_logo._set_subtitle (kana moved back from
row 4 to row 17, dakuten 3 -> 16, TM back to the kana row, EN subtitle row
zeroed); the BG1 portion is left as the patched map since every build
overwrites it anyway. Validation: tools/validate_title_assets.py re-runs both
EN encoders against the reconstruction and requires byte-identical output vs
the IPS.

Usage:  python tools/reconstruct_title_assets.py
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

CHAR_OFF = 0x211000   # 16 KiB BG1 logo char ($E1:1000)
CHAR_LEN = 0x4000
BLOB_OFF = 0x217000   # 12 KiB BG1+BG2+BG3 tilemap blob ($E1:7000)
BLOB_LEN = 0x3000

# Must match encode_title_logo.py / extract_title_flame.py.
FLAME_SLOTS = [0x7A, 0x7E, 0xAC, 0xAD, 0xAE, 0xDC, 0xEB, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF]

# _set_subtitle geometry (encode_title_logo.py).
BG3 = 0x2000
SUB_ROW, EN_ROW, TM_ROW, TM_COL = 17, 18, 16, 28
KANA_ROW = 4


def ips_writes(path):
    """Parse an IPS patch -> {offset: bytes} (RLE expanded)."""
    b = Path(path).read_bytes()
    assert b[:5] == b"PATCH", "not an IPS file"
    i, out = 5, {}
    while b[i:i + 3] != b"EOF" or len(b) - i > 6:  # tolerate offset 0x454F46
        off = int.from_bytes(b[i:i + 3], "big"); i += 3
        size = int.from_bytes(b[i:i + 2], "big"); i += 2
        if size == 0:  # RLE
            n = int.from_bytes(b[i:i + 2], "big"); i += 2
            out[off] = b[i:i + 1] * n; i += 1
        else:
            out[off] = b[i:i + size]; i += size
        if b[i:i + 3] == b"EOF" and i + 3 >= len(b) - 3:
            break
    return out


def extract(writes, lo, ln):
    """Splice IPS records covering [lo, lo+ln) onto a zero canvas."""
    buf = bytearray(ln)
    covered = bytearray(ln)
    for off, data in writes.items():
        a, b = max(off, lo), min(off + len(data), lo + ln)
        if a < b:
            buf[a - lo:b - lo] = data[a - off:b - off]
            covered[a - lo:b - lo] = b"\x01" * (b - a)
    missing = covered.count(0)
    assert missing == 0, f"IPS does not cover ${lo:06X}+${ln:X} ({missing} B missing)"
    return bytes(buf)


def cgram_from_palette_png(path):
    """export/title_palette.png (16x16 swatches of 16px) -> 512 B CGRAM."""
    im = Image.open(path).convert("RGB")
    assert im.size == (256, 256), f"expected 256x256 palette strip, got {im.size}"
    out = bytearray()
    for i in range(256):
        r, g, b = im.getpixel(((i % 16) * 16, (i // 16) * 16))
        w = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
        out += w.to_bytes(2, "little")
    return bytes(out)


def rows(blob, base=BG3):
    def read(r):
        o = base + r * 64
        return [blob[o + i * 2] | (blob[o + i * 2 + 1] << 8) for i in range(32)]
    def write(r, ents):
        o = base + r * 64
        for i, e in enumerate(ents):
            blob[o + i * 2] = e & 0xFF; blob[o + i * 2 + 1] = (e >> 8) & 0xFF
    return read, write


def invert_subtitle(patched):
    """Patched 12 KiB blob -> a pre-_set_subtitle blob that round-trips."""
    blob = bytearray(patched)
    read, write = rows(blob)
    kana, daku, tmrow = read(KANA_ROW), read(KANA_ROW - 1), read(TM_ROW)
    # Sanity: kana left-aligned at col 3 (so re-running computes shift == 0),
    # and nothing in the kana row collides with the TM capture cols 27/28.
    assert min(c for c in range(32) if kana[c]) == 3, "unexpected kana alignment"
    assert kana[27] == kana[28] == 0, "kana row collides with TM capture cols"
    assert tmrow[TM_COL] and tmrow[TM_COL + 1], "TM tiles not where expected"
    kana[27], kana[28] = tmrow[TM_COL], tmrow[TM_COL + 1]
    write(SUB_ROW, kana)            # kana (+ TM at 27/28) back on row 17
    write(SUB_ROW - 1, daku)        # dakuten back on row 16
    for r in (KANA_ROW - 1, KANA_ROW, EN_ROW):
        write(r, [0] * 32)          # rows the transform writes from scratch
    return bytes(blob)


def main():
    writes = ips_writes(ROOT / "dist/rbshura_en.ips")
    char = extract(writes, CHAR_OFF, CHAR_LEN)
    blob = extract(writes, BLOB_OFF, BLOB_LEN)

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)

    flame = b"".join(char[s * 32:(s + 1) * 32] for s in FLAME_SLOTS)
    assert all(any(flame[i * 32:(i + 1) * 32]) for i in range(len(FLAME_SLOTS))), \
        "blank flame tile recovered — wrong char region?"
    (assets / "title_flame.bin").write_bytes(flame)
    print(f"wrote assets/title_flame.bin ({len(flame)} B)")

    orig = invert_subtitle(blob)
    (assets / "title_tilemap_orig.bin").write_bytes(orig)
    print(f"wrote assets/title_tilemap_orig.bin ({len(orig)} B)")

    cg = cgram_from_palette_png(ROOT / "export/title_palette.png")
    (assets / "title_cgram.bin").write_bytes(cg)
    print(f"wrote assets/title_cgram.bin ({len(cg)} B)")


if __name__ == "__main__":
    main()
