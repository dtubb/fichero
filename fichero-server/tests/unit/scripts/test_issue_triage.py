"""scripts/issue_triage.py sorts open issues by what the specs say about them.

WHY: the backlog had 1,514 open issues, most with no spec behaviour, and an issue with no spec never
gets scheduled (maintainer, 2026-10-04). If these rules drift, tracked work gets closed as stale, or
done work stays open forever.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "issue_triage.py"
_SPEC = importlib.util.spec_from_file_location("issue_triage", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)

TODAY = dt.date(2026, 10, 4)


def _issue(number: int, created: str, *labels: str) -> dict:
    return {"number": number, "createdAt": created, "labels": [{"name": n} for n in labels]}


def test_spec_tags_decide_tracked_and_done(tmp_path):
    (tmp_path / "a.md").write_text(
        "- `x.one` — **[GAP]** (#10) not built\n"
        "- `x.two` — **[OK]** (#20) built\n"
        "- `x.three` — **[OK]** (#30) built\n- `x.four` — **[PARTIAL]** (#30) half\n"
        "prose that mentions #40 without a tag\n"
        "- `x.five` — **[GAP]** the behaviour\n  ISSUE: #60 on the continuation line\n\nlater prose #70\n")
    (tmp_path / "_TEMPLATE.md").write_text("- `t` — **[GAP]** (#50)\n")
    cited = _mod.spec_citations(tmp_path)
    assert _mod.bucket(_issue(10, "2026-01-01"), cited, TODAY, 14) == "TRACKED"
    assert _mod.bucket(_issue(20, "2026-01-01"), cited, TODAY, 14) == "DONE"
    assert _mod.bucket(_issue(30, "2026-01-01"), cited, TODAY, 14) == "TRACKED", "one unbuilt behaviour keeps it open"
    assert _mod.bucket(_issue(40, "2026-01-01"), cited, TODAY, 14) == "STALE", "an untagged mention is not tracking"
    assert 50 not in cited, "templates don't count"
    assert cited.get(60) == {"GAP"}, "an issue on a behaviour's continuation line is tracked"
    assert 70 not in cited, "prose after the behaviour ends is not"


def test_waiting_and_recent_are_kept():
    assert _mod.bucket(_issue(1, "2025-01-01", "needs-your-decision"), {}, TODAY, 14) == "WAITING"
    assert _mod.bucket(_issue(2, "2026-09-25"), {}, TODAY, 14) == "RECENT"
    assert _mod.bucket(_issue(3, "2026-09-01"), {}, TODAY, 14) == "STALE"
