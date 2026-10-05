"""The dev launcher refuses a venv that cannot run the engine's jobs (#5493).

WHY: start_fichero_server.sh picked a stale per-worktree fichero-server/.venv over the canonical
~/code/fichero/.venv. It lacked kraken, spaCy + es_core_news_sm and iso639, so the engine started,
looked healthy, and failed every recipe run. The launcher now runs dev_venv_preflight.py with the
Python it picked and stops, naming what is missing and the fixes. These tests run that checker
directly (never the launcher: it would replace the running dev engine on the shared socket).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
_PREFLIGHT = _SCRIPTS / "dev_venv_preflight.py"
_ABSENT = "fichero-no-such-distribution-5493"

sys.path.insert(0, str(_SCRIPTS))
import dev_venv_preflight  # noqa: E402


def _run(requirements: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_PREFLIGHT), str(requirements), *extra],
        capture_output=True, text=True, timeout=60,
    )


def test_a_missing_requirement_stops_the_launch_naming_it_and_the_fixes(tmp_path):
    """The #5493 venv: exit non-zero, the venv it picked, what is missing, both fixes."""
    reqs = tmp_path / "requirements.txt"
    reqs.write_text(f"# a header\npytest  # present\n{_ABSENT}>=1.0\n")

    result = _run(reqs)

    assert result.returncode == 1
    assert f"Missing: {_ABSENT}\n" in result.stderr
    assert sys.executable in result.stderr
    assert "FICHERO_PYTHON_BIN=~/code/fichero/.venv/bin/python" in result.stderr
    assert f"uv pip install --python {sys.executable} -r {reqs}" in result.stderr


def test_a_missing_dev_only_runtime_is_named_with_its_own_install(tmp_path):
    """kraken is not in requirements.txt, so `-r` alone would not bring it back: say how."""
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("pytest\n")

    result = _run(reqs, _ABSENT)

    assert result.returncode == 1
    assert f"uv pip install --python {sys.executable} {_ABSENT}" in result.stderr


def test_a_complete_venv_passes_silently(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("pytest\n")
    result = _run(reqs, "pytest")
    assert (result.returncode, result.stderr) == (0, "")


@pytest.mark.parametrize(
    ("line", "name"),
    [
        ("fastapi", "fastapi"),
        ("uvicorn[standard]", "uvicorn"),
        ("starlette>=1.3.1", "starlette"),
        ("mcp>=1.28.1,<2", "mcp"),
        ("iso639-lang  # ISO 639-3 language names", "iso639-lang"),
        ("es_core_news_sm @ https://github.com/explosion/spacy-models/releases/download/"
         "es_core_news_sm-3.8.0/es_core_news_sm-3.8.0-py3-none-any.whl", "es_core_news_sm"),
        ("https://example.org/wheels/foo_bar-1.0-py3-none-any.whl", "foo_bar"),
        ("git+https://example.org/repo.git#egg=baz", "baz"),
        ('pyobjc-framework-Vision; sys_platform == "darwin"', "pyobjc-framework-Vision"),
        ("# --- a section ---", None),
        ("", None),
        ("-r other.txt", None),
    ],
)
def test_requirement_lines_resolve_to_their_distribution(line, name):
    assert dev_venv_preflight.distribution_name(line) == name


def test_the_real_requirements_file_names_the_runtimes_of_5493():
    """The generated union must still carry what the incident lacked, or the check would miss it."""
    names = dev_venv_preflight.required_distributions(_SCRIPTS.parent / "requirements.txt", ["kraken"])
    assert {"iso639-lang", "spacy", "es_core_news_sm", "en_core_web_sm", "kraken"} <= set(names)


def test_the_launcher_runs_the_check_with_the_python_it_picked_unless_ci_skips_it():
    """Wiring only: the check above is the behaviour; this pins that the launcher calls it."""
    launcher = (_SCRIPTS / "start_fichero_server.sh").read_text()
    call = '"$PYTHON_BIN" "$SCRIPT_DIR/dev_venv_preflight.py" "$API_ROOT/requirements.txt" kraken'
    assert call in launcher
    assert launcher.index("PYTHON_BIN=\"python3\"") < launcher.index(call) < launcher.index("start_backend.py")
    assert launcher.index(call) < launcher.index("exec env PYTHONPATH")
    assert 'FICHERO_SKIP_VENV_CHECK:-}" != "1"' in launcher
