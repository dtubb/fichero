"""Regression tests for verify_all GUI smoke wiring (#1939)."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_full_macos_gate_runs_fichero_ui_tests_scheme() -> None:
    verify_all = (ROOT / "scripts" / "verify_all.sh").read_text(encoding="utf-8")

    assert "xcodebuild macOS UI smoke tests" in verify_all
    assert '-scheme "FicheroUITests"' in verify_all
