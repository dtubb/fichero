#!/usr/bin/env python3
"""Docs publication guardrail.

Rule: mkdocs builds EVERY `.md` under `docs_dir` into a public page. `nav` controls
site navigation, NOT publication. A page left out of `nav` is still live at its URL,
just unlinked — which is how /ROADMAP/, /CLAUDE/ and /archive/ all shipped publicly
without anyone deciding to publish them. See agents/ROADMAP.md.

So every built page must be either:
  - reachable from `nav`, or
  - listed in check_docs_publication_allowlist.json (public on purpose, unlinked).

A NEW unlinked page fails this check. That is the point: publishing is a decision,
not a side effect of putting a file in a folder. Anything that must never be public
belongs outside docs/ (agent scratch -> agent-work/, priority spine -> agents/).

ponytail: regex over mkdocs.yml, not a yaml parse — pyyaml is not stdlib and the nav
is a flat list of `key: path.md` lines. Guardrails stay cheap enough for every worker.

Usage:
    scripts/check_docs_publication.py
    scripts/check_docs_publication.py --list
    scripts/check_docs_publication.py --write-allowlist   # ratchet after a review
    scripts/check_docs_publication.py --self-test
    scripts/check_docs_publication.py --help
"""
from __future__ import annotations

import json
import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MKDOCS = ROOT / "mkdocs.yml"
ALLOWLIST = Path(__file__).resolve().parent / "check_docs_publication_allowlist.json"
RULE_DOC = "agents/ROADMAP.md"

_MD_IN_NAV = re.compile(r":\s*([A-Za-z0-9_][A-Za-z0-9_./-]*\.md)\s*$")
_DOCS_DIR = re.compile(r"^docs_dir:\s*(\S+)", re.M)
_EXCLUDE_BLOCK = re.compile(r"^exclude_docs:\s*\|\s*$((?:\n[ \t]+.*)*)", re.M)


def docs_dir(text: str) -> Path:
    m = _DOCS_DIR.search(text)
    return ROOT / (m.group(1) if m else "docs")


def nav_pages(text: str) -> set[str]:
    """Every `.md` path referenced from the nav block."""
    nav = text.split("\nnav:", 1)
    if len(nav) != 2:
        return set()
    return {m.group(1) for line in nav[1].splitlines() if (m := _MD_IN_NAV.search(line))}


def excluded(text: str) -> set[str]:
    """Paths mkdocs is told not to build. Leading `/` means docs_dir-relative."""
    m = _EXCLUDE_BLOCK.search(text)
    if not m:
        return set()
    out = set()
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.add(line.lstrip("/"))
    return out


def built_pages(text: str) -> set[str]:
    root = docs_dir(text)
    skip = excluded(text)
    pages = set()
    for p in root.rglob("*.md"):
        rel = p.relative_to(root).as_posix()
        if rel in skip or any(rel.startswith(s.rstrip("/") + "/") for s in skip):
            continue
        pages.add(rel)
    return pages


def load_allowlist() -> set[str]:
    if not ALLOWLIST.exists():
        return set()
    return set(json.loads(ALLOWLIST.read_text()).get("unlinked_public_pages", []))


def scan() -> tuple[set[str], set[str]]:
    """Return (new unlinked pages, stale allowlist entries)."""
    text = MKDOCS.read_text()
    unlinked = built_pages(text) - nav_pages(text)
    allowed = load_allowlist()
    return unlinked - allowed, allowed - unlinked


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    if "--self-test" in argv:
        t = "docs_dir: docs\nexclude_docs: |\n  /README.md\n\nnav:\n  - Home: index.md\n"
        assert nav_pages(t) == {"index.md"}, nav_pages(t)
        assert excluded(t) == {"README.md"}, excluded(t)
        assert docs_dir(t) == ROOT / "docs"
        print("check_docs_publication self-test passed")
        return 0

    text = MKDOCS.read_text()
    unlinked_all = built_pages(text) - nav_pages(text)

    if "--write-allowlist" in argv:
        ALLOWLIST.write_text(
            json.dumps(
                {
                    "_doc": (
                        "Pages built as public URLs but not linked from mkdocs nav. "
                        "Public on purpose. Adding an entry is a decision to publish; "
                        f"see {RULE_DOC}."
                    ),
                    "unlinked_public_pages": sorted(unlinked_all),
                },
                indent=2,
            )
            + "\n"
        )
        print(f"wrote {ALLOWLIST.relative_to(ROOT)} ({len(unlinked_all)} entries)")
        return 0

    new, stale = scan()

    if "--list" in argv:
        print(f"unlinked public pages ({len(unlinked_all)}):\n")
        for p in sorted(unlinked_all):
            print(f"  {'[NEW]' if p in new else '[known]'} {p}")
        return 0

    print("docs publication guardrail")
    print(f"  mkdocs.yml: {MKDOCS.relative_to(ROOT)}")
    # #4487 scan floor: built-pages population on 2026-08-02.
    require_scan_floor(len(built_pages(text)), 61, "built docs pages (~122 on 2026-08-02)")
    print(f"  built pages: {len(built_pages(text))}, in nav: {len(nav_pages(text))}")
    print(f"  unlinked but public: {len(unlinked_all)} ({len(new)} unaccounted)")

    if new or stale:
        print(f"\nFAIL docs publication drift. Rule: {RULE_DOC}")
        for p in sorted(new):
            print(f"  NEW public page not in nav and not allowlisted: {p}")
            print("    -> link it from nav, move it out of docs/, or allowlist it.")
        for p in sorted(stale):
            print(f"  stale allowlist entry (page gone or now in nav): {p}")
        if stale and not new:
            print("\n  Fix stale entries with: scripts/check_docs_publication.py --write-allowlist")
        return 1

    print("\nPASS every built page is navigated or consciously allowlisted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
