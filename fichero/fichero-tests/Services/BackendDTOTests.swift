@testable import Fichero
import XCTest

/// Tests for backend-facing DTOs: CheckpointTypes (workflow checkpoint
/// history) + BatchTypes (batch execution). Both are 100% Codable
/// surface with Python snake_case + computed display helpers.
final class BackendDTOTests: XCTestCase {

    // MARK: - CheckpointSnapshot

    func testCheckpointSnapshotDecodesSnakeCase() throws {
        let json = """
        {
            "checkpoint_id": "ck-1",
            "parent_checkpoint_id": "ck-0",
            "step": 3,
            "timestamp": "2026-05-10T10:00:00Z",
            "node_name": "summarize",
            "state_values": {"output": "hello"},
            "writes": {},
            "next_nodes": ["__end__"]
        }
        """.data(using: .utf8)!
        let snap = try JSONDecoder().decode(CheckpointSnapshot.self, from: json)
        XCTAssertEqual(snap.id, "ck-1")  // id derived from checkpointId
        XCTAssertEqual(snap.parentCheckpointId, "ck-0")
        XCTAssertEqual(snap.nodeName, "summarize")
        XCTAssertEqual(snap.nextNodes, ["__end__"])
        XCTAssertEqual(snap.stateValues["output"]?.stringValue, "hello")
    }

    func testCheckpointHistoryResponseDecodesSnakeCase() throws {
        let json = """
        {
            "thread_id": "t-1",
            "workflow_id": "wf-1",
            "workflow_name": "Test",
            "total_steps": 5,
            "checkpoints": []
        }
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(CheckpointHistoryResponse.self, from: json)
        XCTAssertEqual(resp.threadId, "t-1")
        XCTAssertEqual(resp.workflowId, "wf-1")
        XCTAssertEqual(resp.workflowName, "Test")
        XCTAssertEqual(resp.totalSteps, 5)
    }

    // MARK: - CheckpointValue round-trip + stringValue

    func testCheckpointValueNullStringRender() throws {
        let data = "null".data(using: .utf8)!
        let v = try JSONDecoder().decode(CheckpointValue.self, from: data)
        XCTAssertEqual(v.stringValue, "null")
    }

    func testCheckpointValueBoolStringRender() throws {
        let v = CheckpointValue(true)
        XCTAssertEqual(v.stringValue, "true")
        XCTAssertEqual(CheckpointValue(false).stringValue, "false")
    }

    func testCheckpointValueIntStringRender() throws {
        let v = CheckpointValue(42)
        XCTAssertEqual(v.stringValue, "42")
    }

    func testCheckpointValueDoubleStringRendersTwoDecimals() throws {
        let v = CheckpointValue(3.14159)
        XCTAssertEqual(v.stringValue, "3.14")  // "%.2f"
    }

    func testCheckpointValueStringPassthrough() throws {
        let v = CheckpointValue("hello")
        XCTAssertEqual(v.stringValue, "hello")
    }

    func testCheckpointValueArrayStringRender() throws {
        let v = CheckpointValue([1, 2, 3] as [Any])
        XCTAssertEqual(v.stringValue, "[3 items]")
    }

    func testCheckpointValueDictStringRender() throws {
        let v = CheckpointValue(["a": 1, "b": 2] as [String: Any])
        XCTAssertEqual(v.stringValue, "{2 keys}")
    }

    func testCheckpointValueRoundTripPrimitives() throws {
        // Encode then decode each scalar branch via JSON.
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()
        let pairs: [(Any, String)] = [
            (true, "true"),
            (42, "42"),
            ("hello", "hello")
        ]
        for (raw, expected) in pairs {
            let data = try encoder.encode(CheckpointValue(raw))
            let decoded = try decoder.decode(CheckpointValue.self, from: data)
            XCTAssertEqual(decoded.stringValue, expected)
        }
    }

    func testCheckpointValueEncodesNull() throws {
        let v = CheckpointValue(NSNull())
        let data = try JSONEncoder().encode(v)
        XCTAssertEqual(String(data: data, encoding: .utf8), "null")
    }

    // MARK: - BatchInfo

    func testBatchInfoDecodesSnakeCase() throws {
        let json = """
        {
            "batch_id": "b-1",
            "workflow_id": "wf-1",
            "status": "running",
            "total_items": 100,
            "completed_items": 25,
            "failed_items": 2,
            "max_concurrent": 4,
            "created_at": "2026-05-10T10:00:00Z",
            "started_at": "2026-05-10T10:00:05Z",
            "completed_at": null,
            "error_message": null,
            "items": null
        }
        """.data(using: .utf8)!
        let batch = try JSONDecoder().decode(BatchInfo.self, from: json)
        XCTAssertEqual(batch.id, "b-1")
        XCTAssertEqual(batch.totalItems, 100)
        XCTAssertEqual(batch.completedItems, 25)
        XCTAssertEqual(batch.maxConcurrent, 4)
        XCTAssertNil(batch.completedAt)
    }

    func testBatchProgressPercent() {
        let batch = BatchInfo(
            batchId: "b-1", workflowId: "wf-1", status: "running",
            totalItems: 200, completedItems: 50, failedItems: 0,
            maxConcurrent: 4, createdAt: "", startedAt: nil,
            completedAt: nil, errorMessage: nil, items: nil
        )
        XCTAssertEqual(batch.progressPercent, 25.0)
    }

    func testBatchProgressPercentGuardsAgainstZeroTotal() {
        let batch = BatchInfo(
            batchId: "b-1", workflowId: "wf-1", status: "pending",
            totalItems: 0, completedItems: 0, failedItems: 0,
            maxConcurrent: 1, createdAt: "", startedAt: nil,
            completedAt: nil, errorMessage: nil, items: nil
        )
        // No divide-by-zero — explicit early return.
        XCTAssertEqual(batch.progressPercent, 0)
    }

    func testBatchStatusIconCoversAllCases() {
        // Locks status string → SF Symbol map. UI shows
        // questionmark.circle for unknown strings.
        let cases: [(String, String)] = [
            ("pending", "clock"),
            ("running", "play.circle.fill"),
            ("paused", "pause.circle.fill"),
            ("completed", "checkmark.circle.fill"),
            ("partial_failure", "exclamationmark.triangle.fill"),
            ("failed", "xmark.circle.fill"),
            ("cancelled", "stop.circle.fill"),
            ("garbage", "questionmark.circle")
        ]
        for (status, expected) in cases {
            let batch = BatchInfo(
                batchId: "b-1", workflowId: "wf-1", status: status,
                totalItems: 0, completedItems: 0, failedItems: 0,
                maxConcurrent: 1, createdAt: "", startedAt: nil,
                completedAt: nil, errorMessage: nil, items: nil
            )
            XCTAssertEqual(batch.statusIcon, expected, "status=\(status)")
        }
    }

    func testBatchStatusColorCoversAllCases() {
        let cases: [(String, String)] = [
            ("pending", "gray"),
            ("running", "blue"),
            ("paused", "yellow"),
            ("completed", "green"),
            ("partial_failure", "orange"),
            ("failed", "red"),
            ("cancelled", "gray"),
            ("garbage", "primary")
        ]
        for (status, expected) in cases {
            let batch = BatchInfo(
                batchId: "b-1", workflowId: "wf-1", status: status,
                totalItems: 0, completedItems: 0, failedItems: 0,
                maxConcurrent: 1, createdAt: "", startedAt: nil,
                completedAt: nil, errorMessage: nil, items: nil
            )
            XCTAssertEqual(batch.statusColor, expected, "status=\(status)")
        }
    }

    func testBatchNameTruncatesId() {
        let batch = BatchInfo(
            batchId: "abcdef1234567890",
            workflowId: "wf", status: "x",
            totalItems: 0, completedItems: 0, failedItems: 0,
            maxConcurrent: 1, createdAt: "", startedAt: nil,
            completedAt: nil, errorMessage: nil, items: nil
        )
        XCTAssertEqual(batch.name, "Batch abcdef12...")  // first 8 chars
    }

    // MARK: - BatchItemInfo

    func testBatchItemInfoDecodesSnakeCase() throws {
        let json = """
        {
            "thread_id": "t-1",
            "item_index": 5,
            "inputs": {"x": "1"},
            "status": "running",
            "error": null,
            "started_at": "2026-05-10T10:00:00Z",
            "completed_at": null
        }
        """.data(using: .utf8)!
        let item = try JSONDecoder().decode(BatchItemInfo.self, from: json)
        XCTAssertEqual(item.id, "t-1")
        XCTAssertEqual(item.itemIndex, 5)
        XCTAssertEqual(item.inputs?["x"], "1")
    }

    // MARK: - BatchProgress

    func testBatchProgressDecodes() throws {
        let json = """
        {
            "batch_id": "b-1",
            "total_items": 100,
            "completed_items": 50,
            "failed_items": 5,
            "running_items": 10,
            "pending_items": 35,
            "progress_percent": 50.0,
            "estimated_remaining_seconds": 120.5,
            "avg_item_duration_seconds": 2.4
        }
        """.data(using: .utf8)!
        let progress = try JSONDecoder().decode(BatchProgress.self, from: json)
        XCTAssertEqual(progress.batchId, "b-1")
        XCTAssertEqual(progress.runningItems, 10)
        XCTAssertEqual(progress.pendingItems, 35)
        XCTAssertEqual(progress.estimatedRemainingSeconds, 120.5)
        XCTAssertEqual(progress.avgItemDurationSeconds, 2.4)
    }

    // MARK: - CreateBatchRequest

    func testCreateBatchRequestEncodesSnakeCase() throws {
        let req = CreateBatchRequest(
            workflowId: "wf-1",
            items: [BatchInputItem(inputs: ["k": "v"])],
            maxConcurrent: 5
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["workflow_id"] as? String, "wf-1")
        XCTAssertEqual(json?["max_concurrent"] as? Int, 5)
        XCTAssertNotNil(json?["items"])
    }
}
