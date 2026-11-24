"""dev-workflows.run.loop-needs-maintainer: an approve resumes the SAME batch at the rung it excused (manager 2026-11-02)."""
from __future__ import annotations

import json
import types

import pytest

from fichero_builder import check_tool, journal, work


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    monkeypatch.setattr(check_tool, "ACTIVITY", check_tool._no_activity)
    yield
    check_tool.REUSE[0] = None


def test_ladder_does_not_run_a_rung_that_is_reused_and_marks_it_cached():
    ran = []
    green = {"name": "ready", "ok": True, "seconds": 3}
    check_tool.REUSE[0] = {"ready": green}
    out = check_tool.ladder([("ready", lambda: ran.append("ready") or {"ok": True}), ("guards", lambda: ran.append("guards") or {"ok": True})])
    assert ran == ["guards"] and out["ok"] and out["rungs"][0]["cached"] is True and out["rungs"][1].get("cached") is None


def _prior(tmp_path, **kw):
    f = tmp_path / "ladder.json"
    f.write_text(json.dumps({"ok": False, "failed": "red-on-base", "head": "h1", "since": "b1", "pinned": "/p/1",
                             "rungs": [{"name": "pinned-checks", "ok": True}, {"name": "ready", "ok": True}, {"name": "diff-bound", "ok": True},
                                       {"name": "red-on-base", "ok": False}, {"name": "guards", "ok": True}], **kw}))
    return str(f)


def test_only_the_green_rungs_before_the_red_one_are_kept_and_only_for_the_same_head_base_and_pinned_copy(tmp_path):
    f = _prior(tmp_path)
    assert set(work.green_before_approve(f, "b1", "h1", "/p/1")) == {"pinned-checks", "ready", "diff-bound"}, "stops at the red rung: a green one after it is not trusted"
    for args in (("b2", "h1", "/p/1"), ("b1", "h2", "/p/1"), ("b1", "h1", "/p/2")):
        assert work.green_before_approve(f, *args) == {}, f"a moved base, a new head or a new pinned copy starts over: {args}"
    assert work.green_before_approve(str(tmp_path / "none.json"), "b1", "h1", "/p/1") == {}
    assert work.green_before_approve(_prior(tmp_path, ok=True), "b1", "h1", "/p/1") == {}, "a green ladder is never resumed"


def test_do_check_resumes_only_when_an_approval_is_given_and_records_head_base_and_pinned(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(work.land_tool, "resolve_branch", lambda repo, branch: "b1")
    monkeypatch.setattr(check_tool, "ladder_over", lambda *a, **k: seen.append(dict(check_tool.REUSE[0] or {})) or {"ok": True, "failed": "", "rungs": []})
    f = _prior(tmp_path)
    a = types.SimpleNamespace(name="l", pinned="/p/1", ids=[], approve_red=True)
    work.do_check(a, "/r", "integration", "h1", f)
    assert set(seen[0]) == {"pinned-checks", "ready", "diff-bound"}
    assert json.loads(open(f).read())["head"] == "h1" and json.loads(open(f).read())["pinned"] == "/p/1"
    f = _prior(tmp_path)
    work.do_check(types.SimpleNamespace(name="l", pinned="/p/1", ids=[]), "/r", "integration", "h1", f)
    assert seen[1] == {}, "no approval: the whole ladder runs"


def test_a_kept_rebase_runs_the_head_green_half_of_red_on_base_and_never_the_base_run(monkeypatch):
    """2026-11-24: HEAD_GREEN_ONLY turns the red-on-base rung into the green run of the changed tests; the base run is not made."""
    ran = []
    monkeypatch.setattr(check_tool, "stricter_files", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "pinned_violations", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "weakened_tests", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "acceptance_changed", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "_changes", lambda *a, **k: [("A", "", "pkg/a.py"), ("A", "", "pkg/tests/test_a.py")])
    monkeypatch.setattr(check_tool, "_git", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(check_tool, "_scratch_tree", lambda *a, **k: "tree")
    monkeypatch.setattr(check_tool, "drop_tree", lambda *a, **k: None)
    monkeypatch.setattr(check_tool, "green_runs", lambda tree, files, whole, cfg, t: ran.append(("green", files)) or {"ok": True})
    monkeypatch.setattr(check_tool, "red_on_base", lambda *a, **k: ran.append("base run") or {"ok": True})
    check_tool.REUSE[0] = {n: {"ok": True} for n in check_tool.RUNGS if n != "red-on-base"}
    check_tool.HEAD_GREEN_ONLY[0] = True
    try:
        out = check_tool._run_ladder("/r", "s", "h", "/p", ())
    finally:
        check_tool.HEAD_GREEN_ONLY[0] = False
    assert out["ok"] and ran == [("green", ["pkg/tests/test_a.py"])]
