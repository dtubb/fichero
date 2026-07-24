"""Regression coverage for the Swift-to-Python gate harness (#4026)."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_cross_language_gate_terminates_spawned_engine_before_verify_python() -> None:
    gate = (
        ROOT / "fichero" / "fichero-tests" / "CrossLanguageGateTests.swift"
    ).read_text(encoding="utf-8")
    harness = (
        ROOT / "fichero" / "fichero-tests" / "EngineHarness.swift"
    ).read_text(encoding="utf-8")

    termination_call = "EngineHarness.terminateSpawnedEngineForNestedVerifier()"
    script_lookup = 'repo.appendingPathComponent("scripts/verify_python.sh")'
    process_launch = "try process.run()"

    assert termination_call in gate
    assert gate.index(script_lookup) < gate.index(termination_call) < gate.index(process_launch)
    assert "static func terminateSpawnedEngineForNestedVerifier()" in harness
    assert "process.waitUntilExit()" in harness
    assert "cached?.spawned == true" in harness
