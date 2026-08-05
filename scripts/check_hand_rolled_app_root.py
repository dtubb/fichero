#!/usr/bin/env python3
"""No test hand-rolls the app source root (#4493, instance 100).

## What went wrong that this prevents

`fichero/fichero-tests/AppSource.swift` was written to eliminate one idiom:
resolving the app target's source directory by counting
`deletingLastPathComponent()` calls up from `#filePath` and appending a
hardcoded `"fichero"` suffix. The idiom appeared in 114 files in ten different
depth shapes, and two of those counts were wrong in opposite directions — one
landing a level short, one a level deep. Same copied line, different bugs,
written by different people on different days. That is a defect CLASS.

The helper landed. Nothing forbade the pattern. Within a day
`DocumentTitleTests` was written with a fresh hand-rolled copy, by someone
acting entirely reasonably, because there was no way to find out the helper
existed. **A cleanup that does not forbid the pattern is a cleanup that has to
be repeated**, so the consolidation is only half the fix and this script is the
other half.

## Why the pattern is wrong even when the count is right

A correct count is correct only for the file's CURRENT depth. Moving a test
into a subdirectory — the most ordinary edit there is — silently changes the
answer, and the failure surfaces as an `NSCocoaErrorDomain` read error naming a
path nobody recognises, several tests at a time, with no statement of what was
being looked for. `AppSource` walks UP to a landmark instead of counting, so it
survives the move; and when it cannot find the root it throws saying so.

## Exit codes

    0  no hand-rolled resolver outside AppSource.swift
    1  a file resolves the app root by counting path components
    2  BLIND — the matcher failed its own fixtures, or the scan found
       implausibly few Swift files (#4487). Neither is "clean".
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = [ROOT / "fichero"]

# The one file allowed to do the walking, because doing it once is the point.
ALLOWED = {"AppSource.swift"}

# Two or more chained deletions followed by a hardcoded path suffix. Two is the
# floor, not three: the shallowest real offender deleted twice and appended
# "../fichero". A single deletion is just "the directory containing this file"
# and is not a root resolution at all — matching it would flood the check with
# false positives and get it deleted, which is how guardrails die.
_CHAIN = re.compile(
    r"(?P<origin>URL\(fileURLWithPath:\s*#filePath\)\s*)?"
    r"(?:\.deletingLastPathComponent\(\)\s*){2,}"
    r"\.appendingPathComponent\(\s*\"(?P<suffix>[^\"]*)\""
)

# The suffix names a target in this repo — `fichero`, `fichero/Views/...`,
# `../fichero`, `fichero-api-client`.
_TARGET_SUFFIX = re.compile(r"^(?:\.\./)*fichero(?:[-/]|$)")


def _is_source_root_walk(match: re.Match[str]) -> bool:
    """Is this chain resolving the SOURCE TREE, or some other directory?

    The defect class is specifically "find my own source tree by counting" —
    two signals, either of which is sufficient:

      * the chain starts at `#filePath` (it is walking out of a source file);
      * the suffix names a target directory of this repo.

    Both are needed because either alone is evadable: hoisting `#filePath` into
    a `let` on the previous line defeats the first, and a suffix like
    `"../.."` defeats the second.

    What this deliberately does NOT match is a chain over a path the code was
    HANDED — a built engine bundle, a user-picked document, a temp fixture.
    `URL(fileURLWithPath: exe).deletingLastPathComponent()
    .deletingLastPathComponent().appendingPathComponent("Info.plist")` walks a
    bundle assembled at runtime; its depth is a fact about the bundle format,
    not a guess about where the file happens to sit in the repo, and there is
    no shared helper that could replace it.
    """
    return bool(match.group("origin")) or bool(
        _TARGET_SUFFIX.match(match.group("suffix"))
    )


# --- The fixture. ------------------------------------------------------------
#
# In the style of the #4416 matcher self-test: every shape that ACTUALLY
# existed in the tree is listed, so a future narrowing of the regex fails HERE,
# loudly, at the point of the narrowing — rather than going quiet across 114
# files and reporting a clean tree it never looked at. A matcher that has never
# been observed to fire is indistinguishable from one that cannot.

MUST_FIRE = [
    # The four depth shapes that were in the tree on 2026-08-03.
    'URL(fileURLWithPath: #filePath).deletingLastPathComponent()'
    '.deletingLastPathComponent().appendingPathComponent("../fichero")',
    'URL(fileURLWithPath: #filePath).deletingLastPathComponent()'
    '.deletingLastPathComponent().deletingLastPathComponent()'
    '.appendingPathComponent("fichero")',
    'URL(fileURLWithPath: #filePath).deletingLastPathComponent()'
    '.deletingLastPathComponent().deletingLastPathComponent()'
    '.deletingLastPathComponent().appendingPathComponent("fichero")',
    # Suffixed variants — the root plus a path inside the app target.
    'URL(fileURLWithPath: #filePath).deletingLastPathComponent()'
    '.deletingLastPathComponent().deletingLastPathComponent()'
    '.appendingPathComponent("fichero/Views")',
    'URL(fileURLWithPath: #filePath).deletingLastPathComponent()'
    '.deletingLastPathComponent().deletingLastPathComponent()'
    '.appendingPathComponent("fichero/Models/SessionStore.swift")',
    # A sibling target, which is the same resolution with a different suffix
    # and would otherwise be the loophole the class crawls back through.
    'URL(fileURLWithPath: #filePath).deletingLastPathComponent()'
    '.deletingLastPathComponent().deletingLastPathComponent()'
    '.appendingPathComponent("fichero-api-client")',
    # Written across lines, which is how most of them were actually written.
    "URL(fileURLWithPath: #filePath)\n"
    "    .deletingLastPathComponent()\n"
    "    .deletingLastPathComponent()\n"
    "    .deletingLastPathComponent()\n"
    '    .appendingPathComponent("fichero")',
    # `#filePath` hoisted onto a previous line — the obvious evasion. Caught by
    # the suffix rather than the origin, which is why both signals exist.
    'here.deletingLastPathComponent().deletingLastPathComponent()'
    '.appendingPathComponent("fichero/Models")',
]

MUST_NOT_FIRE = [
    # The replacement. If this ever matched, the fix would be unlandable.
    "try AppSource.root()",
    'try AppSource.root().appendingPathComponent("Views")',
    'try AppSource.text("Models/BreadcrumbBuilder.swift")',
    'try AppSource.sibling("fichero-api-client")',
    # One deletion is "the containing directory", not a root walk.
    'url.deletingLastPathComponent().appendingPathComponent("sidecar.json")',
    # Chained deletions with no hardcoded suffix — a real relative walk, e.g.
    # climbing from a document URL the USER picked. Nothing to get wrong.
    "url.deletingLastPathComponent().deletingLastPathComponent()",
    # A computed component is not a hardcoded suffix.
    ".deletingLastPathComponent().deletingLastPathComponent()"
    ".appendingPathComponent(relativePath)",
    # REAL, and legitimately not the class: walking a runtime-built engine
    # bundle to its Info.plist (EmbeddedBackendServiceStartGuardTests). The
    # depth is a fact about the .app format, not a guess about repo layout,
    # and no shared helper could replace it. This one is in the fixture
    # because the first draft of the matcher flagged it.
    'URL(fileURLWithPath: exe).deletingLastPathComponent()'
    '.deletingLastPathComponent().appendingPathComponent("Info.plist")',
    # Same shape over a user-picked document.
    'picked.deletingLastPathComponent().deletingLastPathComponent()'
    '.appendingPathComponent("sidecar.json")',
]


def _self_test() -> list[str]:
    """Prove the matcher fires before trusting it to report a clean tree."""
    failures = []
    for text in MUST_FIRE:
        if not any(_is_source_root_walk(m) for m in _CHAIN.finditer(text)):
            failures.append(f"MISSED: {text!r}")
    for text in MUST_NOT_FIRE:
        if any(_is_source_root_walk(m) for m in _CHAIN.finditer(text)):
            failures.append(f"FALSE POSITIVE: {text!r}")
    return failures


# Directories holding code we did not write and cannot fix: SwiftPM's vendored
# checkouts and build products. swift-nio-http2 resolves a path by counting
# components in one of its benchmarks, which is a true match for the pattern
# and none of our business.
#
# This exclusion matters more than it looks. These paths only exist after
# someone runs a build or a spec regen, so the check passes in a fresh worktree
# and fails in a used one -- and a guardrail that fires on vendored code, for
# reasons the reader cannot act on, is a guardrail somebody switches off. A
# disabled check is worse than an absent one: it still looks present.
# `SourcePackages` is where XCODE puts SPM checkouts (as opposed to `.build`,
# which is where the swift CLI puts them) — so a release build in a worktree
# populated fichero/build/xcode/SourcePackages/checkouts/ and this check started
# firing on swift-nio-http2's benchmark, exactly the case the comment above
# already anticipated but the tuple did not cover (2026-08-05).
VENDORED = (".build", "DerivedData", "Pods", ".swiftpm", "SourcePackages", "checkouts")


def _swift_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.swift")):
            if any(part in VENDORED for part in path.parts):
                continue
            files.append(path)
    return files


def offenders(files: list[Path]) -> list[tuple[str, int]]:
    bad: list[tuple[str, int]] = []
    for path in files:
        if path.name in ALLOWED:
            continue
        text = path.read_text(errors="ignore")
        for match in _CHAIN.finditer(text):
            if not _is_source_root_walk(match):
                continue
            line = text[: match.start()].count("\n") + 1
            bad.append((path.relative_to(ROOT).as_posix(), line))
    return bad


def main() -> int:
    # The matcher proves itself first. A regex that has stopped matching is not
    # a clean tree, and the two must never share exit code 0.
    failures = _self_test()
    if failures:
        print(
            "hand-rolled-app-root guardrail: BLIND — the matcher no longer "
            "recognises shapes that were REAL in this repo, so a green result "
            "would mean nothing:\n  " + "\n  ".join(failures),
            file=sys.stderr,
        )
        return 2

    files = _swift_files()
    # #4487 scan floor: 1401 Swift files under fichero/ on 2026-08-03.
    require_scan_floor(len(files), 700, "Swift files under fichero/ (1401 on 2026-08-03)")

    bad = offenders(files)
    if not bad:
        print(
            f"hand-rolled-app-root guardrail: {len(files)} Swift files, no "
            "hand-rolled app-root resolution outside AppSource.swift."
        )
        return 0

    print(
        f"hand-rolled-app-root guardrail FAILED — {len(bad)} site(s) resolve a "
        "source root by COUNTING path components and appending a hardcoded "
        "suffix. That answer is correct only for the file's current depth: "
        "move the file and it silently resolves somewhere else, failing later "
        "as a file-not-found in an unrelated assertion (#4493).\n\n"
        "Use the shared helper in fichero/fichero-tests/AppSource.swift, which "
        "walks UP to a landmark instead of counting, and throws naming the "
        "path and the landmark when it cannot find the root:\n"
        "    try AppSource.root()                      // fichero/fichero\n"
        '    try AppSource.root().appendingPathComponent("Views")\n'
        '    try AppSource.text("Models/DocumentStore.swift")\n'
        '    try AppSource.sibling("fichero-api-client")\n'
    )
    for path, line in bad:
        print(f"  {path}:{line}")
    return 1


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(SCAN_ROOTS, ROOT / "fichero" / "fichero-tests" / "AppSource.swift")
    raise SystemExit(main())
