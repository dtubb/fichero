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


def test_verify_suite_in_a_subprocess_imports_the_candidates_engine_with_no_pythonpath(tmp_path):
    """The verify-all suite rung end to end: a fresh interpreter, PYTHONPATH unset, an interpreter with no `eng6726` installed, a
    small candidate git tree whose harness.toml names its engine's src."""
    import os
    import subprocess
    t = tmp_path / "t"
    (t / "pkg" / "src" / "eng6726").mkdir(parents=True)
    (t / "pkg" / "src" / "eng6726" / "__init__.py").write_text("WHO = 1\n")
    (t / "pkg" / "tests").mkdir()
    (t / "pkg" / "tests" / "test_a.py").write_text("def test_a():\n    import eng6726\n")
    (t / "harness.toml").write_text(f'[check]\npython = "{sys.executable}"\npython_path = ["pkg/src"]\nguard_glob = ""\nmin_guards = 0\n')
    g = lambda *a: subprocess.run(["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)  # noqa: E731
    g("init", "-q", "-b", "main"), g("add", "-A"), g("commit", "-qm", "1")
    pkg = os.path.dirname(os.path.dirname(check_tool.__file__))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"} | {"FICHERO_BUILDER_STATE": str(tmp_path / "state"), "PYTHONPATH": pkg}
    code = "import sys, json; from fichero_builder import verify; print(json.dumps(verify.verify(sys.argv[1], jail_required=False)['parts']['suite']))"
    p = subprocess.run([sys.executable, "-c", code, str(t)], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert '"ok": true' in p.stdout, p.stdout + p.stderr
