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
        // Skip on Xcode Cloud — the Python gate runs in GitHub Actions Linux
        // (.github/workflows/ci.yml: ruff + pytest + OpenAPI drift) where pip
        // deps and openapi.json regen are cheap. Running them inside the Swift
        // suite on a fresh Mac runner would need a 5-10 min pre-action to set
        // up the venv, and we already have the Python side covered elsewhere.
        let env = ProcessInfo.processInfo.environment
        if env["CI_XCODE_CLOUD"] != nil || env["XCODE_CLOUD_DEPLOYMENT_VARIANT"] != nil {
            throw XCTSkip("Python gate runs in GitHub Actions Linux CI; skipped on Xcode Cloud.")
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
