"""dev-workflows.run.release-stages: stages resume from the first not green; red calls the manager once, then resumes."""
from __future__ import annotations

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


def test_engine_key_is_the_tree_id_of_fichero_server_at_the_sha(tmp_path):
    import subprocess
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    g("init", "-q")
    (tmp_path / "fichero-server").mkdir()
    (tmp_path / "fichero-server" / "uv.lock").write_text("a")
    g("add", "."), g("commit", "-qm", "1")
    one = g("rev-parse", "HEAD")
    (tmp_path / "README").write_text("unrelated")
    g("add", "."), g("commit", "-qm", "2")
    two = g("rev-parse", "HEAD")
    (tmp_path / "fichero-server" / "uv.lock").write_text("b")
    g("add", "."), g("commit", "-qm", "3")
    assert rr.engine_key(tmp_path, one) == rr.engine_key(tmp_path, two) != rr.engine_key(tmp_path, g("rev-parse", "HEAD"))


def test_a_resumed_run_whose_manager_already_ran_starts_no_second_manager():
    journal.append("release", run="r7", stage="verify", state="manager", detail="")
    asked, alerts = [], []
    st = stages([])
    st["verify"] = lambda: (1, "red")
    assert not rr.run("r7", st, lambda *a: asked.append(1) or True, alerts.append)
    assert not asked and len(alerts) == 1


def test_the_alert_is_a_journal_row_and_a_text_that_cannot_be_sent_does_not_crash_the_run():
    def boom(m):
        raise RuntimeError("no one to text")
    st = stages([])
    st["verify"] = lambda: (1, "red")
    assert not rr.run("r8", st, lambda *a: False, boom)
    states = [(r["stage"], r["state"]) for r in rr.rows("r8")]
    assert ("verify", "alert") in states and ("verify", "alert-failed") in states


def test_without_a_merge_branch_the_plan_has_no_merge_stage():
    assert "merge" not in [s for g in rr.plan_for(False) for c in g for s in c] and "merge" in [s for g in rr.plan_for(True) for c in g for s in c]


def test_the_real_stages_build_in_a_clean_clone_on_the_chosen_machine_never_the_loops_checkout(tmp_path, monkeypatch):
    import subprocess
    calls = []
    monkeypatch.setattr(rr, "_sh", lambda script, machine, t: calls.append((machine, script)) or (0, "10" if script.startswith("df") else "ok"))
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path / "root"), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    (tmp_path / "root").mkdir()
    g("init", "-q", "-b", "main"), g("commit", "-q", "--allow-empty", "-m", "1")
    g("remote", "add", "origin", str(tmp_path / "root")), g("update-ref", "refs/remotes/origin/main", "HEAD")
    st = rr.real_stages(tmp_path / "root", tmp_path / "s", "r9", branch="main", mac="down,imac", ios="air", check_runner="local", floor_gb=5, text=print)
    monkeypatch.setattr(rr, "pick_runner", lambda c, probe, f: c[-1])
    for name in ("sweep", "freeze"):
        rc, out = st[name]()
        assert rc == 0, out
        journal.append("release", run="r9", stage=name, state="green", detail=out)
    calls.clear()
    assert st["mac-dmg"]() == (0, "ok") and st["ios"]() == (0, "ok")
    (m1, s1), (m2, s2) = calls
    assert (m1, m2) == ("imac", "air") and str(tmp_path / "root") not in s1 + s2 and "nightly" in s1 and "release-all.sh" in s1


def test_sweep_removes_only_this_runs_clone_dir_never_the_nightly_builds_trees(tmp_path, monkeypatch):
    nightly = tmp_path / "s" / "nightly"
    for part in ("release", "check", "dmg"):
        (nightly / part).mkdir(parents=True)
    monkeypatch.setattr(rr, "pick_runner", lambda c, probe, f: c[0])
    monkeypatch.setattr(rr.subprocess, "run", lambda *a, **k: None)
    st = rr.real_stages(tmp_path, tmp_path / "s", "r10", branch="main", mac="local", ios="local", check_runner="local", floor_gb=1, text=print)
    assert st["sweep"]()[0] == 0 and not (nightly / "release").exists() and (nightly / "check").exists() and (nightly / "dmg").exists()
