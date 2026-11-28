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


def test_unit_reads_actions_only_after_every_earlier_rung_is_green_security_included():
    """`unit` pushes the head to GitHub: a red ready or security must stop the ladder before it."""
    assert "unit" not in check_tool.CHEAP_RUNGS
    assert check_tool.RUNGS.index("unit") > check_tool.RUNGS.index("security")
    for red in ("ready", "security"):
        ran = []
        check_tool.ladder(_rungs(ran, {red}))
        assert "unit" not in ran, red


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


def test_every_test_that_passes_on_base_is_named_in_one_refusal(monkeypatch, tmp_path):
    """2026-11-25, app-bugs nightly-green-1 at 1b42f9abc: three tests passed on base, the rung stopped at the first, so each approve
    (alerts 1888, 1891) named one file and the next ladder asked about the next. One refusal names them all; an approve of one leaves
    the others asked."""
    from fichero_builder import journal
    from fichero_builder.check_tool import Config
    files = ["fichero-server/tests/unit/execution/test_a_failed_jobs_reason_is_its_kinds_words_6597.py",
             "fichero-server/tests/unit/execution/test_a_large_runs_tree_reads_fast_6732.py",
             "fichero-server/tests/unit/execution/test_activity_engine_pins.py"]
    monkeypatch.setattr(journal, "append", lambda *a, **k: None)
    monkeypatch.setattr(check_tool, "pytest_rung", lambda *a, **k: {"ok": True, "remote": "imac", "stdout_tail": "5 passed, 77 warnings in 0.70s"})
    monkeypatch.setattr(check_tool, "green_runs", lambda *a, **k: {"ok": True, "stdout_tail": "", "name": "pytest"})
    monkeypatch.setattr(check_tool, "_git", lambda *a, **k: {"ok": True, "stdout_tail": "abc\n", "stderr_tail": ""})
    monkeypatch.setattr(check_tool, "_lines", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "already_built_files", lambda *a, **k: set())
    monkeypatch.setattr(check_tool, "data_only", lambda *a, **k: False)
    monkeypatch.setattr(check_tool, "_mkdtemp", lambda *a, **k: str(tmp_path / "base"))
    r = check_tool.red_on_base(tmp_path, "a40008b70" + "0" * 31, "h" * 40, files, Config())
    assert not r["ok"] and all(f"NOT RED ON BASE: {f} passes at a40008b70" in r["stderr_tail"] for f in files)
    assert r["stderr_tail"].endswith("\nneeds-approval") and r["stderr_tail"].count("needs-approval") == 1
    r = check_tool.red_on_base(tmp_path, "a40008b70" + "0" * 31, "h" * 40, files, Config(), approve_red=(files[0],))
    assert files[0] not in r["stderr_tail"] and all(f in r["stderr_tail"] for f in files[1:])


def test_the_head_run_in_its_helper_thread_sees_the_ladders_cancel_marker(monkeypatch, tmp_path):
    from fichero_builder import journal
    from fichero_builder.check_tool import Config
    monkeypatch.setattr(journal, "STATE", tmp_path)
    check_tool.cancel_file("hhhhhhhhh").write_text("newer")
    seen = []
    monkeypatch.setattr(check_tool, "pytest_rung", lambda *a, **k: {"ok": False})
    monkeypatch.setattr(check_tool, "green_runs", lambda *a, **k: seen.append(check_tool.cancel_requested()) or {"ok": True, "stdout_tail": ""})
    monkeypatch.setattr(check_tool, "_git", lambda *a, **k: {"ok": True, "stdout_tail": "abc\n", "stderr_tail": ""})
    monkeypatch.setattr(check_tool, "_lines", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "already_built_files", lambda *a, **k: set())
    monkeypatch.setattr(check_tool, "data_only", lambda *a, **k: False)
    monkeypatch.setattr(check_tool, "_mkdtemp", lambda *a, **k: str(tmp_path / "base"))
    check_tool._KEY[0] = "check s..hhhhhhhhh"
    try:
        check_tool.red_on_base(tmp_path, "s" * 40, "h" * 40, ["t_test.py"], Config())
    finally:
        check_tool._KEY[0] = ""
    assert seen == [True], "the head run's thread had no ladder key, so a superseded check was never cancelled there"


def test_the_head_run_and_the_base_runs_start_on_different_runners_at_the_same_time(monkeypatch, tmp_path):
    from fichero_builder.check_tool import Config
    cfg = Config(remotes=("imac:~/g", "air:~/g"))
    started: dict = {}
    both = threading.Barrier(2, timeout=10)

    def fake_remote(name, argv, root, timeout_s, cfg, extra, cwd, remote=""):
        started[name + ("-head" if str(root).endswith("/headtree") else "-base")] = remote
        both.wait()  # a run that waited for the other one (the same runner's lock) would time out here
        return {"name": name, "ok": str(root).endswith("/headtree"), "exit_code": 0, "stdout_tail": "", "stderr_tail": "", "argv": [], "seconds": 0, "remote": remote}

    head_tree, base_tree = tmp_path / "headtree", tmp_path / "basetree"
    head_tree.mkdir()
    monkeypatch.setattr(check_tool, "_remote_run", fake_remote)
    monkeypatch.setattr(check_tool, "_git", lambda *a, **k: {"ok": True, "stdout_tail": "abc\n", "stderr_tail": ""})
    monkeypatch.setattr(check_tool, "_lines", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "already_built_files", lambda *a, **k: set())
    monkeypatch.setattr(check_tool, "data_only", lambda *a, **k: False)
    monkeypatch.setattr(check_tool, "_mkdtemp", lambda *a, **k: str(base_tree))
    monkeypatch.setattr(check_tool, "_DEAD", {})
    r = check_tool.red_on_base(tmp_path, "s" * 40, "h" * 40, ["t_test.py"], cfg, head_tree=head_tree)
    assert r["ok"]
    assert set(started.values()) == {"imac:~/g", "air:~/g"} and started["pytest-head"] != started["pytest-base"]


def test_with_one_runner_the_base_runs_wait_on_the_same_one(monkeypatch):
    from fichero_builder.check_tool import Config
    cfg = Config(remotes=("imac:~/g",))
    assert check_tool._runners_for_base(cfg) == ("imac:~/g",)
    assert check_tool._runners_for_base(Config(remotes=("a", "b", "c"))) == ("b", "c", "a")


def test_a_pure_move_of_a_test_is_judged_green_on_head_only_and_an_edited_move_still_owes_its_red(monkeypatch, tmp_path):
    """2026-11-25, app-bugs nightly-green-1 (alert 1932 at fe76a7261): 11 tests moved whole (R100) into the mirroring folder were
    asked as NOT RED ON BASE; a moved test passes on base where its old copy runs. With `red-on-base-pure-move` it is not asked."""
    import subprocess

    from fichero_builder import journal
    from fichero_builder.check_tool import Config

    def g(*a):
        return subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True, check=True).stdout.strip()
    g("init", "-q"), g("config", "user.email", "t@t"), g("config", "user.name", "t")
    (tmp_path / "tests" / "jobs").mkdir(parents=True)
    (tmp_path / "tests" / "jobs" / "test_moved.py").write_text("def test_a():\n    assert True\n" * 3)
    (tmp_path / "tests" / "jobs" / "test_edited.py").write_text("def test_b():\n    assert True\n" * 3)
    g("add", "."), g("commit", "-qm", "base")
    base = g("rev-parse", "HEAD")
    (tmp_path / "tests" / "execution").mkdir()
    g("mv", "tests/jobs/test_moved.py", "tests/execution/test_moved.py")
    g("mv", "tests/jobs/test_edited.py", "tests/execution/test_edited.py")
    (tmp_path / "tests" / "execution" / "test_edited.py").write_text("def test_b():\n    assert True\n" * 3 + "def test_c():\n    assert 1\n")
    g("add", "-A"), g("commit", "-qm", "move")
    head = g("rev-parse", "HEAD")
    assert check_tool.pure_moves(tmp_path, base, head) == {"tests/execution/test_moved.py": "tests/jobs/test_moved.py"}, "R100 only"

    files = ["tests/execution/test_moved.py", "tests/execution/test_edited.py"]
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(check_tool, "pytest_rung", lambda *a, **k: {"ok": True, "remote": "imac", "stdout_tail": "3 passed"})
    monkeypatch.setattr(check_tool, "green_runs", lambda *a, **k: {"ok": True, "stdout_tail": "", "name": "pytest"})
    monkeypatch.setattr(check_tool, "_git", lambda *a, **k: {"ok": True, "stdout_tail": "abc\n", "stderr_tail": ""})
    monkeypatch.setattr(check_tool, "already_built_files", lambda *a, **k: set())
    monkeypatch.setattr(check_tool, "data_only", lambda *a, **k: False)
    monkeypatch.setattr(check_tool, "_mkdtemp", lambda *a, **k: str(tmp_path / "base"))
    real_lines = check_tool._lines
    monkeypatch.setattr(check_tool, "_lines", lambda root, *a: real_lines(root, *a) if a[:2] == ("diff", "-M100%") else [])
    r = check_tool.red_on_base(tmp_path, base, head, files, Config(auto=("red-on-base-pure-move",)))
    assert not r["ok"] and "NOT RED ON BASE: tests/execution/test_edited.py" in r["stderr_tail"] and "test_moved.py" not in r["stderr_tail"]
    assert [x["file"] for x in journal.read() if x.get("rule") == "red-on-base-pure-move"] == ["tests/execution/test_moved.py"]
    r = check_tool.red_on_base(tmp_path, base, head, files, Config())
    assert "test_moved.py" in r["stderr_tail"], "without the rule in [check].auto: as before"


def _fix_world(tmp_path):
    """A repo: base, a step head h1 (a source change), a pinned copy with red_paths, build_paths and a guard with declared inputs, and the
    lane's last ladder at h1: red-on-base, guards and build green, unit red."""
    import json as _json
    import subprocess as sp
    r = tmp_path / "r"
    r.mkdir()

    def g(*a):
        return sp.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()
    (r / "src").mkdir()
    (r / "src" / "a.py").write_text("x = 1\n")
    g("init", "-q", "-b", "main"), g("add", "."), g("commit", "-qm", "base")
    base = g("rev-parse", "HEAD")
    (r / "src" / "a.py").write_text("x = 2\n")
    g("commit", "-qam", "step")
    h1 = g("rev-parse", "HEAD")
    pin = tmp_path / "pin"
    (pin / "scripts").mkdir(parents=True)
    (pin / "scripts" / "check_a.py").write_text("print('ok')\n")
    (pin / "harness.toml").write_text('[check]\nreuse_fix_verdicts = true\nred_paths = ["src/"]\nbuild_paths = ["app/"]\n'
                                      'guard_glob = "scripts/check_*.py"\n[check.guard_inputs]\ncheck_a = ["docs/"]\n')
    ladder = tmp_path / "ladder.json"
    rungs = [{"name": n, "ok": n != "unit"} for n in ("ready", "red-on-base", "unit", "guards", "build")]
    ladder.write_text(_json.dumps({"ok": False, "rungs": rungs, "head": h1, "since": base, "pinned": str(pin)}))
    return r, g, base, h1, pin, ladder


def test_a_fix_commit_that_touches_no_input_of_a_green_rung_keeps_its_verdict_with_a_reused_row(tmp_path):
    """local.check.fix-round-reuses-verdicts: a fix commit outside red_paths, the guard inputs (docs/) and the build paths (app/) keeps
    those three greens, each naming the head it was judged at; the red unit and the instant ready run again."""
    from fichero_builder import work
    r, g, base, h1, pin, ladder = _fix_world(tmp_path)
    (r / "notes.txt").write_text("fix\n")
    g("add", "."), g("commit", "-qm", "fix")
    kept = work.fix_reuse(str(r), str(ladder), base, g("rev-parse", "HEAD"), pin)
    assert sorted(kept) == ["build", "guards", "red-on-base"] and all(x["reused"] == h1 for x in kept.values())
    (r / "test_a.py").write_text("def test_x(): pass\n")
    g("add", "."), g("commit", "-qm", "a test")
    assert sorted(work.fix_reuse(str(r), str(ladder), base, g("rev-parse", "HEAD"), pin)) == ["build", "guards"], "a changed test: red-on-base runs"


def test_a_moved_base_a_rebased_head_or_a_touched_input_runs_the_rung_again(tmp_path):
    from fichero_builder import work
    r, g, base, h1, pin, ladder = _fix_world(tmp_path)
    (r / "docs").mkdir()
    (r / "docs" / "x.md").write_text("x\n")
    g("add", "."), g("commit", "-qm", "touch a guard input")
    head = g("rev-parse", "HEAD")
    assert "guards" not in work.fix_reuse(str(r), str(ladder), base, head, pin), "a guard's input touched"
    assert work.fix_reuse(str(r), str(ladder), "0" * 40, head, pin) == {}, "a moved base"
    assert work.fix_reuse(str(r), str(ladder), base, head, tmp_path / "other") == {}, "another pinned copy"
    g("reset", "-q", "--hard", base)
    (r / "src" / "a.py").write_text("x = 3\n")
    g("commit", "-qam", "rewritten")
    assert work.fix_reuse(str(r), str(ladder), base, g("rev-parse", "HEAD"), pin) == {}, "a head that does not descend"


def _rob(monkeypatch, owe):
    from fichero_builder.check_tool import Config
    seen = {}
    monkeypatch.setattr(check_tool, "OWE_WHOLE", check_tool._PerThread(owe))
    monkeypatch.setattr(check_tool, "red_on_base", lambda root, since, head, tests, cfg, **k: seen.update(tests=tests, also=k["also_green"]) or {"ok": True, "stdout_tail": "ok"})
    monkeypatch.setattr(check_tool, "_needs_red", lambda names, tests, cfg: True)
    r = check_tool.red_on_base_rung("/r", "b", "h", ["pkg/a.py", "pkg/tests/test_a.py"], ["pkg/tests/test_a.py"], ("pkg/tests",), Config(), "/own")
    return r, seen


def test_with_the_train_on_red_on_base_runs_only_the_changed_tests_and_lists_the_whole_dirs_as_owed(monkeypatch):
    r, seen = _rob(monkeypatch, True)
    assert seen == {"tests": ["pkg/tests/test_a.py"], "also": ()}, "the changed tests only, base and head"
    assert r["owed"] == ["pkg/tests"] and r["stdout_tail"].startswith("owed to the train: pkg/tests")
    from fichero_builder import work
    import types
    got = []
    monkeypatch.setattr(work.land_tool, "resolve_branch", lambda repo, branch: "b")
    monkeypatch.setattr(work.check_tool, "ladder_over", lambda *a, **k: got.append(work.check_tool.OWE_WHOLE[0]) or {"ok": True, "rungs": [], "owed": ["pkg/tests"]})
    monkeypatch.setattr(work.check_tool, "OWE_WHOLE", check_tool._PerThread(False))
    import tempfile
    d = tempfile.mkdtemp()
    monkeypatch.setattr(work.journal, "STATE", __import__("pathlib").Path(d))
    r = work.do_check(types.SimpleNamespace(name="l", pinned="/p", ids=[], train=True, owe_whole=True), "/r", "integration", "h", f"{d}/l.json")
    assert got == [True] and r["owed"] == ["pkg/tests"] and work.check_tool.OWE_WHOLE[0] is False, "set for the ladder only"


def test_with_the_train_off_the_head_run_still_includes_the_whole_dirs(monkeypatch):
    r, seen = _rob(monkeypatch, False)
    assert seen["also"] == ("pkg/tests",) and "owed" not in r


def test_security_contract_current_and_the_since_guards_keep_their_green_when_the_fix_touches_none_of_their_inputs(tmp_path):
    import json as _json
    from fichero_builder import work
    r, g, base, h1, pin, ladder = _fix_world(tmp_path)
    (pin / "harness.toml").write_text('[check]\nreuse_fix_verdicts = true\ncontract_paths = ["api/"]\ncontract_guards = ["scripts/check_contract.py"]\n'
                                      '[check.since_guards]\n"scripts/check_lint.py" = "app/"\n[check.security]\ndirs = ["srv/"]\n')
    three = ("security", "contract-current", "since-guards")
    ladder.write_text(_json.dumps({"ok": False, "rungs": [{"name": n, "ok": True} for n in three] + [{"name": "unit", "ok": False}],
                                   "head": h1, "since": base, "pinned": str(pin)}))

    def after(path):
        (r / path).parent.mkdir(parents=True, exist_ok=True)
        (r / path).write_text("fix\n")
        g("add", "."), g("commit", "-qm", "fix")
        return sorted(work.fix_reuse(str(r), str(ladder), base, g("rev-parse", "HEAD"), pin))
    assert after("notes.txt") == sorted(three)
    assert "contract-current" not in after("api/routes.py")
    assert "since-guards" not in after("app/V.swift")
    assert "security" not in after("srv/x.py")
    assert "security" not in after("scripts/gitleaks.toml"), "the scanner's own config is an input"
