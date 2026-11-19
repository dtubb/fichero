"""dev-workflows.run.release-stages: stages resume from the first not green; red calls the manager once, then resumes."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_builder import journal, release_run as rr


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")


def stages(calls, red=None):
    def mk(n):
        def f():
            calls.append(n)
            return (1, f"{n} broke") if n == red and calls.count(n) == 1 else (0, "ok")
        return f
    return {n: mk(n) for n in rr.STAGES}


def test_all_green_runs_every_stage_once_and_never_calls_the_manager():
    calls, asked = [], []
    assert rr.run("r1", stages(calls), lambda *a: asked.append(a) or True, lambda m: asked.append(m))
    assert sorted(calls) == sorted(rr.STAGES) and not asked


def test_a_second_run_of_the_same_id_rebuilds_nothing_that_is_green():
    calls = []
    rr.run("r1", stages(calls), lambda *a: True, print)
    calls.clear()
    assert rr.run("r1", stages(calls), lambda *a: True, print) and calls == []


def test_resume_starts_at_the_first_stage_not_green():
    calls = []
    for s in rr.STAGES[:rr.STAGES.index("verify")]:
        journal.append("release", run="r2", stage=s, state="green", detail="")
    rr.run("r2", stages(calls), lambda *a: True, print)
    assert "sweep" not in calls and "freeze" not in calls and calls[0] == "verify"


def test_red_calls_the_manager_with_stage_log_and_list_then_resumes_at_that_stage():
    calls, seen = [], []
    ok = rr.run("r3", stages(calls, red="verify"), lambda s, log, lst: seen.append((s, log, lst)) or True, seen.append)
    assert ok and len(seen) == 1 and seen[0][0] == "verify" and "verify broke" in seen[0][1] and seen[0][2] == rr.STAGES
    assert calls.count("verify") == 2 and calls.count("sweep") == 1 and calls.count("freeze") == 1  # nothing before it reran


def test_a_manager_that_cannot_fix_it_texts_what_is_red_and_stops():
    calls, alerts = [], []
    assert not rr.run("r4", stages(calls, red="verify"), lambda *a: False, alerts.append)
    assert len(alerts) == 1 and "verify" in alerts[0] and "ios" not in calls and "publish" not in calls


def test_the_manager_is_asked_once_per_run():
    alerts, asked = [], []
    st = stages([])
    st["verify"] = lambda: (1, "always red")
    assert not rr.run("r5", st, lambda *a: asked.append(1) or True, alerts.append)
    assert len(asked) == 1 and len(alerts) == 1


def test_the_two_chains_both_run_when_one_is_red_and_only_the_red_one_reruns():
    calls = []
    rr.run("r6", stages(calls, red="ios"), lambda *a: True, print)
    assert calls.count("ios") == 2 and calls.count("mac-dmg") == 1 and calls.count("notarize") == 1


def test_pick_runner_takes_the_first_awake_one_over_the_floor():
    free = {"a": None, "b": 10, "c": 80}
    assert rr.pick_runner(["a", "b", "c"], free.get, 50) == "c"
    with pytest.raises(RuntimeError, match="a: unreachable; b: 10 GB"):
        rr.pick_runner(["a", "b"], free.get, 50)


def test_sweep_never_removes_the_live_venv_or_what_holds_it(tmp_path):
    venv = tmp_path / "real-venv"
    venv.mkdir()
    (venv / "x").write_text("1")
    link = tmp_path / "integration" / ".venv"
    link.parent.mkdir()
    link.symlink_to(venv)
    junk = tmp_path / "junk"
    junk.mkdir()
    out = rr.sweep([junk, link, venv, link.parent, tmp_path / "missing"], [link])
    assert out == [f"removed {junk}"] and venv.exists() and link.exists()


def test_engine_key_changes_with_the_lock_and_the_sources_only(tmp_path):
    (tmp_path / "fichero-server").mkdir()
    (tmp_path / "fichero-server" / "uv.lock").write_text("a")
    (tmp_path / "fichero-server" / "m.py").write_text("x")
    k = rr.engine_key(tmp_path)
    (tmp_path / "README").write_text("unrelated")
    assert rr.engine_key(tmp_path) == k
    (tmp_path / "fichero-server" / "uv.lock").write_text("b")
    assert rr.engine_key(tmp_path) != k
