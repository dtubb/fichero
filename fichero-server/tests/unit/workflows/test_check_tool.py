"""The check tool: argv lists with a cwd and a timeout each, typed results. (dev-workflows.tool.check, #6116.)"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from fichero_server.workflows import check_tool as ct

REPO = Path(__file__).resolve().parents[4]

KEYS = {"name", "argv", "exit_code", "ok", "timed_out", "seconds", "stdout_tail", "stderr_tail"}


def test_a_green_command_is_a_typed_result(tmp_path):
    r = ct.run_command("hello", [sys.executable, "-c", "print('hi')"], tmp_path, 20)
    assert set(r) == KEYS and r["ok"] and r["exit_code"] == 0 and r["stdout_tail"] == "hi" and not r["timed_out"]


def test_a_red_command_keeps_its_exit_code_and_stderr_tail(tmp_path):
    r = ct.run_command("bad", [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(4)"], tmp_path, 20)
    assert not r["ok"] and r["exit_code"] == 4 and r["stderr_tail"] == "boom"


def test_a_command_past_its_timeout_is_timed_out_not_ok(tmp_path):
    r = ct.run_command("slow", [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 1)
    assert r["timed_out"] and not r["ok"] and r["exit_code"] is None and r["seconds"] < 10


def test_a_missing_program_is_a_red_result_not_a_raise(tmp_path):
    r = ct.run_command("nope", ["/no/such/program"], tmp_path, 5)
    assert not r["ok"] and r["exit_code"] is None and "No such file" in r["stderr_tail"]


def test_the_tail_is_bounded(tmp_path):
    r = ct.run_command("long", [sys.executable, "-c", "print('x'*5000); print('\\n'.join(map(str, range(100))))"], tmp_path, 20)
    assert len(r["stdout_tail"].splitlines()) <= 40 and len(r["stdout_tail"]) <= 4000


def _repo(tmp_path, n_guards, bodies=None):
    s = tmp_path / "scripts"
    s.mkdir()
    for i in range(n_guards):
        (s / f"check_g{i}.py").write_text((bodies or {}).get(i, "pass\n"))
    return tmp_path


def test_guards_refuse_when_too_few_are_found(tmp_path):
    root = _repo(tmp_path, 3)
    r = ct.guards(root, ct.Config(guard_glob="scripts/check_*.py", min_guards=20))
    assert r["ok"] is False and "fewer than 20" in r["reason"] and r["results"] == []


def test_guards_run_each_one_skip_the_listed_and_name_the_red_one(tmp_path):
    root = _repo(tmp_path, 21, {1: "raise SystemExit(2)\n", 2: "raise SystemExit(2)\n"})
    r = ct.guards(root, ct.Config(guard_glob="scripts/check_*.py", min_guards=20, guard_skip=frozenset({"check_g2"})))
    names = [x["name"] for x in r["results"]]
    assert "check_g2" not in names and len(names) == 20
    assert r["ok"] is False and [x["name"] for x in r["results"] if not x["ok"]] == ["check_g1"]


def test_skipped_guards_do_not_count_toward_the_minimum(tmp_path):  # review-2 H10
    root = _repo(tmp_path, 20)
    r = ct.guards(root, ct.Config(guard_glob="scripts/check_*.py", min_guards=20, guard_skip=frozenset({"check_g2"})))
    assert not r["ok"] and "blind" in r["reason"]


def test_fichero_is_the_first_project_in_its_own_harness_toml():
    cfg = ct.load(REPO)
    assert {"check_coverage_ratchet", "check_docs_paths", "check_hang_ratchet"} <= cfg.guard_skip and len(cfg.guard_skip) == 15
    assert cfg.min_guards == 20 and cfg.guard_glob == "scripts/check_*.py" and cfg.ready == ("scripts/lane_ready_check.sh", "HEAD")
    assert ct.load(REPO / "no-such-dir") == ct.Config()  # no harness.toml = no project rules, nothing hardcoded


def test_pytest_runs_named_files_with_the_fixed_env(tmp_path):
    (tmp_path / "test_a.py").write_text("import os\ndef test_a():\n    assert os.environ['FICHERO_FEATURE_TIER'] == 'dev'\n    assert os.environ['OMP_NUM_THREADS'] == '2'\n    assert os.environ['PYTHONSAFEPATH'] == '1'\n    assert os.environ['RUFF_NO_CACHE'] == 'true'\n")
    cfg = ct.Config(test_env={"FICHERO_FEATURE_TIER": "dev", "OMP_NUM_THREADS": "2"})
    r = ct.pytest_rung(tmp_path, ["test_a.py"], cfg, timeout_s=120)
    assert r["ok"], r


def test_pytest_with_no_files_is_red(tmp_path):
    assert ct.pytest_rung(tmp_path, [], ct.Config(), timeout_s=5)["ok"] is False


def test_contract_current_is_skipped_unless_engine_source_changed(tmp_path):
    assert ct.contract_current(tmp_path, ["docs/x.md"], ct.load(REPO)) == {"ok": True, "skipped": True, "results": []}


# --- diff bound, failing run (red on base), the ladder (dev-workflows.tool.check) ---

import subprocess  # noqa: E402


def _git_repo(tmp_path):
    def g(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    (tmp_path / "mod.py").write_text("VALUE = 1\n")
    g("add", "."), g("commit", "-q", "-m", "base")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    return g, base


def test_diff_bound_trips_on_too_many_files_or_lines(tmp_path):
    g, base = _git_repo(tmp_path)
    (tmp_path / "a.py").write_text("x\n" * 30)
    (tmp_path / "b.py").write_text("y\n")
    g("add", "."), g("commit", "-q", "-m", "more")
    assert ct.diff_bound(tmp_path, base, "HEAD", ct.Config(max_files=5, max_lines=100))["ok"]
    r = ct.diff_bound(tmp_path, base, "HEAD", ct.Config(max_files=1, max_lines=100))
    assert not r["ok"] and "2 files" in r["stderr_tail"]
    assert not ct.diff_bound(tmp_path, base, "HEAD", ct.Config(max_files=5, max_lines=10))["ok"]


def test_red_on_base_needs_a_test_that_fails_on_base_and_passes_on_head(tmp_path):
    g, base = _git_repo(tmp_path)
    (tmp_path / "mod.py").write_text("VALUE = 2\n")
    (tmp_path / "test_mod.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 2\n")
    (tmp_path / "test_proves_nothing.py").write_text("def test_t():\n    assert True\n")
    g("add", "."), g("commit", "-q", "-m", "change")
    assert ct.red_on_base(tmp_path, base, "HEAD", ["test_mod.py"], timeout_s=120)["ok"]
    r = ct.red_on_base(tmp_path, base, "HEAD", ["test_proves_nothing.py"], timeout_s=120)
    assert not r["ok"] and "NOT RED ON BASE" in r["stderr_tail"]
    assert not ct.red_on_base(tmp_path, base, "HEAD", [], timeout_s=5)["ok"]


def test_check_tool_runs_the_ladder(tmp_path):
    """dev-workflows.tool.check: rungs in order, stops at the first red, every result typed."""
    calls = []
    rungs = [("one", lambda: calls.append(1) or {"ok": True, "results": []}),
             ("two", lambda: calls.append(2) or {"ok": False, "results": []}),
             ("three", lambda: calls.append(3) or {"ok": True, "results": []})]
    r = ct.ladder(rungs)
    assert calls == [1, 2] and r["ok"] is False and r["failed"] == "two" and [x["name"] for x in r["rungs"]] == ["one", "two"]
    assert ct.ladder(rungs[:1])["ok"] is True


def _project(tmp_path, extra="", check_extra=""):
    """A throwaway project: its own harness.toml, one good guard, one skipped bad guard; plus a pinned clone of it."""
    work = tmp_path / "work"
    work.mkdir()
    g, _ = _git_repo(work)
    (work / "ci").mkdir()
    (work / "ci" / "lint_ok.py").write_text("pass\n")
    (work / "ci" / "lint_bad.py").write_text("raise SystemExit(7)\n")
    (work / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")  # the pinned pytest config a rules file must name
    (work / "harness.toml").write_text(
        '[check]\n' + check_extra + 'ready = ["python3", "-c", "print(1)"]\nguard_glob = "ci/lint_*.py"\nmin_guards = 1\n'
        'guard_skip = ["lint_bad"]\ncheck_paths = ["ci/", "harness.toml"]\nmax_files = 10\n[check.test_env]\nTINY_PROJECT = "yes"\n' + extra)
    g("add", "."), g("commit", "-q", "-m", "project")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    pinned = tmp_path / "pinned"
    subprocess.run(["git", "clone", "-q", str(work), str(pinned)], check=True, capture_output=True)
    return work, g, base, pinned


def test_the_tool_runs_in_a_throwaway_project_with_its_own_config(tmp_path):
    """Outside Fichero: no Fichero path, check name or env anywhere; the pinned copy's harness.toml says what to run."""
    work, g, base, pinned = _project(tmp_path)
    (work / "mod.py").write_text("VALUE = 2\n")
    (work / "test_mod.py").write_text("import os, mod\ndef test_v():\n    assert mod.VALUE == 2 and os.environ['TINY_PROJECT'] == 'yes'\n")
    g("add", "."), g("commit", "-q", "-m", "change")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert r["ok"], r
    assert [x["name"] for x in r["rungs"]] == ["pinned-checks", "ready", "diff-bound", "red-on-base", "guards", "contract-current", "build"]


def test_a_worker_cannot_change_the_checks_it_is_judged_by(tmp_path):
    """The worker edits a guard, the config, or .claude/: needs-maintainer, nothing else runs."""
    work, g, base, pinned = _project(tmp_path)
    (work / "ci" / "lint_ok.py").write_text("raise SystemExit(0)  # edited by the worker\n")
    g("add", "."), g("commit", "-q", "-m", "edit guard")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert not r["ok"] and r["failed"] == "pinned-checks" and [x["name"] for x in r["rungs"]] == ["pinned-checks"]
    assert "ci/lint_ok.py" in r["rungs"][0]["stderr_tail"] and "needs-maintainer" in r["rungs"][0]["stderr_tail"]
    g("reset", "-q", "--hard", base)
    (work / ".claude").mkdir()
    (work / ".claude" / "settings.json").write_text("{}")
    (work / "sitecustomize.py").write_text("print('hi')\n")
    g("add", "."), g("commit", "-q", "-m", "hooks")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert r["failed"] == "pinned-checks" and ".claude/settings.json" in r["rungs"][0]["stderr_tail"] and "sitecustomize.py" in r["rungs"][0]["stderr_tail"]


def test_the_ladder_runs_the_pinned_guards_not_the_workers_copies(tmp_path):
    """A guard the worker ADDS runs (allowed); the pinned config still skips lint_bad, and the pinned bytes win."""
    work, g, base, pinned = _project(tmp_path)
    (work / "ci" / "lint_new.py").write_text("raise SystemExit(3)\n")
    (work / "mod.py").write_text("VALUE = 2\n")
    (work / "test_mod.py").write_text("import os, mod\ndef test_v():\n    assert mod.VALUE == 2 and os.environ['TINY_PROJECT'] == 'yes'\n")
    g("add", "."), g("commit", "-q", "-m", "add a failing guard")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert not r["ok"] and r["failed"] == "guards"
    assert [x["name"] for x in r["rungs"][-1]["results"] if not x["ok"]] == ["lint_new"]


def test_no_rung_sees_the_workers_home_or_a_real_base_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/Users/someone")
    cfg = ct.Config(base_path_env="PROJ_BASE")
    env = ct._env(tmp_path, cfg)
    assert env["HOME"] != "/Users/someone" and env["PROJ_BASE"] and env["PROJ_BASE"] != env["HOME"]


def test_a_big_diff_is_not_truncated_by_the_output_tail(tmp_path):
    g, base = _git_repo(tmp_path)
    for i in range(45):
        (tmp_path / f"f{i}.txt").write_text("x\n")
    g("add", "."), g("commit", "-q", "-m", "many")
    r = ct.diff_bound(tmp_path, base, "HEAD", ct.Config(max_files=44))
    assert not r["ok"] and "45 files" in r["stderr_tail"]


def test_a_worker_cannot_weaken_its_own_tests(tmp_path):
    """A test function removed, fewer asserts, or more skips in an existing test file: needs-maintainer."""
    work, g, base, pinned = _project(tmp_path)
    (work / "test_old.py").write_text("def test_a():\n    assert 1\n    assert 2\ndef test_b():\n    assert 3\n")
    g("add", "."), g("commit", "-q", "-m", "tests")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(pinned), "pull", "-q"], check=True, capture_output=True)
    cfg = ct.load(pinned)
    (work / "test_old.py").write_text("def test_a():\n    assert 1\ndef test_b():\n    assert 3\n")  # one assert fewer
    g("commit", "-qam", "weaker")
    assert ct.weakened_tests(work, base, "HEAD", cfg) == ["test_old.py"]
    g("reset", "-q", "--hard", base)
    (work / "test_old.py").write_text("def test_a():\n    assert 1\n    assert 2\ndef test_b():\n    assert 3\ndef test_c():\n    assert 4\n")
    g("commit", "-qam", "stronger")
    assert ct.weakened_tests(work, base, "HEAD", cfg) == []
    g("reset", "-q", "--hard", base)
    (work / "test_old.py").write_text("import pytest\n@pytest.mark.skip\ndef test_a():\n    assert 1\n    assert 2\ndef test_b():\n    assert 3\n")
    g("commit", "-qam", "skip")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert r["failed"] == "pinned-checks" and "test_old.py" in r["rungs"][0]["stderr_tail"]


def test_a_worker_cannot_rewrite_its_own_acceptance(tmp_path):
    """The item's own spec bullet may flip its status tag or gain (#N); any other change is needs-maintainer."""
    work, g, base0, pinned = _project(tmp_path)
    (work / "rules").mkdir()
    spec = work / "rules" / "s.md"
    spec.write_text("- `demo.item.one` [PROPOSED] — it does the thing, and ten more.\n- `demo.other` [OK] — unrelated.\n")
    g("add", "."), g("commit", "-q", "-m", "spec")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    cfg = ct.Config(spec_dir="rules")
    spec.write_text("- `demo.item.one` [OK] (#12) — it does the thing, and ten more.\n- `demo.other` [OK] — unrelated.\n")
    g("commit", "-qam", "tag flip")
    assert ct.acceptance_changed(work, base, "HEAD", cfg, ["demo.item.one"]) == []
    spec.write_text("- `demo.item.one` [OK] — it does less.\n- `demo.other` [OK] — unrelated.\n")
    g("commit", "-qam", "rewrite")
    hits = ct.acceptance_changed(work, base, "HEAD", cfg, ["demo.item.one"])
    assert hits and "rules/s.md" in hits[0]
    assert ct.acceptance_changed(work, base, "HEAD", cfg, ["demo.other"]) == []  # only the item's own ids are protected


def test_a_workers_git_config_filter_never_runs_at_checkout(tmp_path):
    """review 2 B2: smudge filters in the worker's .git/config must not run when the ladder makes its trees."""
    g, base = _git_repo(tmp_path)
    (tmp_path / ".gitattributes").write_text("*.txt filter=evil\n")
    (tmp_path / "a.txt").write_text("x\n")
    g("add", "."), g("commit", "-q", "-m", "attrs")
    marker = tmp_path.parent / (tmp_path.name + "-ran")
    g("config", "filter.evil.smudge", f"touch {marker}; cat")
    g("config", "filter.evil.clean", "cat")
    g("config", "diff.external", f"touch {marker}")
    tree = ct._scratch_tree(tmp_path, "HEAD", tmp_path, ct.Config())
    ct.diff_bound(tmp_path, base, "HEAD", ct.Config())
    ct._git(tmp_path, "worktree", "remove", "--force", tree)
    assert not marker.exists()


def _change(work, g):
    (work / "mod.py").write_text("VALUE = 2\n")
    (work / "test_mod.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 2\n")
    g("add", "."), g("commit", "-q", "-m", "change")


def test_a_missing_jail_user_refuses_the_ladder(tmp_path):
    from fichero_server.workflows.jail import JailMissing
    work, g, base, pinned = _project(tmp_path, '[jail]\nuser = "no-such-user-xyz"\n')
    _change(work, g)
    with pytest.raises(JailMissing):
        ct.run_ladder(work, base, "HEAD", pinned)
    assert ct._JAIL is None


def test_the_ladder_runs_its_commands_as_the_jail_user(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin:" + str(Path(sys.executable).parent))  # no gh login to trip the probe
    h = tmp_path / "ownerhome"
    h.mkdir()
    h.chmod(0)  # the probe's floor wants the owner's home unreadable
    monkeypatch.setenv("HOME", str(h))
    sudo = tmp_path / "sudo"
    sudo.write_text('#!/bin/sh\necho "$3" >> "%s/asked"\nshift 4\nexec "$@"\n' % tmp_path)
    sudo.chmod(0o755)
    work, g, base, pinned = _project(tmp_path, check_extra=f'python = "{sys.executable}"\ncontract_guards = ["ci/lint_ok.py"]\ncontract_paths = ["src/"]\npytest_config = "pyproject.toml"\n', extra=f'[land]\nbranch = "main"\nboundary = "ci/"\n'
                                f'[jail]\nuser = "root"\nsudo = "{sudo}"\nworkroot = "{tmp_path}"\ndeny_read = ["{tmp_path}/secret"]\n')
    _change(work, g)
    r = ct.run_ladder(work, base, "HEAD", pinned)
    assert r["ok"], r
    assert "root" in (tmp_path / "asked").read_text()  # ready, pytest and guards went through sudo
    assert ct._JAIL is None


def test_no_jail_table_refuses_the_ladder(tmp_path):
    from fichero_server.workflows.jail import JailMissing
    work, g, base, pinned = _project(tmp_path, "")
    _change(work, g)
    with pytest.raises(JailMissing, match="no \\[jail\\]"):
        ct.run_ladder(work, base, "HEAD", pinned)


def test_unknown_check_keys_refuse(tmp_path):
    (tmp_path / "harness.toml").write_text("[check]\nguard_glob_typo = 1\n")
    with pytest.raises(ValueError, match="unknown keys"):
        ct.load(tmp_path)


def test_a_new_file_under_a_pinned_path_or_any_conftest_is_a_question(tmp_path):
    """Review 3 H2: added files, not only changed ones, are judged; a new guard (guard_glob) is the one allowed addition."""
    work, g, base, pinned = _project(tmp_path)
    (work / "ci" / "helper.py").write_text("x = 1\n")
    (work / "tests").mkdir()
    (work / "tests" / "conftest.py").write_text("import pytest\n")
    g("add", "."), g("commit", "-q", "-m", "adds")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    err = r["rungs"][0]["stderr_tail"]
    assert r["failed"] == "pinned-checks" and "ci/helper.py" in err and "tests/conftest.py" in err


def test_red_on_base_applies_only_to_the_paths_the_rules_file_names(tmp_path):
    """Spec 'by path': a docs change is not red-on-base-able; a change under red_paths still needs its failing test."""
    work, g, base, pinned = _project(tmp_path, "")
    cfg_extra = '\nred_paths = ["src/"]\n'
    (pinned / "harness.toml").write_text((pinned / "harness.toml").read_text().replace("[check]\n", "[check]" + cfg_extra, 1))
    (work / "docs").mkdir()
    (work / "docs" / "a.md").write_text("hi\n")
    g("add", "."), g("commit", "-q", "-m", "docs")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert r["ok"] and "not required" in [x for x in r["rungs"] if x["name"] == "red-on-base"][0]["stdout_tail"]
    (work / "src").mkdir()
    (work / "src" / "m.py").write_text("X = 1\n")
    g("add", "."), g("commit", "-q", "-m", "source with no test")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert r["failed"] == "red-on-base" and "needs a test" in r["rungs"][-1]["stderr_tail"]


def test_the_build_rung_runs_only_for_build_paths_and_reports_red(tmp_path):  # owner 2026-11-01: a build-only Swift rung
    cfg = ct.Config(build_paths=("fichero/",), build=("sh", "-c", "echo built > built.txt; exit 1"), build_lock=str(tmp_path / "b.lock"))
    assert ct.build(tmp_path, ["fichero-server/src/x.py"], cfg)["skipped"], "no Swift touched: no build"
    assert ct.build(tmp_path, ["fichero/App.swift"], ct.Config())["skipped"], "no build configured: no build"
    r = ct.build(tmp_path, ["fichero/App.swift"], cfg)
    assert not r["ok"] and not r["skipped"] and r["results"][0]["exit_code"] == 1
    assert (tmp_path / "built.txt").exists(), "the build ran in the tree it was given"
    assert ct.build(tmp_path, ["fichero/App.swift"], ct.Config(build_paths=("fichero/",), build=("true",)))["ok"]
    deep = ct.Config(build_paths=("fichero/",), build=("true",), build_lock=str(tmp_path / "no" / "such" / "dir" / "b.lock"))
    assert ct.build(tmp_path, ["fichero/App.swift"], deep)["ok"] and (tmp_path / "no" / "such" / "dir" / "b.lock").exists(), "the lock's dir is made (review 2 R2)"


def test_the_build_rung_counts_a_deleted_swift_file_as_a_change(tmp_path):  # review 1 M7
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "fichero").mkdir()
    (tmp_path / "fichero" / "A.swift").write_text("a")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(tmp_path)}
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "base"], check=True, env=env)
    base = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (tmp_path / "fichero" / "A.swift").unlink()
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qam", "delete"], check=True, env=env)
    assert ct.build_names(tmp_path, base, "HEAD") == ["fichero/A.swift"]


def test_the_ready_rung_lets_the_projects_scripts_import_their_siblings(tmp_path):  # first real check, 2026-11-01
    """The ladder's PYTHONSAFEPATH is for pytest; a readiness script runs guard scripts by plain python, and those import
    helpers beside them, which safe-path forbids."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "_helper.py").write_text("OK = True\n")
    (tmp_path / "scripts" / "guard.py").write_text("from _helper import OK\nassert OK\n")
    (tmp_path / "scripts" / "ready.sh").write_text(f"#!/bin/sh\nexec {sys.executable} scripts/guard.py\n")
    (tmp_path / "scripts" / "ready.sh").chmod(0o755)
    r = ct.ready(tmp_path, ct.Config(ready=("scripts/ready.sh",)))
    assert r["ok"], r["stderr_tail"]
    (tmp_path / "scripts" / "check_spawn.py").write_text("import subprocess, sys; sys.exit(subprocess.run([sys.executable, 'scripts/guard.py']).returncode)\n")
    g = ct.guards(tmp_path, ct.Config(guard_glob="scripts/check_*.py"))
    assert g["ok"], g["results"]  # a guard that runs a sibling script by plain python: the same rule


def test_scratch_dirs_are_removed_through_the_jail_when_one_is_set(tmp_path, monkeypatch):  # 2026-11-01: nine check-base dirs left behind
    calls = []

    class FakeJail:
        def argv(self, argv, cwd=None, env=None):
            calls.append(list(argv))
            return argv
    monkeypatch.setattr(ct, "_JAIL", FakeJail())
    d = tmp_path / "scratch"
    d.mkdir()
    (d / "f").write_text("x")
    ct._remove_scratch(str(d))
    assert not d.exists() and calls and calls[0][:2] == ["rm", "-rf"]


def test_a_builder_change_owes_a_red_on_base_test_and_its_tests_run_with_the_builder_on_the_path():
    """dev-workflows.tool.check: the project's own harness.toml puts fichero-builder under red_paths and python_path."""
    cfg = ct.load(REPO)
    assert ct._needs_red(["fichero-builder/fichero_builder/work.py"], [], cfg), "a Builder source change needs a red-on-base test"
    assert not ct._needs_red(["docs/contributor_manual/a.md"], [], cfg)
    assert "fichero-builder" in cfg.python_path


def test_a_maintainer_batch_records_the_pinned_change_and_runs_the_rest(tmp_path):
    """A maintainer batch changes a pinned file on purpose: with maintainer=True the pinned-checks row says so and stays
    green, the ladder judges the candidate by its own rules; a weakened test or rewritten acceptance still refuses."""
    work, g, base, pinned = _project(tmp_path)
    (work / "ci" / "lint_ok.py").write_text("raise SystemExit(0)  # edited by the maintainer\n")
    (work / "mod.py").write_text("VALUE = 2\n")
    (work / "test_mod.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 2\n")
    g("add", "."), g("commit", "-q", "-m", "edit guard")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False, maintainer=True)
    assert r["ok"], r
    assert r["rungs"][0]["ok"] and "ci/lint_ok.py" in r["rungs"][0]["stdout_tail"] and "maintainer" in r["rungs"][0]["stdout_tail"]
    assert [x["name"] for x in r["rungs"]][:3] == ["pinned-checks", "ready", "diff-bound"]
    (work / "test_old.py").write_text("def test_a():\n    assert 1\n    assert 2\ndef test_b():\n    assert 3\n")
    g("add", "."), g("commit", "-q", "-m", "a test")
    base2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    (work / "test_old.py").write_text("def test_a():\n    assert 1\n")
    g("add", "."), g("commit", "-q", "-m", "weaken")
    r = ct.run_ladder(work, base2, "HEAD", pinned, jail_required=False, maintainer=True)
    assert not r["ok"] and r["failed"] == "pinned-checks" and "weakens" in r["rungs"][0]["stderr_tail"]
    # a rewritten acceptance line under --maintainer still refuses (the pinned list is noted; the acceptance rule is not)
    (tmp_path / "two").mkdir()
    work, g, _b, pinned = _project(tmp_path / "two", check_extra='spec_dir = "rules"\n')
    (work / "rules").mkdir()
    (work / "rules" / "s.md").write_text("- `demo.item.one` [PROPOSED] — it does the thing, and ten more.\n")
    g("add", "."), g("commit", "-q", "-m", "spec")
    base3 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "fetch", "-q", str(work)], cwd=pinned, check=True)  # the pinned clone knows the spec commit
    (work / "rules" / "s.md").write_text("- `demo.item.one` [OK] — it does less.\n")
    g("commit", "-qam", "rewrite acceptance")
    r = ct.run_ladder(work, base3, "HEAD", pinned, jail_required=False, maintainer=True, protected_ids=["demo.item.one"])
    assert not r["ok"] and r["failed"] == "pinned-checks" and "acceptance" in r["rungs"][0]["stderr_tail"]
