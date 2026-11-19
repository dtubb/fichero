"""`contract.release-engine-reports-its-release` (#6723): a built engine with a release stamp reports the release
version and build; with none, today's behaviour; the contract version is reported separately."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fichero_server.api import main as api_main

REPO = Path(__file__).resolve().parents[4]
STAMPER = REPO / "scripts" / "stamp_release_into_engine.sh"


def _built_engine(monkeypatch, tmp_path: Path) -> Path:
    """No pyproject beside the package (a built engine) and a stamp path inside a tmp package dir."""
    monkeypatch.setattr(api_main, "SOURCE_PYPROJECT", tmp_path / "no-pyproject.toml")
    stamp = tmp_path / "release-stamp.txt"
    monkeypatch.setattr(api_main, "RELEASE_STAMP", stamp)
    monkeypatch.setattr(api_main, "package_version", lambda name: "2026.10.30")
    return stamp


def test_a_stamped_file_wins_over_the_distribution_version(monkeypatch, tmp_path):
    stamp = _built_engine(monkeypatch, tmp_path)
    stamp.write_text("2026.11.18 29\n")
    assert api_main._resolve_engine_version() == "2026.11.18 (29)"


def test_no_stamp_is_todays_behaviour(monkeypatch, tmp_path):
    _built_engine(monkeypatch, tmp_path)
    assert api_main._resolve_engine_version() == "2026.10.30"


def test_a_malformed_stamp_fails_loudly(monkeypatch, tmp_path):
    import pytest

    stamp = _built_engine(monkeypatch, tmp_path)
    stamp.write_text("2026.11.18\n")
    with pytest.raises(RuntimeError, match="release-stamp"):
        api_main._resolve_engine_version()


def test_the_contract_version_is_unchanged_by_a_stamp(monkeypatch, tmp_path):
    from fichero_server.api.contract_identity_generated import CONTRACT_VERSION

    _built_engine(monkeypatch, tmp_path).write_text("2026.11.18 29\n")
    assert api_main._resolve_contract_identity().version == CONTRACT_VERSION


def test_the_bug_report_names_both_versions():
    from fichero_server.api.routes.system.bug_report import environment
    from fichero_server.api.contract_identity_generated import CONTRACT_VERSION

    env = environment()
    assert env["contract_version"] == CONTRACT_VERSION
    assert env["engine_version"] == api_main._ENGINE_VERSION


def test_a_release_stage_cannot_report_a_version_other_than_the_releases(monkeypatch, tmp_path):
    """Run the stamping step on a staged copy and resolve the version against it: 2026.11.18 (29)."""
    pkg = tmp_path / "Fichero Server.app" / "Contents" / "Resources" / "app" / "fichero_server"
    pkg.mkdir(parents=True)
    subprocess.run([str(STAMPER), str(tmp_path / "Fichero Server.app"), "2026.11.18", "29"], check=True, capture_output=True)
    monkeypatch.setattr(api_main, "SOURCE_PYPROJECT", tmp_path / "no-pyproject.toml")
    monkeypatch.setattr(api_main, "RELEASE_STAMP", pkg / "release-stamp.txt")
    monkeypatch.setattr(api_main, "package_version", lambda name: "2026.10.30")
    assert api_main._resolve_engine_version() == "2026.11.18 (29)"


def test_the_stamper_refuses_a_bundle_with_no_engine_package(tmp_path):
    done = subprocess.run([str(STAMPER), str(tmp_path), "2026.11.18", "29"], capture_output=True, text=True)
    assert done.returncode != 0 and "no fichero_server package" in done.stderr
