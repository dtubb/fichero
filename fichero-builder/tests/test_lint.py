"""The ready check's lint ratchet (manager 2026-11-02): a touched file that already broke a rule on base passes unless that
rule's count grows; a new file is refused on any finding. Real ruff and swiftlint, skipped where absent."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "fichero_builder" / "lint.py"


def _repo(tmp_path, name, base_text):
    def g(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    # the repo's own rules: with no ruff.toml ruff's built-in set applies, which ruff 0.16 widened (I001), so the owner's
    # 0.16.6 and the jail's 0.15.8 disagreed on this test (red on base 2026-11-03); the real ratchet always runs under it
    shutil.copy(Path(__file__).resolve().parents[2] / "ruff.toml", tmp_path / "ruff.toml")
    (tmp_path / name).write_text(base_text)
    g("add", "."), g("commit", "-qm", "base")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()


def _run(tmp_path, tool, base, *files):
    return subprocess.run([sys.executable, str(SCRIPT), "--tool", tool, "--base", base, *files], cwd=tmp_path, capture_output=True, text=True)


@pytest.mark.skipif(not shutil.which("ruff"), reason="ruff not installed")
def test_ruff_refuses_only_a_rule_that_grows_and_any_finding_in_a_new_file(tmp_path):
    base = _repo(tmp_path, "m.py", "import os\nimport sys\n")  # two F401 on base
    (tmp_path / "m.py").write_text("import os\nimport sys\nX = 1\n")
    assert _run(tmp_path, "ruff", base, "m.py").returncode == 0, "the same two findings: no worse"
    (tmp_path / "m.py").write_text("import os\nimport sys\nimport json\n")
    r = _run(tmp_path, "ruff", base, "m.py")
    assert r.returncode == 1 and "F401" in r.stdout and "3 on head, 2 on base" in r.stdout
    (tmp_path / "new.py").write_text("import os\n")
    r = _run(tmp_path, "ruff", base, "new.py")
    assert r.returncode == 1 and "new.py" in r.stdout


@pytest.mark.skipif(not shutil.which("swiftlint"), reason="swiftlint not installed")
def test_swiftlint_passes_a_long_file_that_got_shorter_and_refuses_a_new_long_file(tmp_path):
    long = "".join(f"let v{i} = {i}\n" for i in range(1, 460))
    base = _repo(tmp_path, "Store.swift", long)  # over file_length (400) on base
    (tmp_path / "Store.swift").write_text("".join(f"let v{i} = {i}\n" for i in range(1, 430)))
    r = _run(tmp_path, "swiftlint", base, "Store.swift")
    assert r.returncode == 0, r.stdout + r.stderr
    (tmp_path / "Fresh.swift").write_text(long)
    r = _run(tmp_path, "swiftlint", base, "Fresh.swift")
    assert r.returncode == 1 and "file_length" in r.stdout


def test_a_linter_that_fails_or_prints_nothing_is_a_refusal_never_zero_findings(tmp_path, monkeypatch):
    """Review 2026-11-02: ruff --exit-zero with empty stdout was read as '[]' and a config error passed the gate."""
    import types

    import pytest

    from fichero_builder import lint
    monkeypatch.setattr(lint.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout="", stderr="config error", returncode=2))
    with pytest.raises(lint.LintError, match="no JSON"):
        lint._lint("ruff", "x.py", None)
    monkeypatch.setattr(lint.sys, "argv", ["lint.py", "--tool", "ruff", "--base", "HEAD", "x.py"])
    assert lint.main() == 1, "the CLI refuses too"


def test_lint_runs_on_the_python_3_9_the_jails_python3_is():
    """The jail's PATH starts at the Command Line Tools: `python3 -I lint.py` there is 3.9.6, where `str | None` in a def raised
    TypeError and failed every ready check that touched a .py file (2026-11-02)."""
    old = [p for p in ("/Library/Developer/CommandLineTools/usr/bin/python3", "/usr/bin/python3") if shutil.which(p)
           and subprocess.run([p, "-c", "import sys; sys.exit(sys.version_info >= (3, 10))"]).returncode == 0]
    if not old:
        pytest.skip("no python older than 3.10 here")
    r = subprocess.run([old[0], "-I", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_a_module_planted_beside_lint_py_is_not_imported_by_it(tmp_path):
    """Review 2026-11-02: python < 3.11 puts the script's folder first even under -I; the worker edits that folder, so a planted
    json.py must not run inside the judge. Every python here runs it: the planted file fails the run if it is ever imported."""
    import shutil as sh
    sh.copy(SCRIPT, tmp_path / "lint.py")
    (tmp_path / "json.py").write_text("raise SystemExit('planted json.py was imported')\n")
    (tmp_path / "__future__.py").write_text("raise SystemExit('planted __future__.py was imported')\n")
    (tmp_path / "subprocess.py").write_text("raise SystemExit('planted subprocess.py was imported')\n")
    pys = [sys.executable] + [p for p in ("/Library/Developer/CommandLineTools/usr/bin/python3", "/usr/bin/python3") if shutil.which(p)]
    for py in pys:
        r = subprocess.run([py, "-I", str(tmp_path / "lint.py"), "--help"], capture_output=True, text=True)
        assert r.returncode == 0 and "planted" not in r.stdout + r.stderr, (py, r.stderr)
