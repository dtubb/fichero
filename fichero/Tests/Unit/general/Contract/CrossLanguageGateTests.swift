//
//  CrossLanguageGateTests.swift
//  FicheroTests
//
//  Makes ⌘U run the entire Python side of the gate. Shells out to the single
//  source-of-truth verify_python.sh and fails the Swift suite if any Python leg
//  (lint, unit, contract walk, backend smoke, CLI smoke, CLI contract) fails.
//  Skips (not fails) when the script/venv is absent, so a Swift-only checkout
//  still passes — mirroring EngineHarness.
//

import XCTest

@MainActor
final class CrossLanguageGateTests: XCTestCase {
    func test_python_gate_passes() throws {
        // Skip on Xcode Cloud — the Python gate (ruff + pytest + OpenAPI drift)
        // runs only on the Macs through scripts/verify_all.sh; there is no
        // GitHub CI. A fresh Xcode Cloud runner has no venv.
        let env = ProcessInfo.processInfo.environment
        if env["CI_XCODE_CLOUD"] != nil || env["XCODE_CLOUD_DEPLOYMENT_VARIANT"] != nil {
            throw XCTSkip("Python gate runs on the Macs only; skipped on Xcode Cloud.")
        }
        // Opt-in only: verify_python.sh is a 30-45 MINUTE sweep — nesting it
        // inside one XCTest blows the per-test watchdog and truncates the
        // whole XCTest leg. The serialized harness runs the Python gate as
        // its own leg; this cross-language wrapper exists for explicit
        // one-command verification runs.
        guard env["FICHERO_RUN_CROSS_LANGUAGE_GATE"] == "1" else {
            throw XCTSkip("Set FICHERO_RUN_CROSS_LANGUAGE_GATE=1 to nest the Python gate in XCTest.")
        }

        guard let repo = EngineHarness.repoRoot() else {
            throw XCTSkip("Repo root not found — skipping Python gate.")
        }
        let script = repo.appendingPathComponent("scripts/verify_python.sh")
        guard FileManager.default.fileExists(atPath: script.path) else {
            throw XCTSkip("verify_python.sh not found — skipping Python gate.")
        }
        EngineHarness.terminateSpawnedEngineForNestedVerifier()

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [script.path]
        process.currentDirectoryURL = repo
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        let output = String(data: data, encoding: .utf8) ?? "<no output>"
        add(XCTAttachment(string: output))  // visible in the test report

        XCTAssertEqual(
            process.terminationStatus, 0,
            "verify_python.sh failed — see attached output for the failing leg."
        )
    }
}
