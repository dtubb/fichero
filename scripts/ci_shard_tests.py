#!/usr/bin/env python3
"""Print the test paths of one CI shard (ci.python-tiers): `ci_shard_tests.py TESTS_DIR SHARD TOTAL`.

Every test_*.py file under TESTS_DIR is an entry, weighed by the tests it defines (its `def test_` lines, at least one).
The entries are dealt to TOTAL shards, heaviest first, each to the shard with the least weight so far; ties go to the lowest
shard. Every file lands in exactly one shard, so the shards together are the whole tier, and a new file or folder joins a
shard without anyone editing the workflow. Files, not folders: one folder (workflows) holds a fifth of the tier and made its
shard twice as long as the others (GitHub run 45666948572)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

_TEST = re.compile(r"^\s*(?:async\s+)?def test_", re.MULTILINE)


def entries(root: Path) -> list[tuple[str, int]]:
    out = []
    for p in sorted(root.rglob("test_*.py")):
        if "__pycache__" not in p.parts:
            out.append((str(p), max(1, len(_TEST.findall(p.read_text(encoding="utf-8", errors="replace"))))))
    return out


def shards(items: list[tuple[str, int]], total: int) -> list[list[str]]:
    load, out = [0] * total, [[] for _ in range(total)]
    for path, n in sorted(items, key=lambda x: (-x[1], x[0])):
        i = load.index(min(load))
        load[i] += n
        out[i].append(path)
    return [sorted(s) for s in out]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.splitlines()[0], file=sys.stderr)
        return 2
    root, shard, total = Path(argv[0]), int(argv[1]), int(argv[2])
    if not 1 <= shard <= total:
        print(f"shard {shard} is not in 1..{total}", file=sys.stderr)
        return 2
    print(" ".join(shards(entries(root), total)[shard - 1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
