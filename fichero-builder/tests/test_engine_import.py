"""#6726 item 3: a venv without the engine installed (setup_venv.sh --no-install-project) still imports the CANDIDATE tree's engine
in every pytest the builder runs: the tree's [check].python_path is on sys.path and in the child's PYTHONPATH."""
from __future__ import annotations

import sys

import pytest

from fichero_builder import check_tool

ENGINE = "engine_not_installed_6726"


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "pkg" / "src" / ENGINE).mkdir(parents=True)
    (tmp_path / "pkg" / "src" / ENGINE / "__init__.py").write_text("WHO = 'candidate'\n")
    (tmp_path / "pkg" / "tests").mkdir()
    (tmp_path / "pkg" / "tests" / "test_it.py").write_text(
        f"import subprocess, sys\n\ndef test_imports_the_candidates_engine():\n    import {ENGINE}\n    assert {ENGINE}.WHO == 'candidate'\n\n"
        f"def test_a_child_python_finds_it_too():\n    subprocess.run([sys.executable, '-c', 'import {ENGINE}'], check=True)\n")
    assert subprocess_find(ENGINE) is None  # the interpreter running the tests has no such engine installed
    return tmp_path


def subprocess_find(name):
    import importlib.util
    return importlib.util.find_spec(name)


def cfg():
    return check_tool.Config(python=sys.executable, python_path=("pkg/src",), pytest_plugins=())


def test_the_engine_shaped_pytest_imports_the_candidates_engine(tree):
    r = check_tool.pytest_rung(tree, ["pkg/tests/test_it.py"], cfg(), 120)
    assert r["ok"], r.get("stdout_tail", "") + r.get("stderr_tail", "")


def test_a_whole_tests_run_imports_the_candidates_engine(tree):
    r = check_tool.whole_tests_rung(tree, "pkg/tests", cfg(), 120)
    assert r["ok"], r.get("stdout_tail", "") + r.get("stderr_tail", "")


def test_a_remote_run_puts_the_shipped_trees_engine_on_the_path_not_the_local_trees(tree, monkeypatch):
    seen = []
    monkeypatch.setattr(check_tool, "_ship", lambda root, c, remote="": "/gate/run1/tree")
    monkeypatch.setattr(check_tool, "run_command", lambda name, argv, *a, **k: seen.append(argv[-1]) or {"exit_code": 0, "ok": True})
    monkeypatch.setattr(check_tool, "_remote_back", lambda r: None)
    c = check_tool.Config(python=sys.executable, python_path=("pkg/src",), remote="box:/gate", pytest_plugins=())
    argv = check_tool.pytest_argv(tree, ["pkg/tests/test_it.py"], c)
    check_tool._remote_run("pytest", argv, tree, 60, c, None, None)
    assert "/gate/run1/tree/pkg/src" in seen[0] and str(tree) not in seen[0] and "PYTHONPATH=/gate/run1/tree/pkg/src" in seen[0]
