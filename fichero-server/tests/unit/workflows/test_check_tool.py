"""The check tool: argv lists with a cwd and a timeout each, typed results. (dev-workflows.tool.check, #6116.)"""

from __future__ import annotations

import sys

from fichero_server.workflows import check_tool as ct

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
    r = ct.guards(root)
    assert r["ok"] is False and "fewer than 20" in r["reason"] and r["results"] == []


def test_guards_run_each_one_skip_the_listed_and_name_the_red_one(tmp_path):
    root = _repo(tmp_path, 21, {1: "raise SystemExit(2)\n", 2: "raise SystemExit(2)\n"})
    r = ct.guards(root, skip={"check_g2"})
    names = [x["name"] for x in r["results"]]
    assert "check_g2" not in names and len(names) == 20
    assert r["ok"] is False and [x["name"] for x in r["results"] if not x["ok"]] == ["check_g1"]


def test_the_default_skip_list_is_the_tomls():
    assert {"check_coverage_ratchet", "check_docs_paths", "check_hang_ratchet"} <= ct.DEFAULT_SKIP and len(ct.DEFAULT_SKIP) == 15


def test_pytest_runs_named_files_with_the_fixed_env(tmp_path):
    (tmp_path / "test_a.py").write_text("import os\ndef test_a():\n    assert os.environ['FICHERO_FEATURE_TIER'] == 'dev'\n    assert os.environ['OMP_NUM_THREADS'] == '2'\n")
    r = ct.pytest_rung(tmp_path, ["test_a.py"], timeout_s=120)
    assert r["ok"], r


def test_pytest_with_no_files_is_red(tmp_path):
    assert ct.pytest_rung(tmp_path, [], timeout_s=5)["ok"] is False


def test_contract_current_is_skipped_unless_engine_source_changed(tmp_path):
    assert ct.contract_current(tmp_path, ["docs/x.md"]) == {"ok": True, "skipped": True, "results": []}
