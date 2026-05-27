#!/usr/bin/env python3
"""Diagnose which JP→EN substitutions failed to match anywhere."""
import split_translations as st

from _paths import DATA_JP

raw = st.DUMP_TRANSLATED.read_text(encoding="utf-8")
resolved = st.resolve_conflicts(raw)
entries = st.parse_translated_dump(resolved)
from retrotool.script.table import Table
table = Table(str(st.RBSHURA_TBL))
subs = st.build_substitutions(entries, table)

# Concatenate all scenario bodies for global search.
corpus = "\n".join(
    f.read_text(encoding="utf-16") for f in sorted(DATA_JP.glob("scenario_*.txt"))
)

hits = []
misses = []
for jp, en in subs:
    if jp in corpus:
        hits.append((jp, en))
    else:
        misses.append((jp, en))

print(f"Hits:   {len(hits)}")
print(f"Misses: {len(misses)}")
print()
print("=== First 10 misses ===")
for jp, en in misses[:10]:
    print(f"  JP: {jp[:120]}")
    print(f"  EN: {en[:120]}")
    print()
