#!/usr/bin/env python3
"""Every `Self.<name>` in a Swift TEST file must be declared static in that file.

WHY THIS EXISTS (2026-09-27). A delivery of `SegmentStoreTests.swift` called
`Self.makeStore()` four times; the helper in that file is
`Self.storeWithMockTransport()`. The app build was green in 46 seconds and said
nothing, because `BuildProject` builds the APP target and never typechecks the test
bundle — which is also the mechanical cause of #5093's "15+ Swift tests
unexecuted": nothing in the loop ever built the bundle those tests live in.

So this is the cheapest possible stand-in for the typecheck nobody runs. It does not
replace `build-for-testing`; it catches, in milliseconds and without Xcode, the one
error class a lane that cannot compile Swift will keep producing: a helper referenced
under a name it does not have.

Deliberately narrow:
  * `Self.<name>` only, and only in `fichero/Tests`. `self.<name>` reaches instance
    members of a superclass (XCTestCase) and is not decidable by a grep.
  * String literals are stripped first. Several tests are source scanners that look
    for the TEXT "try Self.validateResponseSize" inside production code; those are
    not references and were the first four false positives this found.
  * A name declared anywhere in the file counts, including in an extension of another
    type. Narrowing that further would need real scope analysis, which is what the
    compiler is for.

Usage:
    scripts/check_swift_test_self_references.py            # whole test tree
    scripts/check_swift_test_self_references.py <paths...>  # named files
    scripts/check_swift_test_self_references.py --self-test
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = ROOT / "fichero" / "Tests"

REFERENCE = re.compile(r"\bSelf\.([A-Za-z_][A-Za-z0-9_]*)")
DECLARATION = re.compile(r"\bstatic\s+(?:func|var|let)\s+([A-Za-z_][A-Za-z0-9_]*)")
#: A Swift string literal, including the multiline form. Stripped before matching so a
#: test that SEARCHES production source for "Self.foo" is not read as calling it.
STRING = re.compile(r'"""(?:.|\n)*?"""|"(?:\\.|[^"\\\n])*"')
#: Comments, stripped AFTER strings, which is the whole trick: by then a `//` inside
#: "https://example.com" has already become spaces, so it cannot be mistaken for the
#: start of a comment. Getting that order wrong is how a naive comment stripper eats
#: 74% of a Swift tree (measured, 2026-09-27, in a throwaway script — not shipped).
COMMENT = re.compile(r"/\*(?:.|\n)*?\*/|//[^\n]*")


def blank(text: str, pattern: re.Pattern[str]) -> str:
    """Replace every match with an equal-length run of spaces, newlines kept.

    Length is preserved so reported line numbers stay true.
    """
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def strip_strings(text: str) -> str:
    return blank(text, STRING)


def strip_noise(text: str) -> str:
    """Strings first, then comments. See `COMMENT` for why the order is load-bearing."""
    return blank(strip_strings(text), COMMENT)


def unresolved(path: Path, text: str) -> list[str]:
    code = strip_noise(text)
    declared = set(DECLARATION.findall(code))
    out: list[str] = []
    for match in REFERENCE.finditer(code):
        name = match.group(1)
        if name in declared:
            continue
        line = code[: match.start()].count("\n") + 1
        out.append(f"  {path}:{line}  Self.{name} is not declared static in this file")
    return out


def self_test() -> int:
    missing = unresolved(Path("x.swift"), "func a() { _ = Self.makeStore() }")
    assert missing, "self-test: an undeclared Self.<name> was not reported"
    declared = unresolved(
        Path("x.swift"),
        "static func makeStore() -> Int { 0 }\nfunc a() { _ = Self.makeStore() }",
    )
    assert not declared, f"self-test: a declared helper was reported: {declared}"
    in_string = unresolved(
        Path("x.swift"), 'func a() { _ = source.range(of: "try Self.validateSize") }'
    )
    assert not in_string, f"self-test: a reference inside a string was reported: {in_string}"
    in_comment = unresolved(
        Path("x.swift"), "/// `if Self.shouldUseCompactFlow(...) { }`\nfunc a() {}"
    )
    assert not in_comment, f"self-test: a reference in a doc comment was reported: {in_comment}"
    in_block = unresolved(Path("x.swift"), "/* Self.gone */\nfunc a() {}")
    assert not in_block, f"self-test: a reference in a block comment was reported: {in_block}"
    assert strip_strings('a "bb" c') == 'a      c', "self-test: line length not preserved"
    # The order that matters: a `//` inside a URL string must not start a comment, or
    # the rest of that line — real code — disappears from the scan.
    kept = strip_noise('let u = "https://x/y"\nfunc a() { _ = Self.helper() }')
    assert "Self.helper" in kept, "self-test: a URL string swallowed the line after it"
    print("self-test OK: fires on an undeclared helper, quiet on a declared one and on strings")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()

    paths = [Path(a) for a in argv if not a.startswith("-")]
    if not paths:
        if not TEST_ROOT.is_dir():
            print(f"FAIL: {TEST_ROOT} missing — the check would pass vacuously")
            return 1
        paths = sorted(TEST_ROOT.rglob("*.swift"))

    problems: list[str] = []
    for path in paths:
        try:
            problems.extend(unresolved(path, path.read_text(encoding="utf-8", errors="ignore")))
        except OSError as exc:
            print(f"FAIL: cannot read {path}: {exc}")
            return 1

    # #4382's rule, applied to this scan: a guardrail must know when it has gone
    # blind. 760 Swift test files on 2026-09-27; a run that suddenly sees a third of
    # them is a moved tree, not a clean repo.
    if len(argv) == 0 or not [a for a in argv if not a.startswith("-")]:
        require_scan_floor(len(paths), 400, "Swift test files (760 on 2026-09-27)")
    print(f"swift test Self.<name> references: {len(paths)} file(s) scanned")
    if problems:
        print(f"\nFAIL: {len(problems)} reference(s) name a helper the file does not declare:")
        for line in problems:
            print(line)
        print(
            "\nThis is what `build-for-testing` would say and `BuildProject` will not: "
            "the app\ntarget compiles without the test bundle. Fix the name, or declare "
            "the helper."
        )
        return 1
    print("OK: every Self.<name> resolves to a static declared in its own file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
