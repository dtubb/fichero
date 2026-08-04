#!/usr/bin/env python3
"""MainActor-isolation guardrail for `static` members on SwiftUI `View` types (#4201).

A `View` type is MainActor-isolated under the macOS 26 SDK, so a "pure" helper
declared `static` on it silently INHERITS MainActor. XCTest runs on the main
thread and is immune, but Swift Testing runs `@Test` suites on cooperative-pool
threads — calling such a helper from a suite that is not `@MainActor` trips the
Swift 6 runtime isolation check and SIGTRAPs the WHOLE test process.

That is not theoretical: it cost five red gate runs to diagnose, surfaced only
in `~/Library/Logs/DiagnosticReports/*.ips` (nothing in the xcresults), and the
crash was attributed to whichever unrelated test batch happened to be in flight
(`LibraryView.skippedChildRowNote`, 2026-07-28).

The caller side is the discriminator that makes this practical: a declaration
scan alone yields ~87 candidates, nearly all harmless. Filtering to members
actually reachable from a NON-`@MainActor` Swift Testing suite is what isolates
the real ones.

The hazard is TRANSITIVE: the proven case read three `private static` regexes on
the same type, which inherit MainActor identically, so marking the entry point
`nonisolated` alone does not even compile. Same-type statics read by a flagged
member are reported alongside it, because they are part of the fix.

Exposure GROWS with the XCTest -> Swift Testing migration: converting a suite to
`@Test` turns a previously-immune caller into an exposed one with no change to
the code under test.

Fix: mark the member (and the same-type statics it reads) `nonisolated`, with a
comment noting the `nonisolated` is load-bearing.

Usage:
    scripts/check_mainactor_view_statics.py
    scripts/check_mainactor_view_statics.py --list
    scripts/check_mainactor_view_statics.py --help
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "fichero" / "fichero"
TESTS_DIR = ROOT / "fichero" / "Tests" / "Unit"
RULE_DOC = "#4201"

# Legitimate cases, keyed "Type.member". Each entry states WHY it is safe.
KNOWN_VIOLATIONS: dict[str, str] = {}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)

# `struct Foo: View`, `struct Foo<T>: Something, View` — the conformance list
# runs to `{` or a `where` clause.
_VIEW_TYPE = re.compile(
    r"^\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+)?"
    r"(?:struct|class|enum)\s+(\w+)[^:{\n]*:\s*([^{\n]+)",
    re.MULTILINE,
)
_STATIC_MEMBER = re.compile(
    r"^\s*(?P<prefix>[\w\s@(){}:.,\"]*?)\bstatic\s+(?:func|let|var)\s+(?P<name>\w+)",
    re.MULTILINE,
)
# A Swift Testing suite is a type containing @Test; @MainActor on the type (or
# on the extension/suite annotation) makes it immune.
_SUITE_DECL = re.compile(
    r"((?:@[\w(). \"]+\s*)*)(?:public\s+|internal\s+|final\s+)*"
    r"(?:struct|class|enum|extension)\s+(\w+)",
    re.MULTILINE,
)


def strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _rel(path: Path) -> str:
    """Repo-relative when possible; absolute under a test's tmp dir."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _conforms_to_view(conformances: str) -> bool:
    return any(c.strip() in {"View", "Scene"} for c in conformances.split(","))


def _body_of(text: str, brace_start: int) -> str:
    """Source between the type's opening brace and its match."""
    depth = 0
    for idx in range(brace_start, len(text)):
        if text[idx] == "{":
            depth += 1
        elif text[idx] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start + 1 : idx]
    return text[brace_start:]


def view_statics(app_dir: Path = APP_DIR) -> dict[str, tuple[str, str]]:
    """{"Type.member": (relative_path, member_body)} for non-nonisolated statics."""
    found: dict[str, tuple[str, str]] = {}
    for path in sorted(app_dir.rglob("*.swift")):
        if "Tests" in path.parts or ".build" in path.parts:
            continue
        try:
            text = strip_comments(path.read_text(errors="ignore"))
        except OSError:
            continue
        rel = _rel(path)
        for match in _VIEW_TYPE.finditer(text):
            type_name, conformances = match.group(1), match.group(2)
            if not _conforms_to_view(conformances):
                continue
            brace = text.find("{", match.end() - len(conformances))
            if brace == -1:
                continue
            body = _body_of(text, brace)
            for member in _STATIC_MEMBER.finditer(body):
                if "nonisolated" in member.group("prefix"):
                    continue
                name = member.group("name")
                snippet = body[member.start() : member.start() + 600]
                found[f"{type_name}.{name}"] = (rel, snippet)
    return found


def exposed_test_callers(tests_dir: Path = TESTS_DIR) -> dict[str, set[str]]:
    """{"Type.member": {suite names}} referenced from non-@MainActor @Test suites.

    XCTest suites are skipped deliberately: they run on the main thread, so the
    isolation check cannot fire there.
    """
    callers: dict[str, set[str]] = {}
    for path in sorted(tests_dir.rglob("*.swift")):
        try:
            raw = path.read_text(errors="ignore")
        except OSError:
            continue
        if "@Test" not in raw:
            continue
        text = strip_comments(raw)
        for match in _SUITE_DECL.finditer(text):
            attrs, suite = match.group(1) or "", match.group(2)
            brace = text.find("{", match.end())
            if brace == -1:
                continue
            body = _body_of(text, brace)
            if "@Test" not in body or "@MainActor" in attrs:
                continue
            for ref in re.finditer(r"\b([A-Z]\w+)\.(\w+)", body):
                callers.setdefault(f"{ref.group(1)}.{ref.group(2)}", set()).add(suite)
    return callers


def same_type_statics_read(snippet: str, type_name: str, statics: set[str]) -> list[str]:
    """Same-type statics the member touches — they inherit MainActor too."""
    touched = {
        name
        for name in statics
        if re.search(rf"\b(?:Self|{type_name})\.{name}\b|(?<![.\w]){name}\b", snippet)
    }
    return sorted(touched)


def scan(app_dir: Path = APP_DIR, tests_dir: Path = TESTS_DIR) -> dict[str, str]:
    statics = view_statics(app_dir)
    callers = exposed_test_callers(tests_dir)
    by_type: dict[str, set[str]] = {}
    for key in statics:
        type_name, member = key.rsplit(".", 1)
        by_type.setdefault(type_name, set()).add(member)

    found: dict[str, str] = {}
    for key, suites in callers.items():
        if key not in statics:
            continue
        rel, snippet = statics[key]
        type_name, member = key.rsplit(".", 1)
        siblings = [
            name
            for name in same_type_statics_read(snippet, type_name, by_type.get(type_name, set()))
            if name != member
        ]
        detail = f"{rel} — reachable from non-@MainActor Swift Testing suite(s): {', '.join(sorted(suites))}"
        if siblings:
            detail += f"; also mark same-type statics: {', '.join(siblings)}"
        found[key] = detail
    return found


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        print(f"MainActor View statics reachable from Swift Testing ({len(found)}):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    # #4487 scan floor: 884 app Swift files on 2026-08-02.
    require_scan_floor(
        sum(1 for _ in (ROOT / "fichero" / "fichero").rglob("*.swift")), 400,
        "app Swift files (884 on 2026-08-02)",
    )
    print("MainActor View-statics guardrail: scanned fichero/fichero + fichero/Tests/Unit")
    print(f"  {len(found)} exposed static(s); {len(known)} known.")

    if stale:
        print(f"\n  {len(stale)} KNOWN_VIOLATIONS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} static(s) on a View type reachable from a non-@MainActor @Test suite:")
        for key in new:
            print(f"      {key}  <-  {found[key]}")
        print(
            "\nFix: mark the member `nonisolated` (and every same-type static it reads —\n"
            "isolation is transitive, so a partial fix will not compile). Alternatively\n"
            f"mark the test suite @MainActor. Rule pointer: {RULE_DOC}."
        )
        return 1

    print("\nPASS no View statics are exposed to cooperative-thread test suites.")
    return 0


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(APP_DIR, TESTS_DIR)
    raise SystemExit(main())
