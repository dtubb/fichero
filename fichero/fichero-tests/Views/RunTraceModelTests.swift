@testable import Fichero
import XCTest

/// Pure run-trace mapping + layout (#4320): snapshot topology joined with
/// `progress_timeline` outcomes, and the deterministic layered layout the
/// trace canvas renders (the snapshot carries no editor positions).
final class RunTraceModelTests: XCTestCase {

    // MARK: - Fixtures

    private func snapshot(
        nodes: [[String: Any]],
        edges: [[String: Any]] = []
    ) -> [String: Any] {
        ["nodes": nodes, "edges": edges]
    }

    private func node(
        _ id: String,
        tool: String = "transcribe",
        label: String = "",
        provider: String = "",
        model: String = ""
    ) -> [String: Any] {
        [
            "id": id, "tool": tool, "label": label,
            "provider_name": provider, "model_name": model
        ]
    }

    // MARK: - Status mapping

    func testCompletedRunMapsNodeOutcomes() {
        let graph = RunTraceModelBuilder.graph(
            snapshot: snapshot(
                nodes: [
                    node("a", provider: "openai", model: "gpt-4o"),
                    node("b"),
                    node("c")
                ],
                edges: [["source": "a", "target": "b"], ["source": "b", "target": "c"]]
            ),
            timeline: ["steps": [
                ["node_id": "a", "started_at": "t", "status": "success", "duration_ms": 850.0],
                ["node_id": "b", "started_at": "t", "status": "skipped", "skip_reason": "empty query"]
                // c never ran
            ]],
            nodeNameMap: ["a": "Transcribe 1"],
            runStatus: "completed",
            runError: nil
        )

        let a = graph?.node(withId: "a")
        XCTAssertEqual(a?.status, .success)
        XCTAssertEqual(a?.label, "Transcribe 1")
        XCTAssertEqual(a?.durationMs, 850.0)
        XCTAssertEqual(a?.providerModelText, "openai · gpt-4o")
        XCTAssertEqual(graph?.node(withId: "b")?.status, .skipped)
        XCTAssertEqual(graph?.node(withId: "b")?.skipReason, "empty query")
        XCTAssertEqual(graph?.node(withId: "c")?.status, .pending)
        XCTAssertEqual(graph?.edges.count, 2)
    }

    func testFailedRunHighlightsTheRunningNodeWithRunError() {
        // Acceptance (#4320): a failed run highlights the failing node with
        // its error. The failing node is left "running" in the timeline —
        // its node_end never arrived.
        let graph = RunTraceModelBuilder.graph(
            snapshot: snapshot(nodes: [node("a"), node("b")],
                               edges: [["source": "a", "target": "b"]]),
            timeline: ["steps": [
                ["node_id": "a", "started_at": "t", "status": "success"],
                ["node_id": "b", "started_at": "t", "status": "running"]
            ]],
            nodeNameMap: nil,
            runStatus: "failed",
            runError: "provider quota exhausted"
        )

        let failing = graph?.node(withId: "b")
        XCTAssertEqual(failing?.status, .failed)
        XCTAssertEqual(failing?.error, "provider quota exhausted")
        XCTAssertEqual(graph?.node(withId: "a")?.status, .success)
        XCTAssertNil(graph?.node(withId: "a")?.error)
    }

    func testFileErrorsWinOverRunErrorAndAreCounted() {
        let graph = RunTraceModelBuilder.graph(
            snapshot: snapshot(nodes: [node("a")]),
            timeline: ["steps": [
                ["node_id": "a", "started_at": "t", "status": "error"],
                ["type": "file", "node_id": "a", "status": "error", "error": "page 3 unreadable"],
                ["type": "file", "node_id": "a", "status": "error", "error": "page 7 unreadable"]
            ]],
            nodeNameMap: nil,
            runStatus: "failed",
            runError: "run-level error"
        )

        let failed = graph?.node(withId: "a")
        XCTAssertEqual(failed?.status, .failed)
        XCTAssertEqual(failed?.error, "page 3 unreadable\n(+1 more file errors)")
    }

    func testLiveRunKeepsRunningStatusAndCancelledRunDemotesToPending() {
        func status(runStatus: String) -> RunTraceNodeStatus? {
            RunTraceModelBuilder.graph(
                snapshot: snapshot(nodes: [node("a")]),
                timeline: ["steps": [["node_id": "a", "started_at": "t", "status": "running"]]],
                nodeNameMap: nil,
                runStatus: runStatus,
                runError: nil
            )?.node(withId: "a")?.status
        }

        XCTAssertEqual(status(runStatus: "running"), .running)
        XCTAssertEqual(status(runStatus: "paused"), .running)
        // Terminal-but-not-failed: the node never completed — not executed.
        XCTAssertEqual(status(runStatus: "cancelled"), .pending)
    }

    func testMissingSnapshotOrEmptyNodesReturnsNil() {
        XCTAssertNil(
            RunTraceModelBuilder.graph(
                snapshot: [:], timeline: nil, nodeNameMap: nil,
                runStatus: "completed", runError: nil
            )
        )
        XCTAssertNil(
            RunTraceModelBuilder.graph(
                snapshot: ["nodes": [[String: Any]]()], timeline: nil,
                nodeNameMap: nil, runStatus: "completed", runError: nil
            )
        )
    }

    func testEdgesToUnknownNodesAreDropped() {
        let graph = RunTraceModelBuilder.graph(
            snapshot: snapshot(
                nodes: [node("a")],
                edges: [["source": "a", "target": "ghost"]]
            ),
            timeline: nil,
            nodeNameMap: nil,
            runStatus: "completed",
            runError: nil
        )
        XCTAssertEqual(graph?.edges, [])
    }

    // MARK: - Layout

    func testLayoutColumnsFollowLongestPathDepth() {
        let nodes = ["a", "b", "c", "d"].map {
            RunTraceNode(
                id: $0, label: $0, tool: "t", provider: nil, model: nil,
                status: .success, durationMs: nil, error: nil, skipReason: nil
            )
        }
        // a → b → d and a → d: d's depth is 2 (longest path), not 1.
        let edges = [
            RunTraceEdge(source: "a", target: "b"),
            RunTraceEdge(source: "b", target: "d"),
            RunTraceEdge(source: "a", target: "d"),
            RunTraceEdge(source: "a", target: "c")
        ]

        let depths = RunTraceLayoutEngine.nodeDepths(nodeIds: nodes.map(\.id), edges: edges)
        XCTAssertEqual(depths, ["a": 0, "b": 1, "c": 1, "d": 2])

        let layout = RunTraceLayoutEngine.layout(nodes: nodes, edges: edges)
        // Same column ⇒ same x; deeper column ⇒ strictly larger x.
        XCTAssertEqual(layout.positions["b"]?.x, layout.positions["c"]?.x)
        XCTAssertLessThan(layout.positions["a"]!.x, layout.positions["b"]!.x)
        XCTAssertLessThan(layout.positions["b"]!.x, layout.positions["d"]!.x)
        // Parallel siblings stack vertically.
        XCTAssertNotEqual(layout.positions["b"]?.y, layout.positions["c"]?.y)
        // Every node fits inside the reported canvas size.
        for point in layout.positions.values {
            XCTAssertLessThan(point.x, layout.size.width)
            XCTAssertLessThan(point.y, layout.size.height)
        }
    }

    func testLayoutSurvivesMalformedCycle() {
        let nodes = ["a", "b"].map {
            RunTraceNode(
                id: $0, label: $0, tool: "t", provider: nil, model: nil,
                status: .success, durationMs: nil, error: nil, skipReason: nil
            )
        }
        let edges = [
            RunTraceEdge(source: "a", target: "b"),
            RunTraceEdge(source: "b", target: "a")
        ]
        // Must terminate and place both nodes.
        let layout = RunTraceLayoutEngine.layout(nodes: nodes, edges: edges)
        XCTAssertEqual(layout.positions.count, 2)
    }

    func testEmptyGraphLayoutIsEmpty() {
        let layout = RunTraceLayoutEngine.layout(nodes: [], edges: [])
        XCTAssertTrue(layout.positions.isEmpty)
        XCTAssertEqual(layout.size, .zero)
    }

    // MARK: - Duration formatting

    func testDurationFormatting() {
        XCTAssertEqual(RunTraceFormat.duration(ms: 850), "850ms")
        XCTAssertEqual(RunTraceFormat.duration(ms: 3200), "3.2s")
        XCTAssertEqual(RunTraceFormat.duration(ms: 125_000), "2m 05s")
    }
}
