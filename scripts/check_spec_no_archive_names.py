#!/usr/bin/env python3
"""No archive names in the specs: a spec line with a word whose lowercased sha256 is in check_spec_no_archive_names.json (the real
archive's person and family names, box and page ids, project folder names) FAILS naming file and line, never the word (#6695).

Why: the specs are published; the archive is private, and a neutral phrase (a notebook corpus, a test page, a letter) says the same.
The list holds hashes, not words, so this public repo does not publish what it forbids. Each line is split into words on anything that
is not a letter or a digit (an id such as AB_CD_12 is its parts), and each word is hashed.

Run: python scripts/check_spec_no_archive_names.py [ROOT]
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

from _scan_files import scan_rglob

WORDS = pathlib.Path(__file__).with_suffix(".json")


WORD = re.compile(r"[A-Za-z0-9]+")


def load_hashes(path: pathlib.Path = WORDS) -> set[str]:
    hashes = set(json.loads(path.read_text(encoding="utf-8"))["sha256_of_lowercased_token"])
    if not hashes:
        raise ValueError(f"{path}: an empty hash list is a guard that sees nothing")
    return hashes


def problems(root: pathlib.Path, hashes: set[str]) -> list[str]:
    specs = root / "docs/contributor_manual/specs"
    files = sorted(scan_rglob(specs, "*.md"))  # a missing specs dir raises: never a clean read of nothing
    if not files:
        return [f"no spec files under {specs}"]
    out = []
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if any(hashlib.sha256(w.lower().encode()).hexdigest() in hashes for w in WORD.findall(line)):
                out.append(f"{f.relative_to(root)}:{n}: an archive name: say a notebook corpus, a test page or a letter")
    return out


def main() -> int:
    found = problems(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "."), load_hashes())
    for p in found:
        print(f"FAIL: {p}")
    print(f"check_spec_no_archive_names: {len(found)} problem(s)" if found else "check_spec_no_archive_names: OK")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
