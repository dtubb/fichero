#!/usr/bin/env python3
"""Release-docs readiness guardrail (release lane step 3, #4534-class).

A release cannot ship with stale or missing docs — the docs are part of the
release, not an afterthought (see
docs/contributor_manual/specs/harness/release-and-versioning.md, "The release
lane"). This runs in `release-all.sh`'s preflight and FAILS the lane unless,
for the version about to be stamped/shipped:

    1. `RELEASE_NOTES.md` has that version's `## <version>` section (dotted
       per-release form, e.g. `## 2026.09.08`) with non-empty prose under it.
    2. `CHANGELOG.md` has that day's entry: a `## <YYYY-MM-DD>` dashed
       heading for the same calendar date, with content under it.
    3. The docs-freshness guardrails pass:
       `check_capability_reference_current.py` and
       `check_features_freshness.py`.

The doc-presence checks (1) and (2) are pure text logic (`docs_ready`) so they
are unit-testable without running the real freshness scripts or touching the
network — see fichero-server/tests/unit/scripts/test_check_release_docs_ready.py.

Exit codes:
    0  ready — release notes, changelog, and docs freshness all check out
    1  not ready — see printed problems

Usage:
    scripts/check_release_docs_ready.py
    scripts/check_release_docs_ready.py --version 2026.09.08
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_XCCONFIG = ROOT / "fichero" / "Configs" / "Version.xcconfig"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"
CHANGELOG = ROOT / "CHANGELOG.md"


def _read_version() -> str:
    text = VERSION_XCCONFIG.read_text()
    match = re.search(r"^MARKETING_VERSION\s*=\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        raise SystemExit(f"error: no MARKETING_VERSION in {VERSION_XCCONFIG}")
    return match.group(1)


def _version_to_changelog_date(version: str) -> str:
    # 2026.09.08[.N][-suffix] -> 2026-09-08. Only the YYYY.MM.DD prefix
    # matters; a build number or prerelease suffix doesn't change the day.
    match = re.match(r"^(\d{4})\.(\d{2})\.(\d{2})", version)
    if not match:
        raise SystemExit(f"error: version {version!r} is not YYYY.MM.DD-shaped")
    return "-".join(match.groups())


def _section_body(text: str, heading: str) -> str | None:
    """Return the body under a `## <heading>` line, or None if absent.

    The body is everything up to the next `## `-level heading (or end of
    file), so a heading with only blank lines under it reports an empty body
    rather than crashing.
    """
    pattern = re.compile(
        rf"^##[ \t]+{re.escape(heading)}[ \t]*$\n(.*?)(?=^##[ \t]|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1)


def docs_ready(version: str, notes_text: str, changelog_text: str) -> list[str]:
    """Return a list of problems; empty means the docs are ready for `version`."""
    problems: list[str] = []

    notes_body = _section_body(notes_text, version)
    if notes_body is None:
        problems.append(f"RELEASE_NOTES.md has no '## {version}' section")
    elif not notes_body.strip():
        problems.append(f"RELEASE_NOTES.md's '## {version}' section is empty")

    changelog_date = _version_to_changelog_date(version)
    changelog_body = _section_body(changelog_text, changelog_date)
    if changelog_body is None:
        problems.append(f"CHANGELOG.md has no '## {changelog_date}' section")
    elif not changelog_body.strip():
        problems.append(f"CHANGELOG.md's '## {changelog_date}' section is empty")

    return problems


def _run_guardrail(script_name: str) -> bool:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script_name)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": "fichero-server/src"},
    )
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        help="Version to check (YYYY.MM.DD[.N][-suffix]); defaults to "
        "MARKETING_VERSION in fichero/Configs/Version.xcconfig.",
    )
    args = parser.parse_args(argv)

    version = args.version or _read_version()
    print(f"Release-docs readiness check for {version}:")

    problems = docs_ready(
        version,
        RELEASE_NOTES.read_text(),
        CHANGELOG.read_text(),
    )
    for problem in problems:
        print(f"  FAIL: {problem}")
    if not problems:
        print("  OK: RELEASE_NOTES.md and CHANGELOG.md both carry this release")

    freshness_ok = True
    for script_name in (
        "check_capability_reference_current.py",
        "check_features_freshness.py",
    ):
        print(f"  running {script_name} ...")
        if _run_guardrail(script_name):
            print(f"  OK: {script_name}")
        else:
            print(f"  FAIL: {script_name}")
            freshness_ok = False

    if problems or not freshness_ok:
        print("verdict: NOT READY — fix the above before releasing")
        return 1

    print("verdict: READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
