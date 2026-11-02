"""The check tool: argv lists with a cwd and a timeout each, typed results. (dev-workflows.tool.check, #6116.)"""

from __future__ import annotations

import os
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


def test_a_red_pytest_tail_keeps_the_failure_when_warnings_follow_it():
    """A red rung lost its failure text to 40 lines of warnings after it (chunk A's red, 2026-11-01)."""
    text = "\n".join(["collected", "=" * 20 + " FAILURES " + "=" * 20, "_ test_x _", "    def test_x():", "E   AssertionError: the real reason", "t.py:3: AssertionError",
                      "=" * 20 + " warnings summary " + "=" * 20, *[f"warning {i}" for i in range(200)], "=" * 20 + " short test summary info " + "=" * 20,
                      "FAILED t.py::test_x", "1 failed, 14 passed"])
    kept = ct.tail(text)
    assert "E   AssertionError: the real reason" in kept and "1 failed, 14 passed" in kept
    assert len(kept) <= 4100 and len(kept.splitlines()) <= 41
    plain = "\n".join(f"line {i}" for i in range(100))
    assert ct.tail(plain).splitlines()[0] == "line 60", "no failure section: the plain last lines"


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
    assert cfg.min_guards == 20 and cfg.guard_glob == "scripts/check_*.py" and cfg.ready == ("scripts/lane_ready_check.sh", "--no-guards", "HEAD")
    assert ct.load(REPO / "no-such-dir") == ct.Config()  # no harness.toml = no project rules, nothing hardcoded


def test_the_build_rung_never_resolves_packages_so_a_read_only_check_tree_builds():
    """2026-11-01: a real Swift check failed with exit 74, xcodebuild wanting to write Package.resolved into the owner-made
    read-only scratch tree. Package.resolved is tracked, so resolution is told to read it and write nothing."""
    cfg = ct.load(REPO)
    assert "-disableAutomaticPackageResolution" in cfg.build
    assert cfg.build.index("-disableAutomaticPackageResolution") < cfg.build.index("build")


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
    assert [x["name"] for x in r["rungs"]] == ["pinned-checks", "ready", "diff-bound", "red-on-base", "guards", "contract-current", "since-guards", "build"]


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


def test_a_maintainer_batch_skips_the_diff_bound_and_a_worker_range_keeps_it(tmp_path):
    """Owner 2026-11-02: guards that stop ordinary work are loosened; the 25-file/1500-line bound is for a jailed worker's
    range, a maintainer batch is split for review by size instead (land_tool.review_groups)."""
    work, g, base, pinned = _project(tmp_path, check_extra="max_lines = 3\n")
    (work / "mod.py").write_text("VALUE = 2\n")
    (work / "test_mod.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 2\n")
    g("add", "."), g("commit", "-q", "-m", "change")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert not r["ok"] and r["failed"] == "diff-bound", r
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False, maintainer=True)
    assert r["ok"], r
    row = next(x for x in r["rungs"] if x["name"] == "diff-bound")
    assert row["ok"] and "maintainer" in row["stdout_tail"] and "5 lines" in row["stdout_tail"], "the size is still shown"


def test_a_since_guard_runs_with_the_range_base_only_when_the_diff_touches_its_prefix(tmp_path):
    """#6318: the SwiftLint ratchet's `--since` question (did this item add warnings in the files it changes) ran in the gate
    only; `[check].since_guards` runs a guard with `--since <base>` in the scratch tree when the diff touches its prefix."""
    work, g, base, pinned = _project(tmp_path, check_extra='since_guards = { "ci/since_g.py" = "app/" }\nred_paths = ["src/"]\n')
    (work / "ci" / "since_g.py").write_text(
        "import sys, pathlib\nargs = sys.argv[1:]\nprint('since', args)\n"
        "raise SystemExit(1 if args[:1] == ['--since'] and pathlib.Path('app/warn.txt').exists() else 0)\n")
    g("add", "."), g("commit", "-q", "-m", "the guard")
    subprocess.run(["git", "-C", str(pinned), "pull", "-q"], check=True, capture_output=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    (work / "other.txt").write_text("x\n")
    g("add", "."), g("commit", "-q", "-m", "not under app/")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    row = next(x for x in r["rungs"] if x["name"] == "since-guards")
    assert r["ok"] and row.get("skipped"), r
    (work / "app").mkdir()
    (work / "app" / "warn.txt").write_text("a warning\n")
    g("add", "."), g("commit", "-q", "-m", "adds a warning")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert not r["ok"] and r["failed"] == "since-guards", r
    row = next(x for x in r["rungs"] if x["name"] == "since-guards")
    assert f"'--since', '{base}'" in row["results"][0]["stdout_tail"], "the guard gets the range's base"


def test_a_change_under_a_whole_tests_prefix_runs_that_tests_dir_whole_in_the_green_run(tmp_path):
    """review of fd9f26187: a Builder source change ran only its own new test, so an old test it broke slipped through."""
    work, g, _b, pinned = _project(tmp_path, extra='[check.whole_tests]\n"mod.py" = "suite"\n',
                                   check_extra=f'python = "{sys.executable}"\npython_path = ["."]\nred_paths = ["mod.py"]\n')
    (work / "suite").mkdir()
    (work / "mod.py").write_text("VALUE = 1\n")
    (work / "suite" / "test_old.py").write_text("import mod\ndef test_old():\n    assert mod.VALUE == 1\n")
    g("add", "."), g("commit", "-q", "-m", "old suite")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "fetch", "-q", str(work)], cwd=pinned, check=True)
    (work / "mod.py").write_text("VALUE = 2\n")
    (work / "test_mod.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 2\n")
    g("add", "."), g("commit", "-q", "-m", "change")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert not r["ok"] and r["failed"] == "red-on-base", r
    assert "test_old" in r["rungs"][-1]["stdout_tail"] + r["rungs"][-1]["stderr_tail"]


@pytest.mark.parametrize("name,write", [
    ("symlink", lambda w: (w / "link").symlink_to("mod.py")),
    ("sitecustomize", lambda w: (w / "sitecustomize.py").write_text("pass\n")),
    ("claude-dir", lambda w: ((w / ".claude").mkdir(), (w / ".claude" / "settings.json").write_text("{}\n"))),
    ("new-pinned-file", lambda w: (w / "ci" / "helper.py").write_text("pass\n")),
    ("pth", lambda w: (w / "x.pth").write_text("import os\n")),
    ("sitecustomize-under-a-dir-named-like-the-note",  # the phrase inside a worker-chosen path must not clear its own violation
     lambda w: ((w / "a: a pinned check file was x").mkdir(), (w / "a: a pinned check file was x" / "sitecustomize.py").write_text("pass\n"))),
])
def test_a_maintainer_batch_clears_only_a_changed_pinned_file_not_the_other_pinned_refusals(tmp_path, name, write):
    work, g, base, pinned = _project(tmp_path)
    (work / "ci" / "lint_ok.py").write_text("raise SystemExit(0)  # edited by the maintainer\n")  # the one thing --maintainer clears
    write(work)
    (work / "mod.py").write_text("VALUE = 2\n")
    (work / "test_mod.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 2\n")
    g("add", "-A"), g("commit", "-q", "-m", name)
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False, maintainer=True)
    assert not r["ok"] and r["failed"] == "pinned-checks", r
    said = r["rungs"][0]["stderr_tail"]
    assert "needs-maintainer" in said and "a pinned check file was changed" not in said


def _whole_project(tmp_path):
    """An engine-shaped `tests` package (with __init__.py) beside pkg/tests, a whole_tests dir with no __init__.py whose
    old test does `from tests import _helper`: one pytest over both collects the wrong `tests` and errors."""
    work, g, _b, pinned = _project(tmp_path, extra='[check.whole_tests]\n"pkg/lib.py" = "pkg/tests"\n',
                                   check_extra=f'python = "{sys.executable}"\npython_path = ["pkg"]\nred_paths = ["pkg/"]\n')
    (work / "pkg" / "tests").mkdir(parents=True)
    (work / "tests").mkdir()
    (work / "tests" / "__init__.py").write_text("")
    (work / "pkg" / "lib.py").write_text("VALUE = 1\n")
    (work / "pkg" / "gone.py").write_text("X = 1\n")
    (work / "pkg" / "tests" / "_helper.py").write_text("ANSWER = 1\n")
    (work / "pkg" / "tests" / "test_old.py").write_text(
        "import gone, lib\nfrom tests import _helper\ndef test_old():\n    assert lib.VALUE >= 1 and _helper.ANSWER == 1 and gone.X == 1\n")
    g("add", "."), g("commit", "-q", "-m", "old suite")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "fetch", "-q", str(work)], cwd=pinned, check=True)
    return work, g, base, pinned


def test_a_whole_tests_dir_runs_as_its_own_pytest_beside_an_engine_shaped_tests_package(tmp_path):
    """review 5 must-fix 1: fichero-builder/tests has no __init__.py, the engine's tests/ has one; in one process the
    second `from tests import x` failed. Each whole dir is its own pytest from its package dir; both runs are recorded."""
    work, g, base, _pinned = _whole_project(tmp_path)
    (work / "pkg" / "lib.py").write_text("VALUE = 2\n")
    (work / "tests" / "test_new.py").write_text("import lib\ndef test_v():\n    assert lib.VALUE == 2\n")
    g("add", "."), g("commit", "-q", "-m", "change")
    r = ct.run_ladder(work, base, "HEAD", _pinned, jail_required=False)
    assert r["ok"], r["rungs"][-1]["stdout_tail"] + r["rungs"][-1]["stderr_tail"]
    row = next(x for x in r["rungs"] if x["name"] == "red-on-base")
    assert len(row["runs"]) == 2 and all(x["ok"] for x in row["runs"])
    assert "test_new.py" in " ".join(row["runs"][0]["argv"]) and "pkg/tests" in " ".join(row["runs"][1]["argv"])
    assert "test_new.py" not in " ".join(row["runs"][1]["argv"]), "the engine-shaped run keeps only the changed files"


@pytest.mark.parametrize("path", ["pkg/pyproject.toml", "pkg/tests/pyproject.toml", "pkg/.pytest.ini", "pkg/tests/.pytest.ini",
                                  "pkg/pytest.toml", "pkg/.pytest.toml"])
def test_a_pytest_config_file_anywhere_is_a_pinned_name_so_it_cannot_turn_the_whole_tests_run_into_collection(tmp_path, path):
    """review 6 must-fix 1: the whole-tests run used the package's own pyproject.toml, or pytest's upward search, so a
    worker-added config with `addopts = --co` made a red suite green by collecting only. Every name pytest reads is pinned."""
    work, g, base, pinned = _whole_project(tmp_path)
    (work / "pkg" / "lib.py").write_text("VALUE = 0\n")  # breaks test_old
    body = ('[tool.pytest.ini_options]\naddopts = "--co"\n' if path.endswith("pyproject.toml")
            else "[pytest]\naddopts = --co\n" if path.endswith(".ini") else '[pytest]\naddopts = "--co"\n')
    (work / path).write_text(body)
    g("add", "-A"), g("commit", "-q", "-m", "config")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert not r["ok"] and r["failed"] == "pinned-checks", r


def test_a_deletion_under_a_whole_tests_prefix_runs_the_dir_whole_even_with_no_test_changed(tmp_path):
    """review 5 must-fix 3: a delete-only commit skipped red-on-base, so the old test importing the deleted file never ran."""
    work, g, base, pinned = _whole_project(tmp_path)
    (work / "pkg" / "gone.py").unlink()
    (work / "pkg" / "lib.py").unlink()
    g("add", "-A"), g("commit", "-q", "-m", "delete")
    r = ct.run_ladder(work, base, "HEAD", pinned, jail_required=False)
    assert not r["ok"] and r["failed"] == "red-on-base", r
    assert "test_old" in r["rungs"][-1]["stdout_tail"] + r["rungs"][-1]["stderr_tail"]


def test_a_change_outside_the_whole_tests_prefix_runs_only_the_changed_test_files(tmp_path):
    work, g, base, pinned = _whole_project(tmp_path)
    (work / "other.py").write_text("Y = 1\n")
    (work / "tests" / "test_new.py").write_text("import sys; sys.path.insert(0, \".\")\nimport other\ndef test_v():\n    assert other.Y == 1\n")
    g("add", "."), g("commit", "-q", "-m", "elsewhere")
    cfg = ct.load(pinned)
    assert ct._whole_tests(["other.py", "tests/test_new.py"], cfg) == ()
    assert ct._whole_tests(["pkg/lib.py"], cfg) == ("pkg/tests",)


def test_already_built_exempts_only_a_test_only_commit_that_names_its_test(tmp_path):
    """The worker writes the message: a line on a commit that also changes source would opt out of the red proof."""
    g, base = _git_repo(tmp_path)
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n")
    g("add", "."), g("commit", "-q", "-m", "good\n\nAlready built: #9 test_a.py::test_a")
    (tmp_path / "test_b.py").write_text("def test_b():\n    assert True\n")
    (tmp_path / "mod.py").write_text("VALUE = 2\n")
    g("add", "."), g("commit", "-q", "-m", "source too\n\nAlready built: #9 test_b.py::test_b")
    (tmp_path / "test_c.py").write_text("def test_c():\n    assert True\n")
    g("add", "."), g("commit", "-q", "-m", "no test named\n\nAlready built: #9")
    (tmp_path / "test_d.py").write_text("def test_d():\n    assert True\n")
    g("add", "."), g("commit", "-q", "-m", "another test named\n\nAlready built: #9 test_a.py::test_a")
    assert ct.already_built_files(tmp_path, base, "HEAD", ct.Config(test_globs=("test_*.py",))) == {"test_a.py"}


def test_already_built_must_pass_on_base_so_a_source_commit_before_it_cannot_skip_the_red(tmp_path):
    """Review of range 1: the source in one commit and the test in a test-only commit with the line skipped the red proof for a
    behaviour that was not on base. "Already built" means the test passes on base, so that is what is run."""
    g, base = _git_repo(tmp_path)
    (tmp_path / "mod.py").write_text("VALUE = 2\n")
    g("add", "."), g("commit", "-q", "-m", "the source")
    (tmp_path / "test_new.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 2\n")
    g("add", "."), g("commit", "-q", "-m", "the test\n\nAlready built: #9 test_new.py::test_v")
    r = ct.red_on_base(tmp_path, base, "HEAD", ["test_new.py"], timeout_s=120)
    assert not r["ok"] and "fails on base" in r["stderr_tail"]


def test_a_source_change_whose_every_test_is_excused_is_refused(tmp_path):
    """Review of range 1: source in one commit, `assert True` with the line in a test-only commit: it passes on base, so no test owed a red."""
    g, base = _git_repo(tmp_path)
    (tmp_path / "mod.py").write_text("VALUE = 2\n")
    g("add", "."), g("commit", "-q", "-m", "the source")
    (tmp_path / "test_x.py").write_text("def test_x():\n    assert True\n")
    g("add", "."), g("commit", "-q", "-m", "a test\n\nAlready built: #9 test_x.py::test_x")
    r = ct.red_on_base(tmp_path, base, "HEAD", ["test_x.py"], timeout_s=120)
    assert not r["ok"] and "owes a red" in r["stderr_tail"]


def test_a_source_change_with_another_test_that_goes_red_may_also_carry_an_excused_one(tmp_path):
    """One step can fix a thing and prove another was there."""
    g, base = _git_repo(tmp_path)
    (tmp_path / "test_have.py").write_text("def test_h():\n    assert True\n")
    g("add", "."), g("commit", "-q", "-m", "proof\n\nAlready built: #9 test_have.py::test_h")
    (tmp_path / "mod.py").write_text("VALUE = 2\n")
    (tmp_path / "test_new.py").write_text("import mod\ndef test_n():\n    assert mod.VALUE == 2\n")
    g("add", "."), g("commit", "-q", "-m", "the fix")
    assert ct.red_on_base(tmp_path, base, "HEAD", ["test_have.py", "test_new.py"], timeout_s=120)["ok"]


def test_an_already_built_test_that_goes_red_on_head_is_refused_by_the_green_run(tmp_path):
    """Passes on base, fails at head, through a change outside the red paths: the line excuses the red run, never the green one."""
    g, base = _git_repo(tmp_path)
    (tmp_path / "mod.py").write_text("VALUE = 2\n")
    g("add", "."), g("commit", "-q", "-m", "not a red path")
    (tmp_path / "test_x.py").write_text("import mod\ndef test_x():\n    assert mod.VALUE == 1\n")
    g("add", "."), g("commit", "-q", "-m", "proof\n\nAlready built: #9 test_x.py::test_x")
    r = ct.red_on_base(tmp_path, base, "HEAD", ["test_x.py"], ct.Config(red_paths=("src/",)), timeout_s=120)
    assert not r["ok"] and "Already built" not in r["stderr_tail"] and "owes a red" not in r["stderr_tail"], "stopped by the green run"


def test_a_commit_that_says_already_built_owes_no_red_on_base_but_its_test_still_runs_green(tmp_path):
    """A worker that found the behaviour in place commits the proving test with the line `Already built: #N <test>`: that
    test passes on base by design, so red-on-base does not refuse it; it still runs in the green run."""
    g, base = _git_repo(tmp_path)
    (tmp_path / "test_have.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 1\n")
    g("add", "."), g("commit", "-q", "-m", "docs: the value is there\n\nAlready built: #9 test_have.py::test_v")
    assert ct.red_on_base(tmp_path, base, "HEAD", ["test_have.py"], timeout_s=120)["ok"]
    # the same size and the same mtime second as the passing version: pytest's rewrite cache would serve the OLD bytecode
    # (stale pyc flake, 1 in ~3 runs before the fresh pycache prefix per rung)
    mtime = os.stat(tmp_path / "test_have.py").st_mtime
    (tmp_path / "test_have.py").write_text("import mod\ndef test_v():\n    assert mod.VALUE == 3\n")
    os.utime(tmp_path / "test_have.py", (mtime, mtime))
    g("add", "."), g("commit", "-q", "-m", "docs: broken\n\nAlready built: #9 test_have.py::test_v")
    assert not ct.red_on_base(tmp_path, base, "HEAD", ["test_have.py"], timeout_s=120)["ok"], "it fails on base, so the line is refused"
    (tmp_path / "test_other.py").write_text("def test_t():\n    assert True\n")
    g("add", "."), g("commit", "-q", "-m", "a plain commit")
    r = ct.red_on_base(tmp_path, base, "HEAD", ["test_other.py"], timeout_s=120)
    assert not r["ok"] and "NOT RED ON BASE" in r["stderr_tail"], "a test from a commit without the line still owes a red"


def test_the_ready_check_skips_its_guard_copy_with_no_guards_because_the_guards_rung_runs_them(tmp_path):
    """2026-11-02: the ready rung ran every guard again (60 s cap each) before the guards rung ran them from the pinned copy;
    under load one timed out and refused a green batch. The Builder passes --no-guards; a bare run still runs them."""
    import shutil

    repo = Path(__file__).resolve().parents[4]
    w = tmp_path / "w"
    (w / "scripts").mkdir(parents=True)
    shutil.copy(repo / "scripts" / "lane_ready_check.sh", w / "scripts" / "lane_ready_check.sh")
    (w / "pipeline" / "projects").mkdir(parents=True)
    (w / "pipeline" / "projects" / "fichero.toml").write_text('[repo]\npython_path = "."\n[[ladder]]\nname = "fast-guards"\nskip = []\n')
    for i in range(20):
        (w / "scripts" / f"check_ok{i:02}.py").write_text("pass\n")
    (w / "scripts" / "check_red.py").write_text("raise SystemExit('red guard')\n")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "C", "GIT_AUTHOR_EMAIL": "noreply@anthropic.com",
           "GIT_COMMITTER_NAME": "C", "GIT_COMMITTER_EMAIL": "noreply@anthropic.com"}
    def g(*a):
        subprocess.run(["git", "-C", str(w), *a], check=True, capture_output=True, env=env)
    g("init", "-q", "-b", "integration"), g("add", "."), g("commit", "-qm", "base #1234")
    g("update-ref", "refs/remotes/origin/integration", "HEAD")
    (w / "notes.txt").write_text("x\n")
    g("add", "."), g("commit", "-qm", "docs: a note #1234")
    run = lambda *a: subprocess.run(["bash", "scripts/lane_ready_check.sh", *a], cwd=w, capture_output=True, text=True, env=env)  # noqa: E731
    bare = run("HEAD")
    assert bare.returncode == 1 and "check_red.py" in bare.stdout, bare.stdout
    skipped = run("--no-guards", "HEAD")
    assert skipped.returncode == 0 and "READY" in skipped.stdout, skipped.stdout
    assert "--no-guards" in ct.load(repo).ready, "the Builder's ready rung passes it"


def test_the_green_run_is_one_pytest_per_package_so_two_tests_dirs_never_shadow_each_other(monkeypatch):
    """Real check 2026-11-02: fichero-server/tests and fichero-builder/tests in one pytest: `tests.test_queue_verb` not found."""
    seen = []
    monkeypatch.setattr(ct, "pytest_rung", lambda tree, fs, cfg, t: seen.append(fs) or {"argv": fs, "exit_code": 0, "ok": True, "seconds": 0,
                                                                                         "stdout_tail": "", "stderr_tail": ""})
    r = ct.green_runs(".", ["fichero-server/tests/a/test_x.py", "fichero-builder/tests/test_y.py", "fichero-server/tests/test_z.py"], (), ct.Config(), 5)
    assert seen == [["fichero-server/tests/a/test_x.py", "fichero-server/tests/test_z.py"], ["fichero-builder/tests/test_y.py"]]
    assert r["ok"] and len(r["runs"]) == 2


def _fake_ssh(tmp_path, monkeypatch):
    """An `ssh` that runs the remote script here (host and -o flags dropped), or fails as ssh does when `down` exists."""
    b = tmp_path / "bin"
    b.mkdir()
    (b / "ssh").write_text('#!/bin/sh\nwhile [ "$1" = "-o" ]; do shift 2; done\nshift\n'
                           f'[ -f {tmp_path}/down ] && {{ echo "ssh: connect to host imac: No route to host" >&2; exit 255; }}\nexec sh -c "$1"\n')
    (b / "ssh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}:{os.environ['PATH']}")


def test_a_remote_runner_runs_the_engine_pytest_there_and_an_unreachable_one_alerts_and_runs_it_here(tmp_path, monkeypatch):
    """[check].remote (manager 2026-11-02): the tree is shipped once, the same pytest runs in the copy with the remote's
    interpreter and the rung's env, and the copy is gone at the end; unreachable = one alert row, then the run here."""
    from fichero_builder import journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    _fake_ssh(tmp_path, monkeypatch)
    tree = tmp_path / "tree"
    tree.mkdir()
    g, _ = _git_repo(tree)
    (tree / "test_where.py").write_text("import os\ndef test_where():\n    assert os.environ['FICHERO_FEATURE_TIER'] == 'dev'\n"
                                        f"    open({str(tmp_path / 'ran')!r}, 'a').write(os.path.dirname(__file__) + '\\n')\n")
    (tmp_path / "gate").mkdir()
    cfg = ct.Config(test_env={"FICHERO_FEATURE_TIER": "dev"}, remote=f"imac:{tmp_path / 'gate'}", remote_python=sys.executable)
    r = ct.pytest_rung(tree, ["test_where.py"], cfg, timeout_s=120)
    assert r["ok"] and r["remote"] == "imac", r
    assert ct.pytest_rung(tree, ["test_where.py"], cfg, timeout_s=120)["ok"]
    where = (tmp_path / "ran").read_text().split()
    assert len(where) == 2 and where[0] == where[1] and where[0].startswith(str(tmp_path / "gate" / "run-")), "one copy, shipped once"
    ct._drop_remote(cfg)
    assert list((tmp_path / "gate").iterdir()) == [], "the copy is removed at the end"
    (tmp_path / "down").write_text("")
    r = ct.pytest_rung(tree, ["test_where.py"], cfg, timeout_s=120)
    assert r["ok"] and "remote" not in r, "unreachable: the same tests ran here"
    assert (tmp_path / "ran").read_text().split()[-1] == str(tree)
    (a,) = [x for x in journal.read() if x["event"] == "alert"]
    assert a["step"] == "remote" and "unreachable" in a["what"] and "No route" in a["what"]
    assert ct.pytest_rung(tree, ["test_where.py"], cfg, timeout_s=120)["ok"]
    assert len([x for x in journal.read() if x["event"] == "alert"]) == 1, "one alert per ladder, not one per run"
    ct._drop_remote(cfg)
