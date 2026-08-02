#!/usr/bin/env python3
"""Turn pytest failures into tracked GitHub issues, one per failing test.

A failed test is work for a worker, not a log line that vanishes when the
worker crashes. Run the suite with a junit report, then feed it here:

    pytest tests/unit tests/contracts --junitxml=/tmp/j.xml -p no:cacheprovider
    python scripts/tests_to_issues.py /tmp/j.xml            # file/refresh issues
    python scripts/tests_to_issues.py /tmp/j.xml --dry-run  # print, file nothing

Idempotent: the issue title is keyed off the test nodeid, so re-running an
already-red suite updates nothing new (skips the open one). When a test goes
green again its issue is NOT auto-closed here — the fixing worker closes it in
its commit ("Closes #N"), which keeps attribution honest.

ponytail: stdlib xml + `gh` subprocess. No API client, no auth handling — `gh`
already owns the token. Lane label is inferred from the test path; refine the
LANE_RULES table if lanes move.
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET

TITLE_PREFIX = "test failure:"

# (substring in nodeid) -> lane label. First match wins; default backend.
LANE_RULES = [
    ("authz", "features"),
    ("membership", "features"),
    ("sharing", "features"),
    (".swift", "client:swiftui"),
]


def lane_label(nodeid: str) -> str:
    for needle, label in LANE_RULES:
        if needle in nodeid:
            return label
    return "backend"


def failures(junit_path: str) -> list[tuple[str, str]]:
    """Return [(nodeid, short_message)] for each failing/erroring testcase."""
    root = ET.parse(junit_path).getroot()
    out: list[tuple[str, str]] = []
    for tc in root.iter("testcase"):
        bad = tc.find("failure")
        if bad is None:
            bad = tc.find("error")
        if bad is None:
            continue
        cls = tc.get("classname", "").replace(".", "/")
        name = tc.get("name", "")
        # junit classname is dotted module path; nodeid uses file::test
        nodeid = f"{cls}.py::{name}" if cls else name
        msg = (bad.get("message") or bad.text or "").strip()
        out.append((nodeid, msg[:500]))
    return out


def open_issue_titles() -> set[str]:
    r = subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--limit", "500",
         "--search", TITLE_PREFIX, "--json", "title", "--jq", ".[].title"],
        capture_output=True, text=True,
    )
    return {line.strip() for line in r.stdout.splitlines() if line.strip()}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        print("usage: tests_to_issues.py <junit.xml> [--dry-run]", file=sys.stderr)
        return 2
    fails = failures(args[0])
    if not fails:
        print("no test failures in report — nothing to file")
        return 0

    existing = set() if dry else open_issue_titles()
    filed = skipped = 0
    for nodeid, msg in fails:
        title = f"{TITLE_PREFIX} {nodeid}"
        if title in existing:
            skipped += 1
            continue
        body = (
            f"Automated from a manager gate run.\n\n"
            f"**Test:** `{nodeid}`\n\n"
            f"**Reproduce:**\n```\npytest {nodeid} -p no:cacheprovider\n```\n\n"
            f"**Failure:**\n```\n{msg or '(no message)'}\n```\n\n"
            f"Fix on your lane branch and close with `Closes #<n>` in the commit."
        )
        if dry:
            print(f"WOULD FILE: {title}  [{lane_label(nodeid)}]")
            filed += 1
            continue
        subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body,
             "--label", "type:bug", "--label", lane_label(nodeid)],
            check=False,
        )
        existing.add(title)
        filed += 1
    print(f"{'would file' if dry else 'filed'}: {filed}, skipped (already open): {skipped}")
    return 0


def _selfcheck() -> None:
    import tempfile
    import os
    xml = (
        '<testsuite>'
        '<testcase classname="tests.unit.test_db" name="test_ok"/>'
        '<testcase classname="tests.unit.test_authz" name="test_bad">'
        '<failure message="assert 1 == 2">trace</failure></testcase>'
        '<testcase classname="tests.unit.test_x" name="test_err">'
        '<error message="boom"/></testcase>'
        '</testsuite>'
    )
    fd, p = tempfile.mkstemp(suffix=".xml")
    os.write(fd, xml.encode()); os.close(fd)
    f = failures(p)
    os.unlink(p)
    assert [n for n, _ in f] == [
        "tests/unit/test_authz.py::test_bad",
        "tests/unit/test_x.py::test_err",
    ], f
    assert lane_label("tests/unit/test_authz.py::test_bad") == "features"
    assert lane_label("tests/unit/test_db.py::test_x") == "backend"
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        raise SystemExit(main())
