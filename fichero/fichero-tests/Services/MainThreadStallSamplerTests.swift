//
//  MainThreadStallSamplerTests.swift
//  FicheroTests
//
//  The stall line is a WIRE FORMAT shared with check_hang_ratchet.py
//  --stall-log (regex: ^STALL \S+ (\d+(?:\.\d+)?)ms$). These tests pin the
//  Swift side of that contract; the Python side pins its own via --self-test.
//  Break either and the ratchet goes blind on self-measured sessions.
//

import Foundation
import Testing
@testable import Fichero

struct MainThreadStallSamplerTests {

    @Test("The stall line matches the ratchet's parser exactly")
    func stallLineMatchesTheSharedFormat() throws {
        let line = MainThreadStallSampler.stallLine(
            date: Date(timeIntervalSince1970: 1_754_654_400),
            duration: 0.1205
        )
        // ^STALL \S+ (\d+(?:\.\d+)?)ms$ — the Python regex, verbatim.
        let pattern = #"^STALL \S+ (\d+(?:\.\d+)?)ms$"#
        let range = line.range(of: pattern, options: .regularExpression)
        #expect(range != nil, "line does not match the shared format: \(line)")
        #expect(line.hasSuffix("120.5ms"))
    }

    @Test("The threshold is the Hangs instrument's own 33ms floor")
    func thresholdMatchesTheInstrument() {
        #expect(MainThreadStallSampler.stallThreshold == 0.033)
    }

    @Test("The sampler is armed at app launch, gated on the env flag")
    func startupHookExists() throws {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // drop the file → Services/
            .deletingLastPathComponent()  // fichero-tests/
            .deletingLastPathComponent()  // fichero/ (product dir)
            .deletingLastPathComponent()  // repo root
        let app = try String(
            contentsOf: repoRoot.appendingPathComponent("fichero/fichero/FicheroApp.swift"),
            encoding: .utf8
        )
        #expect(
            app.contains("MainThreadStallSampler.startIfEnabled()"),
            "the sampler must be armed in applicationDidFinishLaunching or every FICHERO_STALL_LOG=1 run silently measures nothing"
        )
    }
}
