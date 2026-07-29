"""Project-Python resolution for the verification gate (#4022)."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[4]
RESOLVER = ROOT / "scripts" / "find_project_python.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    path.mkdir()
    _run("git", "-C", str(path), "init")
    (path / "tracked").write_text("fixture\n", encoding="utf-8")
    _run("git", "-C", str(path), "add", "tracked")
    _run(
        "git",
        "-C",
        str(path),
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "fixture",
    )


def _add_fake_python(repo: Path) -> Path:
    python = repo / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(python.stat().st_mode | 0o111)
    return python


def test_resolves_main_checkout_venv(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    python = _add_fake_python(repo)

    result = _run(str(RESOLVER), str(repo))

    assert result.returncode == 0
    assert result.stdout.strip() == str(python)


def test_resolves_main_venv_from_linked_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    _init_repo(repo)
    python = _add_fake_python(repo)
    result = _run("git", "-C", str(repo), "worktree", "add", "-b", "worker", str(worktree))
    assert result.returncode == 0, result.stderr

    result = _run(str(RESOLVER), str(worktree))

    assert result.returncode == 0
    assert result.stdout.strip() == str(python)


def test_fails_closed_without_project_venv(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    result = _run(str(RESOLVER), str(repo))

    assert result.returncode == 2
    assert "project Python not found" in result.stderr


def test_verify_all_preserves_explicit_override() -> None:
    verify_all = (ROOT / "scripts" / "verify_all.sh").read_text(encoding="utf-8")

    assert 'if [[ -n "${PYTHON_BIN:-}" ]]' in verify_all
    assert 'PYTHON_BIN="$(scripts/find_project_python.sh .)"' in verify_all
    assert 'PYTHON_BIN="python3"' not in verify_all
