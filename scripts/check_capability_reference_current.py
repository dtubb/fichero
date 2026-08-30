#!/usr/bin/env python3
"""Capability-reference freshness guardrail.

The user manual's workflow/tool reference under `docs/user/reference/` is
GENERATED from the engine's own tool registry and shipped workflow presets
(scripts/generate_capability_reference.py). That is the whole point: the manual
cannot claim a prompt the app no longer sends.

Generation only helps if regeneration is enforced. Add a tool, change a prompt
builder, edit a preset's config — and the committed pages silently describe the
old app. So this check regenerates the whole tree into a temp directory and
compares it, file for file, byte for byte, with what is committed. It also
compares the generated mkdocs `nav` block, because a new tool page that nobody
links is an unlinked public page.

Exit codes follow the house convention:
    0  committed pages match the engine
    1  drift — rerun the generator and commit
    2  BLIND — the scan found implausibly little (see scripts/_check_floor.py)

Usage:
    scripts/check_capability_reference_current.py
    scripts/check_capability_reference_current.py --self-test
    scripts/check_capability_reference_current.py --help
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _check_floor import require_scan_floor

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_capability_reference as gen  # noqa: E402

ROOT = gen.ROOT
COMMITTED = gen.OUT_DIR
REMEDY = "rerun scripts/generate_capability_reference.py and commit its output"


def tree(root: Path) -> dict[str, str]:
    """Every markdown page under root, keyed by its path relative to root."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_text()
        for path in sorted(root.rglob("*.md"))
    }


def compare(expected: dict[str, str], actual: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    """Return (missing, unexpected, changed) page paths."""
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    changed = sorted(p for p in set(expected) & set(actual) if expected[p] != actual[p])
    return missing, unexpected, changed


def self_test() -> int:
    """Prove the comparison fires — a check never seen to fail is not a check."""
    expected = {"a.md": "one", "b.md": "two"}
    assert compare(expected, dict(expected)) == ([], [], [])
    assert compare(expected, {"a.md": "one"}) == (["b.md"], [], [])
    assert compare(expected, {**expected, "c.md": "x"}) == ([], ["c.md"], [])
    assert compare(expected, {**expected, "a.md": "edited"}) == ([], [], ["a.md"])
    assert tree(ROOT / "does-not-exist") == {}
    print("check_capability_reference_current self-test passed")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    if "--self-test" in argv:
        return self_test()

    print("capability reference freshness guardrail")
    print(f"  pages: {COMMITTED.relative_to(ROOT)}")

    with tempfile.TemporaryDirectory() as scratch:
        counts = gen.generate(Path(scratch) / "reference")
        expected = tree(Path(scratch) / "reference")
        actual = tree(COMMITTED)

    # #4487 scan floor on the GENERATED population: 126 tools + 51 workflows +
    # 3 index pages = 180 pages on 2026-08-29. Half of that, rounded down.
    require_scan_floor(len(expected), 90, "generated reference pages")
    print(f"  engine says: {counts['tools']} tools, {counts['workflows']} workflows")
    print(f"  regenerated {len(expected)} pages, committed {len(actual)}")

    missing, unexpected, changed = compare(expected, actual)
    expected_nav = gen.nav_block(gen.load_presets(), gen.load_tools())
    nav_stale = gen.committed_nav_block() != expected_nav

    if missing or unexpected or changed or nav_stale:
        print("\nFAIL the committed capability reference no longer matches the engine.")
        for path in missing:
            print(f"  missing page (a tool or workflow was added): {path}")
        for path in unexpected:
            print(f"  stale page (a tool or workflow was removed or renamed): {path}")
        for path in changed:
            print(f"  out of date (description, options, or prompt changed): {path}")
        if nav_stale:
            print("  mkdocs.yml nav block between the generated markers is stale")
        print(f"\n  -> {REMEDY}.")
        return 1

    print("\nPASS the manual's workflow and tool reference matches the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
