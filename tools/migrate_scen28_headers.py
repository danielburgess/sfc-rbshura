#!/usr/bin/env python3
"""Migrate scenario_28.txt for the relocated `kind=script` setup. TWO
transformations applied:

1. Headers `<<$378624:N[$XXX]>>` → `<<$2158592:N[$YYY]>>` so retrotool
   matches them to the new pointer table at $E0:F000 (file 0x20F000 =
   decimal 2158592).

2. Body bracket-tokens with internal spaces `[XX YY ZZ ...]` →
   `[XXYYZZ...]` (concatenated, no spaces). retrotool's encoder treats
   space-separated tokens as LITERAL CHARACTERS (`[`, `F`, `C`, ` `,
   ...) instead of recognizing them as multi-byte sequences. The
   concatenated form `[FC025008]` encodes correctly to bytes
   `FC 02 50 08`. Verified against retrotool's encode_text test cases.

Both transformations are idempotent — re-running on an already-migrated
file is a no-op.

Usage:
    python tools/migrate_scen28_headers.py            # migrates both JP+EN
    python tools/migrate_scen28_headers.py --check    # diff without writing
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLD_TBL_DEC = 378624          # decimal $378624 (legacy custom-dumper addr)
NEW_TBL_DEC = 2158592         # decimal $20F000 = file offset of $E0:F000
DATAPTR_PLACEHOLDER = NEW_TBL_DEC + 0xE7   # arbitrary, post-ptr-table

HEADER_RE = re.compile(r'<<\$(\d+):(\d+)\[\$(\d+)\]>>')
# Body token with internal spaces: `[XX YY ZZ ...]` where each XX is a
# 2-char hex pair separated by a single space. Don't match `[XX]` (no
# spaces — already valid) or `[XX]` with non-hex content (e.g. `[end]`).
SPACE_TOKEN_RE = re.compile(r'\[((?:[0-9A-Fa-f]{2}\s+)+[0-9A-Fa-f]{2})\]')


def migrate_one(path: Path, *, check: bool) -> dict:
    raw = path.read_bytes()
    is_utf16 = raw.startswith(b'\xff\xfe')
    text = raw.decode('utf-16' if is_utf16 else 'utf-8')

    # 1. Header migration
    header_replaced = 0
    header_already = 0
    header_other = 0
    def header_repl(m):
        nonlocal header_replaced, header_already, header_other
        tbl = int(m.group(1))
        idx = int(m.group(2))
        if tbl == OLD_TBL_DEC:
            header_replaced += 1
            return f'<<${NEW_TBL_DEC}:{idx}[${DATAPTR_PLACEHOLDER}]>>'
        elif tbl == NEW_TBL_DEC:
            header_already += 1
            return m.group(0)
        else:
            header_other += 1
            return m.group(0)
    new_text = HEADER_RE.sub(header_repl, text)

    # 2. Body token migration: `[FC 02 50 08]` → `[FC025008]`
    token_replaced = 0
    def token_repl(m):
        nonlocal token_replaced
        token_replaced += 1
        # Strip whitespace, collapse to concatenated hex
        return '[' + ''.join(m.group(1).split()) + ']'
    new_text = SPACE_TOKEN_RE.sub(token_repl, new_text)

    new_raw = (
        (b'\xff\xfe' + new_text.encode('utf-16-le'))
        if is_utf16 else new_text.encode('utf-8')
    )
    summary = {
        'path': str(path),
        'header_replaced': header_replaced,
        'header_already': header_already,
        'header_other': header_other,
        'token_replaced': token_replaced,
        'size_before': len(raw),
        'size_after': len(new_raw),
    }
    if not check and new_raw != raw:
        path.write_bytes(new_raw)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true',
                    help="don't write, just report what would change")
    ap.add_argument('files', nargs='*',
                    default=['data/jp/scenario_28.txt', 'data/en/scenario_28.txt'])
    args = ap.parse_args(argv)

    print(f'Migrating ${OLD_TBL_DEC} (= ${OLD_TBL_DEC:#X}) → '
          f'${NEW_TBL_DEC} (= ${NEW_TBL_DEC:#X} = file $20F000 = SNES $E0:F000)')
    print(f'Data-ptr placeholder: ${DATAPTR_PLACEHOLDER} '
          f'(arbitrary — retrotool re-derives at build under mode=\'relocate\')')
    print()

    for f in args.files:
        p = (ROOT / f).resolve()
        if not p.exists():
            print(f'  ⚠ {f} not found')
            continue
        s = migrate_one(p, check=args.check)
        verb = "would replace" if args.check else "replaced"
        print(f'{s["path"]}:')
        print(f'  {verb} {s["header_replaced"]} header(s); '
              f'{s["header_already"]} already migrated; '
              f'{s["header_other"]} other-format headers')
        print(f'  {verb} {s["token_replaced"]} body token(s) [XX YY ZZ] → [XXYYZZ]')
        if s['size_before'] != s['size_after']:
            print(f'  size {s["size_before"]:,} → {s["size_after"]:,}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
