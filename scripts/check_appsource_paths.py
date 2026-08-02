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

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = ROOT / "fichero" / "fichero"           # appSource() resolves here
TEST_DIRS = [ROOT / "fichero" / "fichero-tests", ROOT / "fichero" / "fichero-ui-tests"]
_APPSOURCE = re.compile(r'appSource(?:Root)?\(\s*"([^"]+)"')


def _count_sites() -> int:
    """Total appSource(...) call sites across the test trees (#4487 floor)."""
    count = 0
    for test_dir in TEST_DIRS:
        if not test_dir.exists():
            continue
        for tf in sorted(test_dir.rglob("*.swift")):
            count += len(_APPSOURCE.findall(tf.read_text(errors="ignore")))
    return count


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
    # #4487 scan floor: zero appSource(...) call sites means the helper
    # convention moved or the test tree is gone — not "all resolve".
    # 71 sites on 2026-08-02 (appSource helper duplicated across tests).
    require_scan_floor(_count_sites(), 35, "appSource call sites (71 on 2026-08-02)")
    if not bad:
        print("appSource-path guardrail: all appSource(...) paths resolve.")
        return 0
    print(f"appSource-path guardrail FAILED — {len(bad)} test(s) read a source "
          "path that no longer exists (will throw file-not-found at runtime). "
          "Update the literal path to the file's new location:\n")
    for test, rel in bad:
        print(f"  {test}  ->  {rel}")
    return 1


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
    _require_scan_roots_4382(SWIFT_ROOT)
    raise SystemExit(main())
