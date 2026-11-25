#!/usr/bin/env python3
"""Print the test paths of one CI shard (ci.python-tiers): `ci_shard_tests.py TESTS_DIR SHARD TOTAL`.

The entries of TESTS_DIR (each folder, each top-level test_*.py) are dealt to TOTAL shards, largest first by test-file count,
each to the shard with the fewest files so far; ties go to the lowest shard. Every entry lands in exactly one shard, so the
shards together are the whole tier, and a new folder joins a shard without anyone editing the workflow."""
from __future__ import annotations

import sys
from pathlib import Path


def entries(root: Path) -> list[tuple[str, int]]:
    out = []
    for p in sorted(root.iterdir()):
        if p.is_dir() and p.name != "__pycache__" and (n := sum(1 for _ in p.rglob("test_*.py"))):
            out.append((str(p), n))
        elif p.is_file() and p.name.startswith("test_") and p.suffix == ".py":
            out.append((str(p), 1))
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
