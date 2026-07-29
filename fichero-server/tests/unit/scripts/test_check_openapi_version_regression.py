"""Guard against an OpenAPI sync that walks info.version backwards (#4199).

The live incident: `sync_openapi_schema.sh` resolved its interpreter to a
partially-installed `fichero-server/.venv`, so the exported spec carried
`0.1.0.dev1` instead of `2026.7.20b1`, and the sync rewrote `info.version`
across all four committed copies. It was caught by luck.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "fichero-server" / "scripts" / "check_openapi_version_regression.py"


def _load():
    spec = importlib.util.spec_from_file_location("_openapi_version_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


def _spec_file(tmp_path: Path, name: str, version: str | None) -> Path:
    payload: dict = {"openapi": "3.1.0", "paths": {}}
    if version is not None:
        payload["info"] = {"title": "Fichero", "version": version}
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def test_the_live_incident_is_a_regression():
    assert guard.is_regression("2026.7.20b1", "0.1.0.dev1") is True


@pytest.mark.parametrize(
    ("previous", "current"),
    [
        ("2026.7.20b1", "2026.7.21b1"),  # forward patch
        ("2026.7.20b1", "2027.1.1"),  # forward year
        ("0.1.0.dev1", "2026.7.20b1"),  # recovering from a poisoned spec
    ],
)
def test_forward_moves_are_allowed(previous, current):
    assert guard.is_regression(previous, current) is False


def test_identical_version_is_not_a_regression():
    """The overwhelmingly common case: a schema change with no version bump."""
    assert guard.is_regression("2026.7.20b1", "2026.7.20b1") is False


def test_missing_version_never_blocks():
    """A first-ever export has nothing to compare against — must not abort."""
    assert guard.is_regression(None, "2026.7.20b1") is False
    assert guard.is_regression("2026.7.20b1", None) is False


def test_prerelease_ordering_within_one_release():
    """Ordering that only `packaging` gets right; skipped if it is absent."""
    pytest.importorskip("packaging")
    assert guard.is_regression("2026.7.20b2", "2026.7.20b1") is True
    assert guard.is_regression("2026.7.20b1", "2026.7.20b2") is False


def test_unparseable_versions_do_not_crash():
    assert guard.is_regression("not-a-version", "also-not") is False


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------


def test_read_version_extracts_info_version(tmp_path):
    assert guard.read_version(_spec_file(tmp_path, "a.json", "2026.7.20b1")) == "2026.7.20b1"


def test_read_version_tolerates_missing_and_corrupt_files(tmp_path):
    assert guard.read_version(tmp_path / "absent.json") is None
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json")
    assert guard.read_version(corrupt) is None
    assert guard.read_version(_spec_file(tmp_path, "b.json", None)) is None


# ---------------------------------------------------------------------------
# CLI contract (what the shell script depends on)
# ---------------------------------------------------------------------------


def _run(previous: Path, current: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--previous", str(previous), "--current", str(current)],
        capture_output=True,
        text=True,
    )


def test_cli_exits_nonzero_and_names_both_versions_on_regression(tmp_path):
    result = _run(
        _spec_file(tmp_path, "prev.json", "2026.7.20b1"),
        _spec_file(tmp_path, "new.json", "0.1.0.dev1"),
    )

    assert result.returncode == 1
    assert "2026.7.20b1" in result.stderr and "0.1.0.dev1" in result.stderr
    # The remedy must be in the message; rediscovering it is the whole bug.
    assert "FICHERO_PYTHON_BIN" in result.stderr


def test_cli_exits_zero_on_forward_bump(tmp_path):
    result = _run(
        _spec_file(tmp_path, "prev.json", "2026.7.20b1"),
        _spec_file(tmp_path, "new.json", "2026.7.21b1"),
    )

    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# sync_openapi_schema.sh wiring
#
# Asserting the guard in isolation is not enough: the bug was that the sync
# rewrote committed files. These run the REAL shell script against a throwaway
# tree, so they prove the abort actually stops propagation.
# ---------------------------------------------------------------------------

SYNC = ROOT / "fichero-server" / "scripts" / "sync_openapi_schema.sh"


def _fake_tree(tmp_path: Path, exported_version: str) -> tuple[Path, Path]:
    """A minimal REPO_ROOT/API_ROOT with stubbed exporter + CLI generator."""
    api_root = tmp_path / "fichero-server"
    (api_root / "scripts").mkdir(parents=True)
    (api_root / "tests" / "contracts").mkdir(parents=True)
    (tmp_path / "docs" / "contributor" / "api-reference").mkdir(parents=True)

    for name in ("sync_openapi_schema.sh", "check_openapi_version_regression.py"):
        target = api_root / "scripts" / name
        target.write_text((ROOT / "fichero-server" / "scripts" / name).read_text())
        target.chmod(0o755)

    spec = api_root / "tests" / "contracts" / "openapi.json"
    spec.write_text(json.dumps({"info": {"title": "Fichero", "version": "2026.7.20b1"}}))

    (api_root / "scripts" / "export_openapi_schema.py").write_text(
        "import json, pathlib\n"
        f"p = pathlib.Path(r'{spec}')\n"
        f"p.write_text(json.dumps({{'info': {{'version': '{exported_version}'}}}}))\n"
    )
    # Writes a marker so the test can prove it never ran on the abort path.
    (api_root / "scripts" / "generate_openapi_cli.py").write_text(
        "import pathlib\n"
        f"pathlib.Path(r'{tmp_path / 'cli-generator-ran'}').write_text('yes')\n"
    )
    return api_root, spec


def test_sync_aborts_and_restores_when_export_walks_the_version_back(tmp_path):
    api_root, spec = _fake_tree(tmp_path, exported_version="0.1.0.dev1")
    original = spec.read_text()

    result = subprocess.run(
        ["bash", str(api_root / "scripts" / "sync_openapi_schema.sh")],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "FICHERO_PYTHON_BIN": sys.executable},
    )

    assert result.returncode == 1, result.stdout + result.stderr
    # The committed spec must be byte-identical to before the failed sync.
    assert spec.read_text() == original
    # And nothing downstream may have run.
    assert not (tmp_path / "cli-generator-ran").exists()
    assert not (tmp_path / "docs" / "contributor" / "api-reference" / "openapi.json").exists()


def test_sync_proceeds_on_a_forward_bump(tmp_path):
    api_root, spec = _fake_tree(tmp_path, exported_version="2026.7.21b1")

    result = subprocess.run(
        ["bash", str(api_root / "scripts" / "sync_openapi_schema.sh")],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "FICHERO_PYTHON_BIN": sys.executable},
    )

    assert json.loads(spec.read_text())["info"]["version"] == "2026.7.21b1"
    assert (tmp_path / "cli-generator-ran").exists(), result.stdout + result.stderr


def test_help_documents_the_interpreter_requirement():
    result = subprocess.run(
        ["bash", str(SYNC), "--help"], capture_output=True, text=True
    )

    assert result.returncode == 0
    assert "FICHERO_PYTHON_BIN" in result.stdout
