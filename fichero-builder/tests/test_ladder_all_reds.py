import threading

import pytest

from fichero_builder import check_tool, work


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(check_tool, "ACTIVITY", check_tool._no_activity)
    check_tool.REUSE[0] = None
    yield
    check_tool.REUSE[0] = None


def _rungs(ran, reds):
    return [(n, (lambda n=n: ran.append(n) or {"ok": n not in reds, "stderr_tail": f"{n} red" if n in reds else ""}))
            for n in check_tool.RUNGS]


def test_a_red_cheap_rung_does_not_stop_the_other_cheap_rungs_and_every_red_is_reported():
    ran = []
    out = check_tool.ladder(_rungs(ran, {"ready", "guards", "contract-current", "since-guards"}))
    assert not out["ok"] and out["failed"] == "ready"
    assert out["also_failed"] == ["guards", "contract-current", "since-guards"]
    assert ran == ["ready", "guards", "contract-current", "since-guards"], "after a red only the cheap independent rungs go on"


def test_a_red_cheap_rung_before_a_green_ladder_end_still_skips_the_heavy_rungs():
    ran = []
    out = check_tool.ladder(_rungs(ran, {"guards"}))
    assert out["failed"] == "guards" and out["also_failed"] == []
    assert "build" not in ran and "perf" not in ran and "security" not in ran


def test_a_red_heavy_rung_stops_at_once_and_keeps_the_cheap_reds_found_before_it():
    ran = []
    out = check_tool.ladder(_rungs(ran, {"ready", "red-on-base"}))
    assert out["failed"] == "ready" and out["also_failed"] == []
    assert "red-on-base" not in ran, "a rung that is not cheap and independent never runs after a red"
    ran.clear()
    out = check_tool.ladder(_rungs(ran, {"red-on-base", "guards"}))
    assert out["failed"] == "red-on-base" and ran[-1] == "red-on-base"


def test_a_green_ladder_has_no_also_failed():
    out = check_tool.ladder(_rungs([], set()))
    assert out["ok"] and out["also_failed"] == []


def test_the_fix_brief_carries_every_red_rungs_words():
    r = {"failed": "ready", "rungs": [{"name": "ready", "ok": False, "stderr_tail": "lint broke"}, {"name": "diff-bound", "ok": True},
                                      {"name": "guards", "ok": False, "stderr_tail": "guard X red"}]}
    t = work._tail(r)
    assert "lint broke" in t and "guard X red" in t and "ready" in t and "guards" in t
    mid = {"failed": "ready", "rungs": [{"name": "ready", "ok": False, "stderr_tail": "lint broke"}, {"name": "guards", "ok": True}, {"name": "since-guards", "ok": True}]}
    assert "lint broke" in work._tail(mid), "one red rung followed by green cheap rungs: its words, not the last row's"
    one = {"failed": "ready", "rungs": [{"name": "ready", "ok": False, "stderr_tail": "only"}]}
    assert work._tail(one) == "only"


def test_red_on_base_runs_the_base_and_head_runs_at_once(monkeypatch, tmp_path):
    from fichero_builder.check_tool import Config
    head_started, base_started = threading.Event(), threading.Event()

    def base(root, files, cfg, t):
        base_started.set()
        assert head_started.wait(10), "the head run never started while the base run was going: they ran in a row"
        return {"ok": False}

    def head(tree, files, whole, cfg, t):
        head_started.set()
        assert base_started.wait(10), "the base run never started while the head run was going: they ran in a row"
        return {"ok": True, "stdout_tail": "", "name": "pytest"}

    monkeypatch.setattr(check_tool, "pytest_rung", base)
    monkeypatch.setattr(check_tool, "green_runs", head)
    monkeypatch.setattr(check_tool, "_git", lambda *a, **k: {"ok": True, "stdout_tail": "abc\n", "stderr_tail": ""})
    monkeypatch.setattr(check_tool, "_lines", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "already_built_files", lambda *a, **k: set())
    monkeypatch.setattr(check_tool, "data_only", lambda *a, **k: False)
    monkeypatch.setattr(check_tool, "_mkdtemp", lambda *a, **k: str(tmp_path / "base"))
    r = check_tool.red_on_base(tmp_path, "s" * 40, "h" * 40, ["t_test.py"], Config())
    assert r["ok"] and r["name"] == "red-on-base"
