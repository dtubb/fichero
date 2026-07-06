@testable import Fichero
import XCTest

/// Tests for WorkflowRunResponse's custom Codable conformance. The generated
/// Components.Schemas.WorkflowRunResponse is a different type; this app-level
/// struct hand-rolls init(from:)/encode(to:) to snake_case-map fields and
/// type-erase the two free-form JSON blobs (workflow_snapshot,
/// progress_timeline) through CheckpointValue. Pure decode/encode, no engine.
final class WorkflowRunResponseCodingTests: XCTestCase {

    // MARK: - Full decode

    func testDecodesAllFieldsIncludingErasedBlobs() throws {
        let json = Data("""
        {
            "thread_id": "t-1",
            "workflow_id": "wf-1",
            "workflow_name": "My Flow",
            "python_code": "print(1)",
            "execution_log": "ran",
            "status": "completed",
            "started_at": "2026-05-10T10:00:00Z",
            "completed_at": "2026-05-10T10:01:00Z",
            "duration_ms": 1234.5,
            "error": null,
            "workflow_snapshot": {"version": 2, "name": "snap"},
            "node_name_map": {"n1": "Start"},
            "progress_timeline": {"step": 3},
            "diagram_mermaid": "graph TD;"
        }
        """.utf8)
        let run = try JSONDecoder().decode(WorkflowRunResponse.self, from: json)

        XCTAssertEqual(run.threadId, "t-1")
        XCTAssertEqual(run.workflowId, "wf-1")
        XCTAssertEqual(run.workflowName, "My Flow")
        XCTAssertEqual(run.pythonCode, "print(1)")
        XCTAssertEqual(run.executionLog, "ran")
        XCTAssertEqual(run.status, "completed")
        XCTAssertEqual(run.startedAt, "2026-05-10T10:00:00Z")
        XCTAssertEqual(run.completedAt, "2026-05-10T10:01:00Z")
        XCTAssertEqual(run.durationMs, 1234.5)
        XCTAssertNil(run.error)
        XCTAssertEqual(run.diagramMermaid, "graph TD;")
        XCTAssertEqual(run.nodeNameMap, ["n1": "Start"])

        // Erased blobs come back as [String: Any].
        let snapshot = try XCTUnwrap(run.workflowSnapshot)
        XCTAssertEqual(snapshot["name"] as? String, "snap")
        XCTAssertEqual(snapshot["version"] as? Int, 2)  // CheckpointValue prefers Int
        let timeline = try XCTUnwrap(run.progressTimeline)
        XCTAssertEqual(timeline["step"] as? Int, 3)
    }

    // MARK: - Minimal decode (only required keys)

    func testDecodesMinimalPayloadWithOptionalsNil() throws {
        let json = Data("""
        {
            "thread_id": "t-2",
            "workflow_id": "wf-2",
            "workflow_name": "Bare",
            "status": "running"
        }
        """.utf8)
        let run = try JSONDecoder().decode(WorkflowRunResponse.self, from: json)
        XCTAssertEqual(run.status, "running")
        XCTAssertNil(run.pythonCode)
        XCTAssertNil(run.durationMs)
        XCTAssertNil(run.error)
        XCTAssertNil(run.workflowSnapshot)
        XCTAssertNil(run.nodeNameMap)
        XCTAssertNil(run.progressTimeline)
        XCTAssertNil(run.diagramMermaid)
    }

    /// A snapshot that isn't a JSON object must degrade to nil, not throw —
    /// the `as? [String: Any]` guard is the tolerant-decode path.
    func testNonObjectSnapshotDegradesToNil() throws {
        let json = Data("""
        {
            "thread_id": "t-3",
            "workflow_id": "wf-3",
            "workflow_name": "Weird",
            "status": "error",
            "workflow_snapshot": "not-an-object"
        }
        """.utf8)
        let run = try JSONDecoder().decode(WorkflowRunResponse.self, from: json)
        XCTAssertNil(run.workflowSnapshot)
    }

    // MARK: - Encode

    func testEncodeEmitsSnakeCaseKeysAndSnapshot() throws {
        let run = WorkflowRunResponse(
            threadId: "t-1", workflowId: "wf-1", workflowName: "Flow",
            pythonCode: "x", executionLog: nil, status: "completed",
            startedAt: nil, completedAt: nil, durationMs: 12.0, error: nil,
            workflowSnapshot: ["k": "v"], nodeNameMap: ["a": "b"],
            progressTimeline: nil, diagramMermaid: nil
        )
        let data = try JSONEncoder().encode(run)
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(obj["thread_id"] as? String, "t-1")
        XCTAssertEqual(obj["workflow_id"] as? String, "wf-1")
        XCTAssertEqual(obj["duration_ms"] as? Double, 12.0)
        XCTAssertEqual((obj["workflow_snapshot"] as? [String: Any])?["k"] as? String, "v")
        XCTAssertEqual(obj["node_name_map"] as? [String: String], ["a": "b"])
    }

    /// Nil blobs are dropped entirely (encode, not encodeIfPresent-with-null).
    func testEncodeOmitsNilBlobsAndOptionals() throws {
        let run = WorkflowRunResponse(
            threadId: "t-1", workflowId: "wf-1", workflowName: "Flow",
            pythonCode: nil, executionLog: nil, status: "running",
            startedAt: nil, completedAt: nil, durationMs: nil, error: nil,
            workflowSnapshot: nil, nodeNameMap: nil,
            progressTimeline: nil, diagramMermaid: nil
        )
        let data = try JSONEncoder().encode(run)
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertNil(obj["workflow_snapshot"])
        XCTAssertNil(obj["progress_timeline"])
        XCTAssertNil(obj["python_code"])
        XCTAssertNil(obj["duration_ms"])
        // Required keys still present.
        XCTAssertEqual(obj["status"] as? String, "running")
    }
}
