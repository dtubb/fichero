"""scripts/maintainer_queue.py sorts issues into what waits on the maintainer.

WHY: "what's the update / what should I test / what's blocked on me" must have one deterministic
answer from GitHub, not from an agent's memory (maintainer, 2026-10-04). If the sorting drifts, a
blocked decision or a build waiting for his eyes silently drops off his list.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "maintainer_queue.py"
_SPEC = importlib.util.spec_from_file_location("maintainer_queue", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)


def _issue(number: int, title: str, *labels: str) -> dict:
    return {"number": number, "title": title, "labels": [{"name": n} for n in labels], "milestone": None}


def test_each_issue_lands_in_the_right_section():
    decide = _issue(1, "a ruling", "needs-your-decision")
    blocked = _issue(2, "[rights] BLOCKED on the maintainer: consent")
    test = _issue(3, "vertical page", "needs-your-test", "residue")
    owed = _issue(4, "half done", "residue")
    plain = _issue(5, "ordinary work")
    closed = _issue(6, "fixed")

    got = _mod.sections([decide, blocked, test, owed, plain], [closed])

    assert got["DECIDE"] == [decide, blocked]
    assert got["TEST"] == [test]
    assert got["OWED"] == [owed], "an issue waiting for his test is listed once, under TEST"
    assert got["CLOSED"] == [closed]
    assert all(plain not in issues for issues in got.values())
