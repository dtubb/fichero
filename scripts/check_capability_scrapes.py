#!/usr/bin/env python3
"""Capability-scrape ratchet guardrail (creative-director ruling on `AppSource`).

`fichero/Tests/Unit/general/AppSource.swift` resolves the app's Swift source tree so a
test can load a source file as a `String` and assert on it. Two DIFFERENT intents share
that idiom:

  * CAPABILITY-SCRAPE (the anti-pattern): asserts a feature is PRESENT by string match,
    standing in for a behavior test — e.g. `source.contains("New Entity")`,
    `source.contains("NewEntitySheet(")` (see
    `fichero/Tests/Unit/general/Views/Library/EntitiesTableCreateTests.swift`).
  * GUARDRAIL-SCAN (legitimate): asserts a forbidden pattern is ABSENT across the
    codebase — e.g. "no view uses `.system(size:)`", "no direct NSPasteboard". These are
    fine and must keep passing.

Perfect static classification of "scrape vs. scan" is impossible, so this is a BASELINE
RATCHET, matching check_preview_coverage.py's shape: `capability_scrapes_baseline.txt`
holds the ~227 files that already use the AppSource idiom with a `.contains(` assertion.
The ratchet can only SHRINK:

  * a file NOT in the baseline that starts using the idiom is a NEW capability-scrape —
    FAIL. Write a behavior test instead, or, if it's a legitimate guardrail-scan, add it
    to the baseline with a one-line justification.
  * a baseline entry that no longer uses the idiom (converted to a behavior test, or
    deleted) must be REMOVED from the baseline — leaving it in would let the ratchet
    silently regrow the day someone reintroduces the pattern under the same filename.
    FAIL until removed. This drift check is what makes it a ratchet rather than a static
    allowlist: the goal is the baseline shrinking to zero over time, never growing back.

Pure file parse, no build. Not wired into verify_all.sh (gate-wiring is a separate call).

Usage:
    scripts/check_capability_scrapes.py
    scripts/check_capability_scrapes.py --list
    scripts/check_capability_scrapes.py --update   # rewrite the baseline
    scripts/check_capability_scrapes.py --help
"""
from __future__ import annotations

import sys
from pathlib import Path
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "fichero" / "Tests"
BASELINE = Path(__file__).resolve().parent / "capability_scrapes_baseline.txt"

#: Markers of the AppSource idiom: a reference to the resolver, plus at least one
#: `.contains(` assertion on the loaded source. Both must appear for a file to count —
#: a file that merely mentions AppSource without a `.contains(` check isn't scraping,
#: and a file with `.contains(` unrelated to AppSource isn't this idiom at all.
_APPSOURCE_MARKERS = ("AppSource", "appSource(")
_CONTAINS_MARKER = ".contains("


def uses_appsource_idiom(source: str) -> bool:
    """True if `source` references AppSource (or a local `appSource(...)` helper built
    on it) AND makes at least one `.contains(` assertion — the shape shared by every
    capability-scrape and every source-reading guardrail-scan alike.
    """
    if not any(marker in source for marker in _APPSOURCE_MARKERS):
        return False
    return _CONTAINS_MARKER in source


def scan(tests_dir: Path | None = None, root: Path | None = None) -> set[str]:
    """Repo-relative paths (posix, sorted by caller) of test files using the idiom.

    `tests_dir`/`root` default to the CURRENT module globals (read at call time, not
    at import time) so tests can point this at a temp tree by reassigning
    `check_capability_scrapes.TESTS_DIR` / `.ROOT` rather than only via the parameter.
    """
    tests_dir = tests_dir if tests_dir is not None else TESTS_DIR
    root = root if root is not None else ROOT
    found: set[str] = set()
    for path in scan_rglob(tests_dir, "*.swift"):
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        if uses_appsource_idiom(source):
            found.add(path.relative_to(root).as_posix())
    return found


def _load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    lines = BASELINE.read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


HEADER = (
    "# Capability-scrape ratchet baseline (scripts/check_capability_scrapes.py).\n"
    "#\n"
    "# One repo-relative path per line, sorted. Every file here uses the AppSource\n"
    "# source-reading idiom (references AppSource/appSource( AND asserts .contains(\n"
    "# on the loaded source) — either a grandfathered capability-scrape awaiting a\n"
    "# real behavior test, or a legitimate guardrail-scan for a forbidden pattern.\n"
    "#\n"
    "# This ratchet only SHRINKS: a NEW file using the idiom that is not listed here\n"
    "# fails the guardrail. A listed file that stops using the idiom (converted to a\n"
    "# behavior test, or deleted) must be REMOVED from this list, or the guardrail\n"
    "# fails on ratchet drift — the point is the count trending to zero, not staying\n"
    "# put. Run `scripts/check_capability_scrapes.py --update` to regenerate.\n"
)


def _write_baseline(paths: set[str]) -> list[str]:
    """Edit the baseline in place: drop the entries that no longer scrape, append new ones.

    It used to rewrite the file from the tree, sorted, which dropped every `#` justification a
    person wrote above an entry and every section note, so a reason survived only until the next
    run of the maintenance command this tool offers (#5054). Now the human-written text stays
    where it was; a dropped entry takes the comment lines directly above it along, and the
    JUSTIFIED entries dropped are returned so the caller says so out loud.
    """
    text = BASELINE.read_text() if BASELINE.exists() else HEADER
    header, body = (HEADER, text[len(HEADER):]) if text.startswith(HEADER) else ("", text)
    kept: list[str] = []
    pending: list[str] = []
    listed: set[str] = set()
    dropped_justified: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            pending.append(line)
        elif stripped and stripped not in paths:
            if pending:  # the comment block directly above a dropped entry was its justification
                dropped_justified.append(stripped)
            pending = []
        else:
            kept.extend(pending)
            kept.append(line)
            pending = []
            if stripped:
                listed.add(stripped)
    kept.extend(pending)
    while kept and not kept[-1].strip():
        kept.pop()
    lines = kept + sorted(paths - listed)
    BASELINE.write_text(header + ("\n".join(lines) + "\n" if lines else ""))
    return sorted(dropped_justified)


def _baseline_label() -> str:
    """BASELINE's path relative to ROOT, falling back to the absolute path when the
    two don't share a root (e.g. a test points ROOT at a temp tree but leaves
    BASELINE pointed at the real repo file)."""
    try:
        return str(BASELINE.relative_to(ROOT))
    except ValueError:
        return str(BASELINE)


def check() -> list[str]:
    current = scan()
    baseline = _load_baseline()

    problems: list[str] = []
    baseline_label = _baseline_label()

    new = sorted(current - baseline)
    for path in new:
        problems.append(
            f"NEW capability-scrape idiom in {path}: this file reads app source via "
            "AppSource and asserts .contains( on it, but is not in the baseline. Write "
            "a behavior test instead of a source scrape — or, if this is a legitimate "
            f"guardrail-scan (a forbidden-pattern absence check), add it to "
            f"{baseline_label} with a one-line justification."
        )

    stale = sorted(baseline - current)
    for path in stale:
        problems.append(
            f"ratchet drift: {baseline_label} lists {path}, which no longer "
            "uses the AppSource capability-scrape idiom (file missing, or the .contains( "
            "assertion is gone). Remove it from the baseline — converting a scrape to a "
            "behavior test is the goal, and the baseline must shrink to reflect that."
        )

    return problems


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    if "--update" in argv:
        current = scan()
        dropped = _write_baseline(current)
        print(f"Wrote {len(current)} known capability-scrape idiom file(s) to {BASELINE.name}")
        for path in dropped:
            print(
                f"REMOVED a justified entry (it no longer scrapes, or is gone): {path}",
                file=sys.stderr,
            )
        return 0

    if "--list" in argv:
        current = scan()
        baseline = _load_baseline()
        print(f"Files using the AppSource capability-scrape idiom ({len(current)}):\n")
        for path in sorted(current):
            print(f"  [{'known' if path in baseline else 'NEW'}] {path}")
        return 0

    problems = check()
    if problems:
        print("FAIL check_capability_scrapes:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(
        f"OK check_capability_scrapes: {len(_load_baseline())} known AppSource "
        "capability-scrape/guardrail-scan file(s), no new scrapes, no ratchet drift."
    )
    return 0


if __name__ == "__main__":
    if not TESTS_DIR.exists():
        print(
            f"{Path(__file__).name}: BLIND -- scan root missing: {TESTS_DIR} "
            "(the tree moved; update this guardrail's paths)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    raise SystemExit(main())
