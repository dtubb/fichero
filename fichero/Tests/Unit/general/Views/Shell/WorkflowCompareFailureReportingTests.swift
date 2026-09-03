@testable import Fichero
import Foundation
import Testing

/// Per-model failure reporting (Daniel, 2026-09-02): one model returning
/// "Vision LLM returned empty response … after retry" surfaced as a single
/// opaque global error, naming neither the model that failed nor the three
/// that succeeded. A comparison in which one model fails is a RESULT, not an
/// error in the run.
struct WorkflowCompareFailureReportingTests {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath),
                   encoding: .utf8)
    }

    @Test("progress carries a per-model reason, defaulting to none")
    func progressCarriesAReason() {
        var run = WorkflowCompareRunProgress(id: "gpt-5", label: "gpt-5")
        #expect(run.failureReason == nil)
        #expect(run.threadId == nil)
        run.state = .failed
        run.failureReason = "Vision LLM returned empty response after retry"
        #expect(run.failureReason?.isEmpty == false)
    }

    @Test("two models can disagree about their outcome")
    func modelsCarryIndependentOutcomes() {
        // The shape a global alert could not express: some succeeded, one did
        // not, and the row must be able to say which.
        var good = WorkflowCompareRunProgress(id: "claude", label: "claude")
        good.state = .succeeded
        var bad = WorkflowCompareRunProgress(id: "gpt-5", label: "gpt-5")
        bad.state = .failed
        bad.failureReason = "empty response"
        let row = [good, bad]
        #expect(row.filter { $0.state == .failed }.map(\.id) == ["gpt-5"])
        #expect(row.first { $0.state == .succeeded }?.failureReason == nil)
    }

    @Test("a success clears any reason a previous run left behind")
    func successClearsTheReason() throws {
        // The host writes `state == .failed ? reason : nil`, so re-running a
        // fan-out cannot leave last time's error on a capsule that has since
        // gone green.
        let host = try Self.appSource(
            "Views/Shell/ContentView/Layout/ContentView+WorkflowCompare.swift")
        #expect(host.contains("state == .failed ? reason : nil"))
        #expect(host.contains("reason: succeeded ? nil : execution?.workflowError"))
    }

    @Test("the capsule shows the reason on hover and on click")
    func capsuleShowsTheReason() throws {
        let bar = try Self.appSource("Views/Shell/Toolbar/WorkflowBar+Compare.swift")
        #expect(bar.contains("compareCapsuleHelp"))
        #expect(bar.contains("compareFailureDetail"))
        // Copyable: a model error is the kind of string that gets pasted into
        // an issue, and a tooltip cannot be copied.
        #expect(bar.contains(".textSelection(.enabled)"))
    }

    @Test("only a failed capsule is clickable")
    func onlyFailuresOpen() throws {
        // A green capsule opening an empty popover would teach the user that
        // the click means nothing.
        let bar = try Self.appSource("Views/Shell/Toolbar/WorkflowBar+Compare.swift")
        #expect(bar.contains(".disabled(!isFailed)"))
        #expect(bar.contains("expandedCompareModel == run.id && isFailed"))
    }

    @Test("a missing reason says so rather than showing nothing")
    func absentReasonIsStated() throws {
        let bar = try Self.appSource("Views/Shell/Toolbar/WorkflowBar+Compare.swift")
        #expect(bar.contains("The engine reported no reason"))
    }
}
