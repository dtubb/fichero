"""The check tool: argv lists with a cwd and a timeout each, typed results. (dev-workflows.tool.check, #6116.)"""

from __future__ import annotations

import sys

from pathlib import Path

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


def test_fichero_is_the_first_project_in_its_own_harness_toml():
    cfg = ct.load(REPO)
    assert {"check_coverage_ratchet", "check_docs_paths", "check_hang_ratchet"} <= cfg.guard_skip and len(cfg.guard_skip) == 15
    assert cfg.min_guards == 20 and cfg.guard_glob == "scripts/check_*.py" and cfg.ready == ("scripts/lane_ready_check.sh", "HEAD")
    assert ct.load(REPO / "no-such-dir") == ct.Config()  # no harness.toml = no project rules, nothing hardcoded


def test_pytest_runs_named_files_with_the_fixed_env(tmp_path):
    (tmp_path / "test_a.py").write_text("import os\ndef test_a():\n    assert os.environ['FICHERO_FEATURE_TIER'] == 'dev'\n    assert os.environ['OMP_NUM_THREADS'] == '2'\n")
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


def _project(tmp_path):
    """A throwaway project: its own harness.toml, one good guard, one skipped bad guard; plus a pinned clone of it."""
    work = tmp_path / "work"
    work.mkdir()
    g, _ = _git_repo(work)
    (work / "ci").mkdir()
    (work / "ci" / "lint_ok.py").write_text("pass\n")
    (work / "ci" / "lint_bad.py").write_text("raise SystemExit(7)\n")
    (work / "harness.toml").write_text(
        '[check]\nready = ["python3", "-c", "print(1)"]\nguard_glob = "ci/lint_*.py"\nmin_guards = 2\n'
        'guard_skip = ["lint_bad"]\ncheck_paths = ["ci/", "harness.toml"]\nmax_files = 10\n[check.test_env]\nTINY_PROJECT = "yes"\n')
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
    r = ct.run_ladder(work, base, "HEAD", pinned)
    assert r["ok"], r
    assert [x["name"] for x in r["rungs"]] == ["pinned-checks", "ready", "diff-bound", "red-on-base", "guards", "contract-current"]


def test_a_worker_cannot_change_the_checks_it_is_judged_by(tmp_path):
    """The worker edits a guard, the config, or .claude/: needs-maintainer, nothing else runs."""
    work, g, base, pinned = _project(tmp_path)
    (work / "ci" / "lint_ok.py").write_text("raise SystemExit(0)  # edited by the worker\n")
    g("add", "."), g("commit", "-q", "-m", "edit guard")
    r = ct.run_ladder(work, base, "HEAD", pinned)
    assert not r["ok"] and r["failed"] == "pinned-checks" and [x["name"] for x in r["rungs"]] == ["pinned-checks"]
    assert "ci/lint_ok.py" in r["rungs"][0]["stderr_tail"] and "needs-maintainer" in r["rungs"][0]["stderr_tail"]
    g("reset", "-q", "--hard", base)
    (work / ".claude").mkdir()
    (work / ".claude" / "settings.json").write_text("{}")
    (work / "sitecustomize.py").write_text("print('hi')\n")
    g("add", "."), g("commit", "-q", "-m", "hooks")
    r = ct.run_ladder(work, base, "HEAD", pinned)
    assert r["failed"] == "pinned-checks" and ".claude/settings.json" in r["rungs"][0]["stderr_tail"] and "sitecustomize.py" in r["rungs"][0]["stderr_tail"]


def test_the_ladder_runs_the_pinned_guards_not_the_workers_copies(tmp_path):
    """A guard the worker ADDS runs (allowed); the pinned config still skips lint_bad, and the pinned bytes win."""
    work, g, base, pinned = _project(tmp_path)
    (work / "ci" / "lint_new.py").write_text("raise SystemExit(3)\n")
    (work / "mod.py").write_text("VALUE = 2\n")
    (work / "test_mod.py").write_text("import os, mod\ndef test_v():\n    assert mod.VALUE == 2 and os.environ['TINY_PROJECT'] == 'yes'\n")
    g("add", "."), g("commit", "-q", "-m", "add a failing guard")
    r = ct.run_ladder(work, base, "HEAD", pinned)
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
    r = ct.run_ladder(work, base, "HEAD", pinned)
    assert r["failed"] == "pinned-checks" and "test_old.py" in r["rungs"][0]["stderr_tail"]


def test_a_worker_cannot_rewrite_its_own_acceptance(tmp_path):
    """The item's own spec bullet may flip its status tag or gain (#N); any other change is needs-maintainer."""
    work, g, base0, pinned = _project(tmp_path)
    (work / "specs").mkdir()
    spec = work / "specs" / "s.md"
    spec.write_text("- `demo.item.one` [PROPOSED] — it does the thing, and ten more.\n- `demo.other` [OK] — unrelated.\n")
    g("add", "."), g("commit", "-q", "-m", "spec")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    cfg = ct.Config(spec_dir="specs")
    spec.write_text("- `demo.item.one` [OK] (#12) — it does the thing, and ten more.\n- `demo.other` [OK] — unrelated.\n")
    g("commit", "-qam", "tag flip")
    assert ct.acceptance_changed(work, base, "HEAD", cfg, ["demo.item.one"]) == []
    spec.write_text("- `demo.item.one` [OK] — it does less.\n- `demo.other` [OK] — unrelated.\n")
    g("commit", "-qam", "rewrite")
    hits = ct.acceptance_changed(work, base, "HEAD", cfg, ["demo.item.one"])
    assert hits and "specs/s.md" in hits[0]
    assert ct.acceptance_changed(work, base, "HEAD", cfg, ["demo.other"]) == []  # only the item's own ids are protected
