import XCTest
@testable import Fichero

/// Guardrail for #4457 — an editor-side workflow run must SETTLE when its SSE
/// stream dies, and settle to the truth.
///
/// `WorkflowEditor+Actions.performWorkflowRun` drove completion from a terminal
/// event only:
///
///     if event.isTerminal { completion.finish() }
///     ...
///     await completion.wait()
///
/// `WorkflowStreamService.execute()` called `startStream` WITHOUT `onStreamEnd`
/// — even though `startStream` has always accepted it and `subscribe()` has
/// always forwarded it. So when the transport died mid-run no terminal frame
/// could ever arrive, `completion.wait()` suspended forever (a leaked
/// continuation and task), `endExecution` never ran, and the editor's run UI
/// span forever. The Activity surface meanwhile reconciled the same run
/// correctly via `WorkflowExecutionStore.reconcileAfterStreamEnd`, so the two
/// surfaces disagreed about one run — the #4380/#4403 class.
///
/// There is a second, quieter half. `computeFinalStatus` reads the OBSERVER,
/// and on a dead stream the observer never saw a terminal event, so it falls
/// through to `.completed` — reporting a success the run never had. Settling is
/// not enough; it has to settle to what the persisted record actually says.
final class WorkflowStreamEndReconciliationTests: XCTestCase {

    // MARK: - Terminality is one definition, exhaustively

    /// `running` and `paused` are the only states a run can still leave on its
    /// own. Everything else is terminal. This is the split
    /// `WorkflowExecutionStore.shouldSubscribe(status:)` makes on the sibling
    /// `WorkflowStatus` enum; the two must not diverge.
    func testOnlyRunningAndPausedAreNonTerminal() {
        XCTAssertFalse(ExecutionStatus.running.isTerminal)
        XCTAssertFalse(ExecutionStatus.paused.isTerminal)

        for status: ExecutionStatus in [.completed, .error, .failed, .cancelled, .stopped, .deleted] {
            XCTAssertTrue(
                status.isTerminal,
                "\(status.rawValue) is a stopped-for-good state and must report terminal (#4457)."
            )
        }
    }

    /// A reconciled terminal status must map to the app status the run really
    /// had — in particular a cancelled run must not arrive as `.failed`, the
    /// collapse #4321 removed.
    func testReconciledStatusMapsThroughTheExistingMapper() {
        XCTAssertEqual(WorkflowExecution.workflowStatus(from: .completed), .completed)
        XCTAssertEqual(WorkflowExecution.workflowStatus(from: .failed), .failed)
        XCTAssertEqual(WorkflowExecution.workflowStatus(from: .error), .failed)
        XCTAssertEqual(WorkflowExecution.workflowStatus(from: .cancelled), .cancelled)
        XCTAssertEqual(WorkflowExecution.workflowStatus(from: .stopped), .cancelled)
    }

    // MARK: - The seam is actually wired

    /// `execute()` must forward `onStreamEnd`. Without this the editor cannot
    /// learn its stream died, whatever it does at the call site.
    func testExecuteForwardsOnStreamEndToStartStream() throws {
        let source = try Self.appSource("Services/WorkflowStreamService.swift")
        guard let executeRange = source.range(of: "func execute("),
              let subscribeRange = source.range(of: "func subscribe(") else {
            return XCTFail("Expected execute() and subscribe() in WorkflowStreamService (#4457).")
        }
        let executeBody = String(source[executeRange.lowerBound..<subscribeRange.lowerBound])
        XCTAssertTrue(
            executeBody.contains("onStreamEnd"),
            """
            WorkflowStreamService.execute() must accept and forward onStreamEnd to \
            startStream. startStream has always supported it and subscribe() has \
            always passed it; execute() dropped it, so a caller awaiting a terminal \
            frame waited forever when the transport died (#4457).
            """
        )
    }

    /// The editor must use the seam, not just have it available.
    func testEditorRunPassesOnStreamEnd() throws {
        let source = try Self.appSource("Views/Workflow/Editor/WorkflowEditor+Actions.swift")
        XCTAssertTrue(
            source.contains("onStreamEnd:"),
            "performWorkflowRun must pass onStreamEnd to execute() or it can still hang (#4457)."
        )
        XCTAssertTrue(
            source.contains("settleAfterStreamEnd"),
            """
            The stream-end path must reconcile against the persisted record via \
            settleAfterStreamEnd — the shared bounded poll — rather than \
            reimplementing a retry loop, which is how the Activity and editor \
            paths came to disagree (#4457).
            """
        )
    }

    /// Settling with the observer's guess would report success for a run that
    /// died. The persisted record must win.
    func testFinalStatusPrefersTheReconciledRecord() throws {
        let source = try Self.appSource("Views/Workflow/Editor/WorkflowEditor+Actions.swift")
        XCTAssertTrue(
            source.contains("completion.reconciledStatus"),
            """
            The final status must prefer the reconciled persisted status over \
            computeFinalStatus, which reads the observer and falls through to \
            .completed on a dead stream — claiming a success that never \
            happened (#4457).
            """
        )
        guard let reconciled = source.range(of: "completion.reconciledStatus"),
              let computed = source.range(of: "computeFinalStatus(executionThreadId: executionThreadId)") else {
            return XCTFail("Expected both the reconciled status and the observer fallback (#4457).")
        }
        XCTAssertTrue(
            reconciled.lowerBound < computed.lowerBound,
            "The reconciled record must be the preferred branch, not the fallback (#4457)."
        )
    }

    /// Was a hand-counted root that landed ONE LEVEL SHORT, so all three tests
    /// in this file died as file-not-found errors naming a path nobody
    /// recognised (#4493). `AppSource` walks up to a landmark instead of
    /// counting, so it cannot be wrong by a level.
    private static func appSource(_ relativePath: String) throws -> String {
        try AppSource.text(relativePath)
    }
}
