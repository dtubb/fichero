@testable import Fichero
import XCTest

/// Tests for the `Workflow` UI model and `WorkflowInputSource` enum.
/// Locks: WorkflowInputSource raw values (UI persistence + API contract),
/// Workflow ↔ WorkflowDefinition round-trip (toAPIFormat / init-from-api),
/// default values matching what the workflow editor expects.
final class WorkflowModelTests: XCTestCase {

    // MARK: - WorkflowInputSource

    func testInputSourceRawValues() {
        XCTAssertEqual(WorkflowInputSource.collection.rawValue, "collection")
        XCTAssertEqual(
            WorkflowInputSource.currentSelection.rawValue,
            "current_selection"
        )
    }

    func testInputSourceAllCases() {
        XCTAssertEqual(WorkflowInputSource.allCases.count, 2)
    }

    func testInputSourceDisplayName() {
        XCTAssertEqual(WorkflowInputSource.collection.displayName, "Entire Collection")
        XCTAssertEqual(
            WorkflowInputSource.currentSelection.displayName,
            "Selected Documents"
        )
    }

    func testInputSourceIcon() {
        XCTAssertEqual(WorkflowInputSource.collection.icon, "folder")
        XCTAssertEqual(
            WorkflowInputSource.currentSelection.icon,
            "checkmark.circle"
        )
    }

    func testInputSourceHelpTextNonEmpty() {
        for source in WorkflowInputSource.allCases {
            XCTAssertFalse(source.helpText.isEmpty)
        }
    }

    // MARK: - Workflow defaults

    func testWorkflowDefaults() {
        let wf = Workflow(name: "Test Workflow")
        XCTAssertFalse(wf.id.isEmpty)
        XCTAssertEqual(wf.name, "Test Workflow")
        XCTAssertEqual(wf.description, "")
        XCTAssertEqual(wf.provider, "")
        XCTAssertEqual(wf.model, "")
        XCTAssertEqual(wf.nodes.count, 0)
        XCTAssertEqual(wf.edges.count, 0)
        XCTAssertEqual(wf.folderPath, "/")
        XCTAssertEqual(wf.sortOrder, 0)
        XCTAssertEqual(wf.inputSource, .collection)
        XCTAssertFalse(wf.isSystem)
    }

    // MARK: - Round-trip via WorkflowDefinition

    func testWorkflowToAPIFormatPreservesFields() {
        let wf = Workflow(
            id: "wf-1",
            name: "Catalogue",
            description: "Process docs",
            provider: "openai",
            model: "gpt-4o",
            folderPath: "/Catalogue",
            sortOrder: 5,
            inputSource: .currentSelection,
            isSystem: true
        )
        let api = wf.toAPIFormat()
        XCTAssertEqual(api.id, "wf-1")
        XCTAssertEqual(api.name, "Catalogue")
        XCTAssertEqual(api.description, "Process docs")
        XCTAssertEqual(api.provider, "openai")
        XCTAssertEqual(api.model, "gpt-4o")
        XCTAssertEqual(api.folderPath, "/Catalogue")
        XCTAssertEqual(api.sortOrder, 5)
        XCTAssertEqual(api.inputSource, .currentSelection)
        XCTAssertTrue(api.isSystem)
    }

    func testWorkflowFromAPIRoundTrip() {
        let api = WorkflowDefinition(
            id: "wf-1",
            name: "Test",
            description: "desc",
            provider: "anthropic",
            model: "claude",
            folderPath: "/x",
            sortOrder: 7,
            inputSource: .currentSelection,
            isSystem: false
        )
        let wf = Workflow(from: api)
        XCTAssertEqual(wf.id, "wf-1")
        XCTAssertEqual(wf.provider, "anthropic")
        XCTAssertEqual(wf.sortOrder, 7)
        XCTAssertEqual(wf.inputSource, .currentSelection)
    }

    func testFullRoundTrip() {
        let original = Workflow(
            id: "wf-99",
            name: "Round trip",
            description: "test",
            provider: "p",
            model: "m",
            folderPath: "/test",
            sortOrder: 3,
            inputSource: .collection,
            isSystem: true
        )
        let restored = Workflow(from: original.toAPIFormat())
        XCTAssertEqual(original, restored)
    }

    // MARK: - WorkflowDefinition decode with missing optional fields

    func testWorkflowDefinitionDecodesWithMissingOptionalFields() throws {
        // The Python backend may not always include every field.
        // The custom init(from:) decoder fills defaults — this is the
        // backwards-compat contract.
        let json = """
        {
            "id": "wf-1",
            "name": "Minimal"
        }
        """.data(using: .utf8)!
        let def = try JSONDecoder().decode(WorkflowDefinition.self, from: json)
        XCTAssertEqual(def.id, "wf-1")
        XCTAssertEqual(def.name, "Minimal")
        XCTAssertEqual(def.description, "")    // default
        XCTAssertEqual(def.folderPath, "/")    // default
        XCTAssertEqual(def.sortOrder, 0)       // default
        XCTAssertEqual(def.inputSource, .collection)  // default
        XCTAssertFalse(def.isSystem)           // default
        XCTAssertEqual(def.timeoutSeconds, 300)
        XCTAssertEqual(def.maxRetries, 3)
        XCTAssertEqual(def.version, "1.0")
    }

    func testWorkflowDefinitionDecodesSnakeCaseFields() throws {
        let json = """
        {
            "id": "wf-1",
            "name": "Test",
            "folder_path": "/Catalogue",
            "sort_order": 10,
            "input_source": "current_selection",
            "is_system": true,
            "timeout_seconds": 600,
            "max_retries": 5,
            "created_at": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let def = try JSONDecoder().decode(WorkflowDefinition.self, from: json)
        XCTAssertEqual(def.folderPath, "/Catalogue")
        XCTAssertEqual(def.sortOrder, 10)
        XCTAssertEqual(def.inputSource, .currentSelection)
        XCTAssertTrue(def.isSystem)
        XCTAssertEqual(def.timeoutSeconds, 600)
        XCTAssertEqual(def.maxRetries, 5)
        XCTAssertEqual(def.createdAt, "2026-05-10T10:00:00Z")
    }
}
