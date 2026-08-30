@testable import Fichero
import XCTest

/// Per-step run records (#4284) reaching the trace surface.
///
/// The defect these pin: before step records, a step that completed having
/// produced nothing returned `"success"` from the timeline and rendered as a
/// green checkmark, while a step that never ran was simply absent and
/// rendered as `pending`. The user could not tell "this ran and found
/// nothing" from "this never happened" — and those demand different
/// responses. Every test here fails if the two collapse back together.
final class RunTraceStepStatusTests: XCTestCase {

    // MARK: - Fixtures

    private func step(
        _ nodeId: String,
        status: String,
        producedNothing: Bool = false,
        durationMs: Double? = nil,
        error: String? = nil,
        skipReason: String? = nil,
        artifacts: [WorkflowRunArtifact] = []
    ) -> WorkflowRunStep {
        WorkflowRunStep(
            nodeId: nodeId,
            nodeName: nodeId,
            tool: "transcribe",
            status: status,
            startedAt: nil,
            completedAt: nil,
            durationMs: durationMs,
            error: error,
            skipReason: skipReason,
            terminatedByRun: nil,
            filesTotal: nil,
            filesSucceeded: nil,
            filesFailed: nil,
            artifactCount: nil,
            producedNothing: producedNothing,
            artifacts: artifacts
        )
    }

    private func node(_ id: String, status: RunTraceNodeStatus = .pending) -> RunTraceNode {
        RunTraceNode(
            id: id, label: id, tool: "transcribe", provider: nil, model: nil,
            status: status, durationMs: nil, error: nil, skipReason: nil
        )
    }

    // MARK: - The three states must not collapse

    func testCompletedWithOutputIsSuccessButCompletedWithNothingIsNot() {
        XCTAssertEqual(
            RunTraceModelBuilder.stepStatus(status: "completed", producedNothing: false),
            .success
        )
        XCTAssertEqual(
            RunTraceModelBuilder.stepStatus(status: "completed", producedNothing: true),
            .producedNothing
        )
    }

    /// The core of #4284: produced-nothing, did-not-run and failed are three
    /// different answers and must be three different states.
    func testProducedNothingDidNotRunAndFailedAreAllDistinct() {
        let producedNothing = RunTraceModelBuilder.stepStatus(
            status: "completed", producedNothing: true
        )
        let didNotRun = RunTraceModelBuilder.stepStatus(status: "not_run", producedNothing: false)
        let failed = RunTraceModelBuilder.stepStatus(status: "failed", producedNothing: false)

        XCTAssertNotEqual(producedNothing, didNotRun)
        XCTAssertNotEqual(producedNothing, failed)
        XCTAssertNotEqual(didNotRun, failed)
        XCTAssertEqual(didNotRun, .pending)
        XCTAssertEqual(failed, .failed)
    }

    /// Each of the three reads differently on screen — same colour, icon or
    /// wording would put them back in one bucket for the person looking.
    func testTheThreeStatesRenderDistinguishably() {
        let states: [RunTraceNodeStatus] = [.producedNothing, .pending, .failed]

        let colors = states.map { RunTraceStatusStyle.color(for: $0) }
        let icons = states.map { RunTraceStatusStyle.icon(for: $0) }
        let notes = states.map { RunTraceStatusStyle.note(for: $0) }
        let spoken = states.map { RunTraceStatusStyle.accessibilityText(for: $0) }
        let empties = states.map { RunTraceStatusStyle.emptyArtifactsText(for: $0) }

        XCTAssertEqual(Set(colors).count, 3, "colours must differ")
        XCTAssertEqual(Set(icons).count, 3, "icons must differ")
        XCTAssertEqual(Set(notes).count, 3, "captions must differ")
        XCTAssertEqual(Set(spoken).count, 3, "VoiceOver text must differ")
        XCTAssertEqual(Set(empties).count, 3, "empty-artifact wording must differ")
    }

    /// "produced nothing" must never be spoken as plain "completed" — that
    /// implies output a screen-reader user cannot see is absent.
    func testProducedNothingIsSpokenAsProducingNothing() {
        let spoken = RunTraceStatusStyle.accessibilityText(for: .producedNothing)
        XCTAssertTrue(spoken.contains("produced nothing"), spoken)
        XCTAssertNotEqual(spoken, RunTraceStatusStyle.accessibilityText(for: .success))
    }

    /// A green tick needs no caption; every outcome that could be misread does.
    func testOnlySelfEvidentStatesOmitTheCaption() {
        XCTAssertNil(RunTraceStatusStyle.note(for: .success))
        XCTAssertNil(RunTraceStatusStyle.note(for: .running))
        for status: RunTraceNodeStatus in [.producedNothing, .pending, .failed, .cancelled, .skipped] {
            XCTAssertNotNil(RunTraceStatusStyle.note(for: status), "\(status) needs words")
        }
    }

    func testCancelledIsNeitherFailedNorNotRun() {
        let cancelled = RunTraceModelBuilder.stepStatus(status: "cancelled", producedNothing: false)
        XCTAssertEqual(cancelled, .cancelled)
        XCTAssertNotEqual(cancelled, .failed)
        XCTAssertNotEqual(cancelled, .pending)
    }

    /// A status the client has never heard of must claim the least, not
    /// borrow the look of success or failure.
    func testUnknownStatusDoesNotMasqueradeAsSuccessOrFailure() {
        let unknown = RunTraceModelBuilder.stepStatus(status: "quantum", producedNothing: false)
        XCTAssertEqual(unknown, .pending)
        XCTAssertNotEqual(unknown, .success)
        XCTAssertNotEqual(unknown, .failed)
    }

    // MARK: - Overlaying records onto the timeline graph

    func testStepRecordsOverrideTimelineDerivedStatus() {
        // The timeline said "success"; the record says it produced nothing.
        let graph = RunTraceGraph(nodes: [node("a", status: .success)], edges: [])
        let applied = RunTraceModelBuilder.applying(
            steps: [step("a", status: "completed", producedNothing: true)],
            to: graph
        )
        XCTAssertEqual(applied.node(withId: "a")?.status, .producedNothing)
    }

    /// Legacy runs carry no records at all; they must pass through unchanged
    /// rather than being reset to "did not run".
    func testRunWithoutStepRecordsIsUntouched() {
        let graph = RunTraceGraph(nodes: [node("a", status: .success)], edges: [])
        let applied = RunTraceModelBuilder.applying(steps: [], to: graph)
        XCTAssertEqual(applied, graph)
    }

    func testNodesWithoutAMatchingRecordKeepTheirTimelineStatus() {
        let graph = RunTraceGraph(
            nodes: [node("a", status: .success), node("b", status: .running)],
            edges: [RunTraceEdge(source: "a", target: "b")]
        )
        let applied = RunTraceModelBuilder.applying(
            steps: [step("a", status: "not_run")],
            to: graph
        )
        XCTAssertEqual(applied.node(withId: "a")?.status, .pending)
        XCTAssertEqual(applied.node(withId: "b")?.status, .running)
        XCTAssertEqual(applied.edges, graph.edges)
    }

    /// File-level failure detail lives in the timeline, not on the record —
    /// applying records must not wipe it.
    func testTimelineErrorSurvivesWhenTheRecordHasNone() {
        let withError = RunTraceNode(
            id: "a", label: "a", tool: "t", provider: nil, model: nil,
            status: .failed, durationMs: 12, error: "page 3 unreadable", skipReason: nil
        )
        let applied = RunTraceModelBuilder.applying(
            steps: [step("a", status: "failed")],
            to: RunTraceGraph(nodes: [withError], edges: [])
        )
        XCTAssertEqual(applied.node(withId: "a")?.error, "page 3 unreadable")
        XCTAssertEqual(applied.node(withId: "a")?.durationMs, 12)
    }

    // MARK: - produced_nothing is read, never inferred

    /// An empty `artifacts` list is true of a step that never ran AND of one
    /// that ran and found nothing. Only the server's flag separates them, so
    /// the flag is what must be read.
    func testProducedNothingComesFromTheFlagNotAnEmptyArtifactList() {
        let neverRan = step("a", status: "not_run", producedNothing: false, artifacts: [])
        let ranEmpty = step("b", status: "completed", producedNothing: true, artifacts: [])

        XCTAssertFalse(neverRan.didProduceNothing)
        XCTAssertTrue(ranEmpty.didProduceNothing)

        let graph = RunTraceGraph(nodes: [node("a"), node("b")], edges: [])
        let applied = RunTraceModelBuilder.applying(steps: [neverRan, ranEmpty], to: graph)
        XCTAssertEqual(applied.node(withId: "a")?.status, .pending)
        XCTAssertEqual(applied.node(withId: "b")?.status, .producedNothing)
    }
}
