"""Regression tests for verify_all platform wiring (#1939, #3960)."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_full_macos_gate_runs_fichero_ui_tests_scheme() -> None:
    verify_all = (ROOT / "scripts" / "verify_all.sh").read_text(encoding="utf-8")

    assert "xcodebuild macOS UI smoke tests" in verify_all
    # After the scheme rework there is no standalone "FicheroUITests" scheme; the
    # macOS UI smoke leg runs the UI-only `fichero` test plan (testTargets:
    # [FicheroUITests]) via the macOS app scheme. Guard that wiring.
    assert '-testPlan "fichero"' in verify_all


def test_full_ios_gate_is_generic_simulator_compile_only() -> None:
    verify_all = (ROOT / "scripts" / "verify_all.sh").read_text(encoding="utf-8")

    assert "xcodebuild iOS Simulator compile gate" in verify_all
    assert 'XCODE_SCHEME_IOS="Fichero (Dev Local iOS)"' in verify_all
    assert 'IOS_SIMULATOR_DESTINATION="generic/platform=iOS Simulator"' in verify_all
    assert 'VERIFY_ALL_DERIVED_ROOT="${VERIFY_ALL_DERIVED_ROOT:-build/verify-all-derived}"' in verify_all
    assert '-destination "${IOS_SIMULATOR_DESTINATION}"' in verify_all
    assert '-derivedDataPath "${VERIFY_ALL_DERIVED_ROOT}/ios-simulator"' in verify_all
    assert "simulator_udid" not in verify_all
    assert "xcrun" not in verify_all
