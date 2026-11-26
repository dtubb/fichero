"""The repo's [check.guard_inputs] (speed 5) names real guards and real paths: a stale prefix makes rev-parse fail, so that
guard silently never caches; a renamed guard keeps a dead entry (2026-11-08, #6116)."""
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_declared_guard_exists_and_every_input_is_in_the_tree():
    inputs = tomllib.loads((ROOT / "harness.toml").read_text())["check"]["guard_inputs"]
    assert len(inputs) > 50
    for stem, prefixes in inputs.items():
        assert (ROOT / "scripts" / f"{stem}.py").is_file(), stem
        assert "scripts" in prefixes, stem  # the guard itself, its helpers and baselines
        for p in prefixes:
            if not (ROOT / ".git").exists():  # a gate copy (the M4 run dir) has no repo: the tree itself is the check
                assert (ROOT / p).exists(), f"{stem}: {p} is not in the tree"
                continue
            r = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"HEAD:{p}"], capture_output=True)
            assert r.returncode == 0, f"{stem}: {p} is not in HEAD"


def test_a_since_guard_takes_one_prefix_or_a_list_of_them(tmp_path):
    from fichero_builder import check_tool

    cfg = check_tool.Config(since_guards={"scripts/check_a.py": "fichero/", "scripts/check_b.py": ["fichero/", "fichero-server/"]})
    ran = []
    original = check_tool._run
    check_tool._run = lambda name, *a, **k: ran.append(name) or {"ok": True}
    try:
        check_tool.since_guards(tmp_path, "base", ["fichero-server/x.py"], cfg)
        assert ran == ["check_b"]
        ran.clear()
        check_tool.since_guards(tmp_path, "base", ["fichero/y.swift"], cfg)
        assert ran == ["check_a", "check_b"]
    finally:
        check_tool._run = original


def test_with_guards_by_diff_a_guard_whose_inputs_the_batch_does_not_touch_is_skipped_and_the_remote_batch_holds_no_lock(tmp_path, monkeypatch):
    """2026-11-26 (owner: per step only what changed; the nightly runs everything): the guards rung was 37% of every check's time, and
    the one guards lock was held across the remote batch, so three runners judged guards one lane at a time (2 h of waits a day)."""
    from fichero_builder import check_tool, journal

    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    (tmp_path / "scripts").mkdir()
    for g in ("check_engine", "check_app", "check_whole"):
        (tmp_path / "scripts" / f"{g}.py").write_text("print('ok')\n")
    inputs = {"check_engine": ["fichero-server/src"], "check_app": ["fichero"]}
    ran, free = [], []
    monkeypatch.setattr(check_tool, "_run", lambda name, *a, **k: ran.append(name) or {"ok": True, "exit_code": 0, "stdout_tail": "", "stderr_tail": ""})

    def batch(away, root, cfg):
        try:
            with journal.Lock("guards", wait=False):
                free.append(True)
        except BlockingIOError:
            free.append(False)
        return {}
    monkeypatch.setattr(check_tool, "_remote_guard_batch", batch)
    monkeypatch.setattr(check_tool, "_guard_away", lambda s, cfg: True)
    cfg = check_tool.Config(guard_glob="scripts/check_*.py", guard_inputs=inputs, guards_by_diff=True)
    r = check_tool.guards(tmp_path, cfg, ["fichero-server/src/x.py"])
    assert r["ok"] and ran == ["check_engine", "check_whole"], "check_app's input `fichero` is not `fichero-server`: skipped"
    assert [x for x in r["results"] if x.get("skipped")] == [{"name": "check_app", "argv": [str(tmp_path / "scripts" / "check_app.py")], "ok": True,
                                                              "seconds": 0, "exit_code": 0, "skipped": "inputs untouched", "stdout_tail": "", "stderr_tail": ""}]
    assert free == [True], "the remote batch runs outside the guards lock"
    ran.clear()
    check_tool.guards(tmp_path, cfg, ["scripts/check_app.py"])
    assert ran == ["check_app", "check_whole"], "a guard whose own script changed runs"
    ran.clear()
    check_tool.guards(tmp_path, cfg)  # verify and the nightly: no batch, every guard
    assert ran == ["check_app", "check_engine", "check_whole"]
    ran.clear()
    check_tool.guards(tmp_path, check_tool.Config(guard_glob="scripts/check_*.py", guard_inputs=inputs), ["fichero-server/src/x.py"])
    assert ran == ["check_app", "check_engine", "check_whole"], "guards_by_diff off (the default): every guard, as before"
