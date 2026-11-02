#!/usr/bin/env python3
"""Lint ratchet for the ready check: per touched file, count the linter's violations by rule on base and on head; refuse
only a rule whose count grows, or any violation in a file that is new. A file that already broke a rule on base (a 997-line
store cut to 919, still over file_length) passes as long as it gets no worse (manager 2026-11-02).

Usage: fichero-builder/fichero_builder/lint.py --tool swiftlint|ruff --base <rev> FILE...   (run from the repo root; exit 1 = refused)
The base version goes to the linter on stdin under the file's own path, so the repo's config applies to both. Stdlib only, and Python 3.9 (the jail's `python3` is the Command Line Tools one). Harness code, not a guard: it lives in the Builder (manager 2026-11-02), so adding it was no new file under a pinned path."""
import os
import sys

# before any other import: python < 3.11 keeps the script's own folder first on sys.path even under -I, and that folder is the
# worker's to edit, so a planted json.py or subprocess.py there would run inside this judge (review 2026-11-02)
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.dirname(os.path.abspath(__file__))]

import argparse  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
from collections import Counter  # noqa: E402
from typing import Optional  # noqa: E402


class LintError(RuntimeError):
    """The linter itself failed (a config error, a crash): never read as zero findings (review 2026-11-02)."""


def _rows(argv: list, text: Optional[str], tool: str) -> list:
    r = subprocess.run(argv, input=text, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise LintError(f"{tool} gave no JSON (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-200:]}") from None


def _lint(tool: str, path: str, text: Optional[str]) -> list:
    """[(rule, message)] for `path` (its working copy, or `text` when given)."""
    if tool == "ruff":
        argv = ["ruff", "check", "--output-format", "json", "--exit-zero"] + (["--stdin-filename", path, "-"] if text is not None else [path])
        rows = _rows(argv, text, tool)
        return [(r["code"] or "syntax", f"{path}:{r['location']['row']}: {r['code']} {r['message']}") for r in rows]
    argv = ["swiftlint", "lint", "--quiet", "--reporter", "json"] + (["--use-stdin"] if text is not None else [path])  # the config from the cwd (the repo root)
    rows = _rows(argv, text, tool)
    return [(r["rule_id"], f"{path}:{r.get('line')}: {r['rule_id']} {r['reason']}") for r in rows]


def check(tool: str, base: str, files: list) -> list:
    """The refusals: one line per finding of a rule that grew (or of a new file)."""
    bad = []
    for f in files:
        old = subprocess.run(["git", "show", f"{base}:{f}"], capture_output=True, text=True)
        head = _lint(tool, f, None)
        if old.returncode:  # new on this branch: clean or refused
            bad += [m for _r, m in head]
            continue
        was, now = Counter(r for r, _m in _lint(tool, f, old.stdout)), Counter(r for r, _m in head)
        grew = {r for r in now if now[r] > was[r]}
        bad += [f"{m} ({now[r]} on head, {was[r]} on base)" for r, m in head if r in grew]
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", choices=["swiftlint", "ruff"], required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    try:
        bad = check(a.tool, a.base, a.files)
    except LintError as e:
        print(f"REFUSED: {e}")
        return 1
    for line in bad[:40]:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
