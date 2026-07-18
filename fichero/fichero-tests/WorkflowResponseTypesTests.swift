@testable import Fichero
import XCTest

/// Tests for the workflow API response DTOs + NodeExecutionState helpers.
/// Locks: snake_case decoding for every backend payload (drift = silent
/// missing fields), NodeExecutionState.progressText format ("N/M"),
/// isParallelProcessing gate (status + fileTotal both required).
final class WorkflowResponseTypesTests: XCTestCase {

    // MARK: - NodeResponse snake_case

    func testNodeResponseDecodesSnakeCase() throws {
        let json = """
        {
            "id": "n1",
            "tool": "summarize",
            "label": "Summarise",
            "description": "step",
            "input_ports": [],
            "output_ports": [],
            "position_x": 100.5,
            "position_y": 200.0
        }
        """.data(using: .utf8)!
        let node = try JSONDecoder().decode(NodeResponse.self, from: json)
        XCTAssertEqual(node.id, "n1")
        XCTAssertEqual(node.positionX, 100.5)
        XCTAssertEqual(node.positionY, 200.0)
        XCTAssertEqual(node.label, "Summarise")
    }

    func testNodeResponseAcceptsNilLabel() throws {
        let json = """
        {
            "id": "n1", "tool": "x", "label": null, "description": null,
            "input_ports": [], "output_ports": [],
            "position_x": 0, "position_y": 0
        }
        """.data(using: .utf8)!
        let node = try JSONDecoder().decode(NodeResponse.self, from: json)
        XCTAssertNil(node.label)
        XCTAssertNil(node.description)
    }

    // MARK: - RunWorkflowRequest encoding

    func testRunWorkflowRequestEncodesSnakeCaseKey() throws {
        let wf = WorkflowDefinition(
            id: "wf-1", name: "x", description: "",
            provider: "openai", model: "gpt-4o",
            folderPath: "/", sortOrder: 0,
            inputSource: .collection, isSystem: false
        )
        let req = RunWorkflowRequest(workflow: wf, inputs: ["k": "v"], inputFiles: ["/tmp/a.pdf"])
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertNotNil(json?["workflow"])
        XCTAssertEqual(json?["input_files"] as? [String], ["/tmp/a.pdf"])
        let inputs = json?["inputs"] as? [String: Any]
        XCTAssertNotNil(inputs?["k"])
    }

    func testRunWorkflowRequestInputsWrappedInAnyCodable() {
        let wf = WorkflowDefinition(
            id: "wf-1", name: "x", description: "",
            provider: "", model: "",
            folderPath: "/", sortOrder: 0,
            inputSource: .collection, isSystem: false
        )
        let req = RunWorkflowRequest(workflow: wf, inputs: ["n": 42], inputFiles: [])
        XCTAssertEqual(req.inputs.count, 1)  // raw [String: Any] → [String: AnyCodable]
        XCTAssertTrue(req.inputFiles.isEmpty)
    }

    // MARK: - WorkflowResponse

    func testWorkflowResponseDecodesSnakeCase() throws {
        let json = """
        {
            "id": "wf-1", "name": "Test", "description": "",
            "provider": "openai", "model": "gpt-4o",
            "nodes": [], "edges": [],
            "folder_path": "/Catalogue",
            "sort_order": 3,
            "is_system": true,
            "untested": false
        }
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(WorkflowResponse.self, from: json)
        XCTAssertEqual(resp.folderPath, "/Catalogue")
        XCTAssertEqual(resp.sortOrder, 3)
        XCTAssertTrue(resp.isSystem)
    }

    // MARK: - NodeExecutionStatus raw values

    func testExecutionStatusRawValues() {
        // Locked to backend strings — drift here = invisible-status bug.
        XCTAssertEqual(NodeExecutionStatus.idle.rawValue, "idle")
        XCTAssertEqual(NodeExecutionStatus.running.rawValue, "running")
        XCTAssertEqual(NodeExecutionStatus.parallelRunning.rawValue, "parallel_running")
        XCTAssertEqual(NodeExecutionStatus.completed.rawValue, "completed")
        XCTAssertEqual(NodeExecutionStatus.failed.rawValue, "failed")
    }

    // MARK: - NodeExecutionState

    func testExecutionStateDefaults() {
        let state = NodeExecutionState(nodeId: "n1")
        XCTAssertEqual(state.id, "n1")
        XCTAssertEqual(state.status, .idle)
        XCTAssertEqual(state.progress, 0.0)
        XCTAssertNil(state.currentFile)
        XCTAssertFalse(state.isParallelProcessing)
        XCTAssertNil(state.progressText)
    }

    func testIsParallelProcessingRequiresBothStatusAndFileTotal() {
        var state = NodeExecutionState(nodeId: "n1")
        state.status = .parallelRunning
        XCTAssertFalse(state.isParallelProcessing)  // fileTotal = 0
        state.fileTotal = 10
        XCTAssertTrue(state.isParallelProcessing)
        state.status = .running  // wrong status
        XCTAssertFalse(state.isParallelProcessing)
    }

    func testProgressTextFormat() {
        var state = NodeExecutionState(nodeId: "n1")
        state.status = .parallelRunning
        state.fileTotal = 10
        state.successCount = 3
        state.errorCount = 2
        XCTAssertEqual(state.progressText, "5/10")  // success + error
    }

    func testProgressTextNilWhenNotParallel() {
        var state = NodeExecutionState(nodeId: "n1")
        state.status = .running
        state.fileTotal = 10
        state.successCount = 5
        XCTAssertNil(state.progressText)
    }

    // MARK: - WorkflowSSEEvent

    func testSSEEventDecodesSnakeCase() throws {
        let json = """
        {
            "event": "node_start",
            "thread_id": "t-1",
            "workflow_id": "wf-1",
            "data": {},
            "timestamp": "2026-05-10T10:00:00Z",
            "node_id": "n1",
            "file_path": "/tmp/x.pdf",
            "file_index": 2,
            "file_total": 10,
            "progress": 0.2
        }
        """.data(using: .utf8)!
        let ev = try JSONDecoder().decode(WorkflowSSEEvent.self, from: json)
        XCTAssertEqual(ev.event, "node_start")
        XCTAssertEqual(ev.threadId, "t-1")
        XCTAssertEqual(ev.workflowId, "wf-1")
        XCTAssertEqual(ev.nodeId, "n1")
        XCTAssertEqual(ev.filePath, "/tmp/x.pdf")
        XCTAssertEqual(ev.fileIndex, 2)
        XCTAssertEqual(ev.fileTotal, 10)
        XCTAssertEqual(ev.progress, 0.2)
    }

    func testSSEEventOptionalParallelFieldsCanBeMissing() throws {
        // Sequential nodes don't emit parallel_* fields. Decoder must
        // tolerate their absence rather than fail the whole event.
        let json = """
        {
            "event": "node_complete",
            "thread_id": "t-1",
            "workflow_id": "wf-1",
            "data": {},
            "timestamp": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let ev = try JSONDecoder().decode(WorkflowSSEEvent.self, from: json)
        XCTAssertNil(ev.nodeId)
        XCTAssertNil(ev.filePath)
        XCTAssertNil(ev.fileIndex)
        XCTAssertNil(ev.fileTotal)
        XCTAssertNil(ev.progress)
    }
}
