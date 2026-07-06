@testable import Fichero
import XCTest

/// Tests for ResearchModels — the research display DTOs that mirror the
/// backend's research_models.py. These are pure Codable value types with
/// snake_case CodingKeys, enum `label`/`rawValueForAPI` display helpers, and
/// one defensive decode-only initializer (ResearchTaskStatus). No live engine.
final class ResearchModelsTests: XCTestCase {

    // MARK: - ResearchTaskStatus: defensive decode + display mapping

    /// Backend sends the snake_case "in_progress"; the custom init maps it to
    /// the camelCase case. This is the only status the JSON wire form differs
    /// from the Swift case name, so it's the one that needs a custom init.
    func testTaskStatusDecodesInProgressFromSnakeCase() throws {
        let decoded = try JSONDecoder().decode(ResearchTaskStatus.self,
                                         from: Data("\"in_progress\"".utf8))
        XCTAssertEqual(decoded, .inProgress)
    }

    func testTaskStatusDecodesKnownValues() throws {
        let cases: [(String, ResearchTaskStatus)] = [
            ("pending", .pending),
            ("completed", .completed),
            ("blocked", .blocked),
            ("cancelled", .cancelled)
        ]
        for (raw, expected) in cases {
            let decoded = try JSONDecoder().decode(ResearchTaskStatus.self,
                                             from: Data("\"\(raw)\"".utf8))
            XCTAssertEqual(decoded, expected, "raw=\(raw)")
        }
    }

    /// Unknown / unexpected server strings must NOT throw — they fall back to
    /// .pending so a new backend status never crashes an older client.
    func testTaskStatusUnknownFallsBackToPending() throws {
        for raw in ["\"deferred\"", "\"\"", "\"IN_PROGRESS\"", "\"inProgress\""] {
            let decoded = try JSONDecoder().decode(ResearchTaskStatus.self,
                                             from: Data(raw.utf8))
            XCTAssertEqual(decoded, .pending, "raw=\(raw) should degrade to .pending")
        }
    }

    /// rawValueForAPI is the explicit encode-for-backend path (the Codable
    /// synthesized encode is not used for the wire). Only .inProgress differs
    /// from the default rawValue.
    func testTaskStatusRawValueForAPI() {
        XCTAssertEqual(ResearchTaskStatus.inProgress.rawValueForAPI, "in_progress")
        XCTAssertEqual(ResearchTaskStatus.pending.rawValueForAPI, "pending")
        XCTAssertEqual(ResearchTaskStatus.completed.rawValueForAPI, "completed")
        XCTAssertEqual(ResearchTaskStatus.blocked.rawValueForAPI, "blocked")
        XCTAssertEqual(ResearchTaskStatus.cancelled.rawValueForAPI, "cancelled")
    }

    func testTaskStatusLabels() {
        XCTAssertEqual(ResearchTaskStatus.inProgress.label, "In Progress")
        XCTAssertEqual(ResearchTaskStatus.pending.label, "Pending")
        XCTAssertEqual(ResearchTaskStatus.completed.label, "Completed")
        XCTAssertEqual(ResearchTaskStatus.blocked.label, "Blocked")
        XCTAssertEqual(ResearchTaskStatus.cancelled.label, "Cancelled")
    }

    // MARK: - Other status enums: label == capitalized rawValue

    func testProjectStatusLabelsAndCases() {
        XCTAssertEqual(ResearchProjectStatus.allCases,
                       [.active, .paused, .completed, .archived])
        XCTAssertEqual(ResearchProjectStatus.active.label, "Active")
        XCTAssertEqual(ResearchProjectStatus.archived.label, "Archived")
    }

    func testPlanStatusLabelsAndCases() {
        XCTAssertEqual(ResearchPlanStatus.allCases,
                       [.draft, .active, .completed, .cancelled])
        XCTAssertEqual(ResearchPlanStatus.draft.label, "Draft")
        XCTAssertEqual(ResearchPlanStatus.cancelled.label, "Cancelled")
    }

    func testStepStatusLabelsAndCases() {
        XCTAssertEqual(ResearchStepStatus.allCases,
                       [.pending, .completed, .failed, .skipped])
        XCTAssertEqual(ResearchStepStatus.failed.label, "Failed")
        XCTAssertEqual(ResearchStepStatus.skipped.label, "Skipped")
    }

    // MARK: - ResearchStepTool: wire raw value ↔ display label

    func testStepToolRawValues() {
        XCTAssertEqual(ResearchStepTool.webSearch.rawValue, "web_search")
        XCTAssertEqual(ResearchStepTool.browserNavigate.rawValue, "browser_navigate")
        XCTAssertEqual(ResearchStepTool.documentFetch.rawValue, "document_fetch")
        XCTAssertEqual(ResearchStepTool.localSearch.rawValue, "local_search")
    }

    func testStepToolLabels() {
        XCTAssertEqual(ResearchStepTool.webSearch.label, "Web Search")
        XCTAssertEqual(ResearchStepTool.browserNavigate.label, "Browser")
        XCTAssertEqual(ResearchStepTool.documentFetch.label, "Document Fetch")
        XCTAssertEqual(ResearchStepTool.localSearch.label, "Local Search")
    }

    func testStepToolDecodesFromWireRawValue() throws {
        let decoded = try JSONDecoder().decode(ResearchStepTool.self,
                                         from: Data("\"web_search\"".utf8))
        XCTAssertEqual(decoded, .webSearch)
    }

    // MARK: - Struct snake_case CodingKeys mapping

    func testResearchTaskDecodesSnakeCaseKeys() throws {
        let json = Data("""
        {
            "id": "task-1",
            "plan_id": "plan-9",
            "name": "Read sources",
            "description": "",
            "status": "in_progress",
            "priority": 2,
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-11T10:00:00Z"
        }
        """.utf8)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let task = try decoder.decode(ResearchTask.self, from: json)
        XCTAssertEqual(task.id, "task-1")
        XCTAssertEqual(task.planId, "plan-9")   // ← snake_case key mapped
        XCTAssertEqual(task.status, .inProgress)
        XCTAssertEqual(task.priority, 2)
    }

    func testResearchStepDecodesSnakeCaseKeys() throws {
        let json = Data("""
        {
            "id": "step-1",
            "task_id": "task-7",
            "tool": "local_search",
            "label": "Search library",
            "description": "",
            "status": "completed",
            "order_index": 3
        }
        """.utf8)
        let step = try JSONDecoder().decode(ResearchStep.self, from: json)
        XCTAssertEqual(step.taskId, "task-7")      // ← task_id
        XCTAssertEqual(step.orderIndex, 3)          // ← order_index
        XCTAssertEqual(step.tool, .localSearch)
        XCTAssertEqual(step.status, .completed)
    }

    func testBrowserSaveResponseDecodesSnakeCaseKeys() throws {
        let json = Data("""
        {
            "success": true,
            "document_id": "doc-1",
            "document_name": "Saved Page",
            "file_path": "/a/b.pdf",
            "content_type": "application/pdf",
            "size_bytes": 4096
        }
        """.utf8)
        let resp = try JSONDecoder().decode(BrowserSaveResponse.self, from: json)
        XCTAssertTrue(resp.success)
        XCTAssertEqual(resp.documentId, "doc-1")
        XCTAssertEqual(resp.filePath, "/a/b.pdf")
        XCTAssertEqual(resp.sizeBytes, 4096)
        XCTAssertNil(resp.error)
    }

    /// The optional fields on a failure response stay nil without throwing.
    func testBrowserSaveResponseFailureLeavesOptionalsNil() throws {
        let json = Data("""
        { "success": false, "error": "timeout" }
        """.utf8)
        let resp = try JSONDecoder().decode(BrowserSaveResponse.self, from: json)
        XCTAssertFalse(resp.success)
        XCTAssertEqual(resp.error, "timeout")
        XCTAssertNil(resp.documentId)
        XCTAssertNil(resp.sizeBytes)
    }

    func testBrowserSaveRequestEncodesSnakeCaseKeys() throws {
        let req = BrowserSaveRequest(url: "https://x.test",
                                     projectId: "proj-1",
                                     suggestedName: "Note",
                                     parentFolderId: nil)
        let data = try JSONEncoder().encode(req)
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(obj["project_id"] as? String, "proj-1")
        XCTAssertEqual(obj["suggested_name"] as? String, "Note")
        XCTAssertNil(obj["parentFolderId"])  // never the camelCase form
    }
}
