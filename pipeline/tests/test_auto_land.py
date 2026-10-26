"""pipeline.auto-land-to-integration: the scheduler lands a reviewed READY item on the next pass, integration only."""
from __future__ import annotations

import pytest

from pipeline import core, journal, runner
from pipeline.tests.test_runner import origin_head, reviewed_item


def test_a_reviewed_item_lands_on_the_next_pass_when_switched_on(scratch, issues, fake_coder, monkeypatch):
    it = reviewed_item(scratch, fake_coder, monkeypatch)
    before = origin_head(scratch)
    runner.run(once=True)
    assert origin_head(scratch) == before and core.state()["items"]["1001"]["state"] == "reviewed", "off by default"
    scratch["cfg"].setdefault("run", {})["auto_land"] = True
    runner.run(once=True)
    assert origin_head(scratch) == it["sha"] and core.state()["items"]["1001"]["state"] == "pushed"
    assert any(e["event"] == "land" and e["apply"] for e in journal.read())


def test_a_needs_maintainer_item_never_auto_lands(scratch, issues, fake_coder, monkeypatch):
    reviewed_item(scratch, fake_coder, monkeypatch)
    scratch["cfg"].setdefault("run", {})["auto_land"] = True
    before = origin_head(scratch)
    core._move("1001", "needs-maintainer", "changes its own checks")
    runner.run(once=True)
    assert origin_head(scratch) == before


def test_an_item_with_an_open_question_never_auto_lands(scratch, issues, fake_coder, monkeypatch):
    reviewed_item(scratch, fake_coder, monkeypatch)
    scratch["cfg"].setdefault("run", {})["auto_land"] = True
    journal.append("queue", kind="question", text="q", key="1001", issue=1001)
    before = origin_head(scratch)
    runner.auto_land(scratch["cfg"], [])
    assert origin_head(scratch) == before


def test_a_main_base_is_refused_not_pushed(scratch, issues, fake_coder, monkeypatch):
    reviewed_item(scratch, fake_coder, monkeypatch)
    scratch["cfg"].setdefault("run", {})["auto_land"] = True
    scratch["cfg"]["repo"]["base"] = "origin/main"
    did = []
    runner.auto_land(scratch["cfg"], did)
    assert "refused" in did[0] and "integration branch" in did[0]
    with pytest.raises(RuntimeError):
        runner._land("1001", apply=True)
