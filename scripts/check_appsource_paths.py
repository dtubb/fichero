#!/usr/bin/env python3
"""appSource() path guardrail.

Many unit tests read app SOURCE by a literal relative path via the shared
`appSource("Views/...")` / `appSourceRoot(...)` helper, which resolves against
`fichero/fichero/` and does `String(contentsOf:)`. A stale path COMPILES FINE
but throws CocoaError (file-not-found) at RUNTIME — so a compile-only gate
(build-for-testing) misses it. This check verifies every quoted appSource path
points at a real file, catching the breakage a file MOVE introduces without
running the whole (GUI-launching) test bundle.

Exit codes:
    0  every appSource("...") path resolves to a real file
    1  a test references a source path that no longer exists
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = ROOT / "fichero" / "fichero"           # appSource() resolves here
TEST_DIRS = [ROOT / "fichero" / "fichero-tests", ROOT / "fichero" / "fichero-ui-tests"]
_APPSOURCE = re.compile(r'appSource(?:Root)?\(\s*"([^"]+)"')


def stale_paths() -> list[tuple[str, str]]:
    bad: list[tuple[str, str]] = []
    for test_dir in TEST_DIRS:
        if not test_dir.exists():
            continue
        for tf in sorted(test_dir.rglob("*.swift")):
            for m in _APPSOURCE.finditer(tf.read_text(errors="ignore")):
                rel = m.group(1)
                if rel and not (SWIFT_ROOT / rel).exists():
                    bad.append((tf.relative_to(ROOT).as_posix(), rel))
    return bad


def main() -> int:
    bad = stale_paths()
    if not bad:
        print("appSource-path guardrail: all appSource(...) paths resolve.")
        return 0
    print(f"appSource-path guardrail FAILED — {len(bad)} test(s) read a source "
          "path that no longer exists (will throw file-not-found at runtime). "
          "Update the literal path to the file's new location:\n")
    for test, rel in bad:
        print(f"  {test}  ->  {rel}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
