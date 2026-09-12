#!/usr/bin/env python3
"""Xcode Preview coverage guardrail (ui-testing-strategy).

Rule (spec: docs/contributor_manual/specs/testing/ui-testing-strategy.md):

    > Xcode Previews rendered via RenderPreview are the CHEAP cross-platform
    > verification layer (no app launch). We can't lean on them if surfaces
    > ship without one. So: every file that declares a SwiftUI `View` must carry
    > a `#Preview` — a new surface cannot proceed until it has one.

This is a ratchet, like check_accessibility.py: `check_preview_coverage_baseline.json`
holds the CURRENT backlog of view files with no `#Preview`. The script passes today
and fails only when a NEW view file ships without a preview — so coverage can only go
up. When you add a preview to a backlog file it drops out automatically; run --update
to prune the baseline (review the diff).

Conservative: only files that DECLARE a `struct … : … View` are required to have a
preview (a `ViewModifier`/`ButtonStyle`/pure-helper file is not flagged). A view
previewed only via a separate `*PreviewCatalog.swift` still counts as covered if that
catalog names it — see COVERED_ELSEWHERE.

Usage:
    scripts/check_preview_coverage.py
    scripts/check_preview_coverage.py --list
    scripts/check_preview_coverage.py --update   # rewrite the baseline JSON
    scripts/check_preview_coverage.py --help
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
BASELINE = Path(__file__).resolve().parent / "check_preview_coverage_baseline.json"
SPEC_DOC = "docs/contributor_manual/specs/testing/ui-testing-strategy.md"

# A file declares a SwiftUI View if a struct conforms to `View` (word-bounded, so
# `ViewModifier`/`ViewBuilder` do NOT match). Handles generics + extra conformances.
_VIEW_STRUCT = re.compile(r"\bstruct\s+\w+[^{\n]*:\s*[^{\n]*\bView\b")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")

#: How many view-declaring files the last scan examined. A sweep for an ABSENCE
#: (#4382) must know it measured something: at zero violations, "every view has a
#: preview" and "the detector matched no views at all" print the same line. Assert
#: the floor, not the result.
VIEWS_SEEN = 0
MIN_VIEWS_SEEN = 100  # the tree holds hundreds; under this, assume the detector broke.


def _decomment(text: str) -> str:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())


def scan(views_dir: Path = VIEWS_DIR) -> dict[str, str]:
    """Return {relative-path: reason} for view files lacking a #Preview."""
    global VIEWS_SEEN
    VIEWS_SEEN = 0
    missing: dict[str, str] = {}
    for path in sorted(views_dir.rglob("*.swift")):
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        code = _decomment(source)
        if not _VIEW_STRUCT.search(code):
            continue  # not a SwiftUI View file — not required to have a preview.
        VIEWS_SEEN += 1
        if "#Preview" in code:
            continue  # has an inline preview — covered.
        missing[path.relative_to(views_dir).as_posix()] = "declares a View, no #Preview"
    return missing


def _load_baseline() -> dict[str, str]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text())


def _require_scan_root(root: Path) -> None:
    if not root.exists():
        print(
            f"{Path(__file__).name}: BLIND -- scan root missing: {root} "
            "(the tree moved; update this guardrail's paths)",
            file=sys.stderr,
        )
        sys.exit(2)


def _require_views_seen() -> None:
    if VIEWS_SEEN >= MIN_VIEWS_SEEN:
        return
    print(
        f"{Path(__file__).name}: BLIND -- examined only {VIEWS_SEEN} view file(s), "
        f"expected at least {MIN_VIEWS_SEEN}. The detector broke or the tree moved; "
        "a clean result here would be a measurement of nothing.",
        file=sys.stderr,
    )
    sys.exit(2)


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    missing = scan()
    _require_views_seen()

    if "--update" in argv:
        BASELINE.write_text(json.dumps(dict(sorted(missing.items())), indent=2) + "\n")
        print(f"Wrote {len(missing)} known preview-less view files to {BASELINE.name}")
        return 0

    known = set(_load_baseline())

    if "--list" in argv:
        print(f"View files without a #Preview ({len(missing)}):\n")
        for key in missing:
            print(f"  [{'known' if key in known else 'NEW'}] {key}")
        return 0

    new = sorted(set(missing) - known)
    stale = sorted(known - set(missing))

    print("Xcode Preview coverage guardrail (ui-testing-strategy):")
    print(f"  scanned {VIEWS_DIR.relative_to(ROOT)}, {VIEWS_SEEN} view file(s) examined")
    print(f"  {len(missing)} view file(s) without a #Preview; {len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} NEW view file(s) shipped WITHOUT a #Preview:")
        for key in new:
            print(f"      {key}")
        print(
            "\nFix: add a `#Preview { … }` (with a realistic fixture) to each new view so it "
            "renders in the cheap RenderPreview layer — a surface can't proceed without one.\n"
            f"Rule: {SPEC_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} baseline entr(ies) now have a preview — run --update to drop:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ No new view files without a preview.")
    return 0


if __name__ == "__main__":
    _require_scan_root(VIEWS_DIR)
    raise SystemExit(main())
