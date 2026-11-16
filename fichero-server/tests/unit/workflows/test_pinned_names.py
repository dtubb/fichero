"""review 4 B6: pinned checks judge what pytest imports, by NAME anywhere, with git's -z paths."""

from __future__ import annotations

from fichero_server.workflows import check_tool as ct

from .test_check_tool import _project


def _violations(tmp_path, files: dict, mutate=None):
    work, g, base, pinned = _project(tmp_path)
    (work / "tests").mkdir()
    (work / "tests" / "conftest.py").write_text("x = 1\n")
    g("add", "."), g("commit", "-q", "-m", "tests")
    base = ct._lines(work, "rev-parse", "HEAD")[0]
    pinned2 = tmp_path / "pinned2"
    import subprocess
    subprocess.run(["git", "clone", "-q", str(work), str(pinned2)], check=True, capture_output=True)
    for name, body in files.items():
        p = work / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if body is None:
            p.symlink_to("/etc/passwd")
        else:
            p.write_text(body)
    if mutate:
        mutate(work)
    g("add", "-A"), g("commit", "-q", "-m", "attack")
    return ct.pinned_violations(work, base, "HEAD", ct.load(pinned2), pinned2)


def test_a_modified_existing_conftest_is_refused(tmp_path):
    assert any("conftest.py" in v for v in _violations(tmp_path, {"tests/conftest.py": "x = 2\n"}))


def test_a_non_ascii_path_is_not_a_quoting_escape(tmp_path):
    v = _violations(tmp_path, {"tests/é/conftest.py": "", ".claude/é.json": "{}"})
    assert any("conftest.py" in x for x in v) and any(".claude/" in x for x in v)


def test_pytest_ini_tox_setup_cfg_gitattributes_ruff_anywhere_are_pinned(tmp_path):
    names = ["tests/pytest.ini", "a/tox.ini", "b/setup.cfg", "c/.gitattributes", "d/ruff.toml"]
    v = _violations(tmp_path, dict.fromkeys(names, "x\n"))
    for n in names:
        assert any(n in x for x in v), (n, v)


def test_shadowing_and_plugin_names_and_symlinks_are_refused(tmp_path):
    files = {"pytest.py": "", "src/_pytest/__init__.py": "", "src/x-1.dist-info/entry_points.txt": "[pytest11]\n", "ok.txt": None}
    v = _violations(tmp_path, files)
    for n in ("pytest.py", "_pytest", "dist-info", "ok.txt"):
        assert any(n in x for x in v), (n, v)


def test_the_overlay_never_writes_through_a_symlink(tmp_path):
    work, g, base, pinned = _project(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    (work / "ci" / "new.py").symlink_to(victim)  # a worker-committed symlink at a path the pinned copy also holds
    g("add", "-A"), g("commit", "-q", "-m", "link")
    (pinned / "ci" / "new.py").write_text("pinned bytes\n")
    import subprocess
    subprocess.run(["git", "-C", str(pinned), "add", "ci/new.py"], check=True, capture_output=True)  # tracked = in the pinned set
    cfg = ct.load(pinned)
    tree = ct._scratch_tree(work, "HEAD", pinned, cfg)
    assert victim.read_text() == "keep"
    assert (ct.Path(tree) / "ci" / "new.py").read_text() == "pinned bytes\n" and not (ct.Path(tree) / "ci" / "new.py").is_symlink()


def test_pytest_runs_with_pinned_config_no_autoload_and_safe_path(tmp_path, monkeypatch):
    (tmp_path / "pytest.py").write_text("raise SystemExit(0)  # a shadow that would exit 0\n")
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert 1 == 2\n")
    cfg = ct.Config(pytest_plugins=("pytest_timeout",))
    argv = ct.pytest_argv(tmp_path, ["test_a.py"], cfg)
    assert "-c" not in argv or True
    assert "pytest_timeout" in argv[-1] and "-I" in argv  # the args ride inside the -I -c program
    assert ct._env(tmp_path, cfg, {})["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    # safe path is `-I` (it implies -P), never a PYTHONSAFEPATH env var a test's children would inherit (2026-11-05)
    seen = []
    real = ct._run
    monkeypatch.setattr(ct, "_run", lambda *a, **k: seen.append(a[5]) or {"ok": True})
    ct.pytest_rung(tmp_path, ["test_a.py"], cfg, timeout_s=60)
    assert seen == [None], "the rung adds no env var"
    monkeypatch.setattr(ct, "_run", real)
    assert not ct.pytest_rung(tmp_path, ["test_a.py"], cfg, timeout_s=60)["ok"]  # the shadow pytest.py did not win: -I keeps the cwd off sys.path


def test_a_guard_script_a_test_starts_still_imports_the_helper_beside_it(tmp_path):
    """2026-11-05: the pytest rung set PYTHONSAFEPATH=1, every child a test started inherited it, and a guard script run by a test lost
    its own dir from sys.path (`No module named _check_floor`, test_guardrails_scan_floor red in every safe-path rung)."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "_helper.py").write_text("OK = 0\n")
    (tmp_path / "scripts" / "check_x.py").write_text("import sys\nfrom _helper import OK\nsys.exit(OK)\n")
    (tmp_path / "test_guard.py").write_text(
        "import subprocess, sys\nfrom pathlib import Path\n\ndef test_the_guard_runs():\n"
        "    r = subprocess.run([sys.executable, str(Path(__file__).parent / 'scripts' / 'check_x.py')], capture_output=True, text=True)\n"
        "    assert r.returncode == 0, r.stderr\n")
    r = ct.pytest_rung(tmp_path, ["test_guard.py"], ct.Config(), timeout_s=120)
    assert r["ok"], r.get("stdout_tail", "")[-800:]


def test_a_rung_leaves_no_scratch_home_or_base_behind(tmp_path, monkeypatch):
    from fichero_server.workflows import check_tool as ct
    monkeypatch.setattr(ct.tempfile, "tempdir", str(tmp_path))
    (tmp_path / "r").mkdir()
    r = ct._run("x", ["/bin/echo", "hi"], tmp_path / "r", 10, ct.Config(base_path_env="BASE"))
    assert r["ok"]
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith("check-")] == []


def test_a_planted_stdlib_or_dependency_module_cannot_forge_a_green_pytest(tmp_path):  # review 5 N5
    """The tree's folders go on sys.path AFTER site-packages and the stdlib (python -I), so a src/gettext.py or
    src/pluggy.py that os._exit(0)s shadows nothing. (Code in the test process itself can always exit 0: that is the
    reviewer's wall, not the ladder's.)"""
    import sys
    (tmp_path / "src").mkdir()
    for mod in ("gettext", "pluggy", "argparse"):
        (tmp_path / "src" / f"{mod}.py").write_text("import os\nos._exit(0)\n")
    (tmp_path / "test_a.py").write_text("def test_red():\n    assert False\n")
    cfg = ct.Config(python=sys.executable, python_path=("src",))
    assert ct.pytest_rung(tmp_path, ["test_a.py"], cfg, timeout_s=120)["ok"] is False
    (tmp_path / "test_a.py").write_text("def test_green():\n    assert True\n")
    assert ct.pytest_rung(tmp_path, ["test_a.py"], cfg, timeout_s=120)["ok"] is True  # the control: it still runs


def test_pytest_tests_the_commit_not_an_editable_install(tmp_path):  # review 6 R1
    """An editable install's .pth adds a directory right after site-packages; the tree must come before it, or the
    commit's code is never imported and a green proves nothing."""
    import sys
    other = tmp_path / "other"
    other.mkdir()
    (other / "mod.py").write_text("def f():\n    return 1\n")  # the "install": returns what the test wants
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text("def f():\n    return 2\n")  # the commit under test
    (tmp_path / "test_a.py").write_text("import mod\n\n\ndef test_a():\n    assert mod.f() == 1\n")
    argv = ct.pytest_argv(tmp_path, ["test_a.py"], ct.Config(python=sys.executable, python_path=("src",)))
    # what a .pth does: put `other` on sys.path right after the site-packages directory, before anything we add later
    pth = (f"import sys; i = next(n for n, p in enumerate(sys.path) if p.endswith('site-packages')) + 1; "
           f"sys.path.insert(i, {str(other)!r})\n")
    argv[-1] = pth + argv[-1]
    r = ct.run_command("pytest", argv, tmp_path, 120, {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert r["ok"] is False and "assert 2 == 1" in r["stdout_tail"], r["stdout_tail"]  # the commit ran and failed
