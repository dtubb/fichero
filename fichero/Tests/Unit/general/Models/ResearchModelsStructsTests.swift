@testable import Fichero
import XCTest

/// Completes ResearchModels coverage: ResearchModelsTests pinned the enums +
/// ResearchTask/ResearchStep decode; this covers the remaining snake_case
/// structs (Project/Plan/Note/Source/Checklist + ChecklistItem). Pure decode,
/// no live engine.
final class ResearchModelsStructsTests: XCTestCase {

    private func isoDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    func testResearchProjectDecodesSnakeCase() throws {
        let json = Data("""
        {
            "id": "p-1", "name": "Diaries", "description": "d",
            "status": "active",
            "library_destination_folder_id": "f-9",
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-11T10:00:00Z"
        }
        """.utf8)
        let project = try isoDecoder().decode(ResearchProject.self, from: json)
        XCTAssertEqual(project.id, "p-1")
        XCTAssertEqual(project.status, .active)
        XCTAssertEqual(project.libraryDestinationFolderId, "f-9")  // ← snake_case
    }

    /// The optional folder id is nil when the key is absent.
    func testResearchProjectNilDestinationFolder() throws {
        let json = Data("""
        {
            "id": "p-2", "name": "N", "description": "", "status": "paused",
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-10T10:00:00Z"
        }
        """.utf8)
        let project = try isoDecoder().decode(ResearchProject.self, from: json)
        XCTAssertNil(project.libraryDestinationFolderId)
        XCTAssertEqual(project.status, .paused)
    }

    func testResearchPlanDecodesSnakeCase() throws {
        let json = Data("""
        {
            "id": "pl-1", "project_id": "p-1", "name": "Phase 1",
            "description": "", "status": "active", "order_index": 2,
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-10T10:00:00Z"
        }
        """.utf8)
        let plan = try isoDecoder().decode(ResearchPlan.self, from: json)
        XCTAssertEqual(plan.projectId, "p-1")   // ← project_id
        XCTAssertEqual(plan.orderIndex, 2)       // ← order_index
        XCTAssertEqual(plan.status, .active)
    }

    func testResearchNoteDecodesSnakeCaseAndTags() throws {
        let json = Data("""
        {
            "id": "n-1", "project_id": "p-1", "task_id": "t-3",
            "note_type": "insight", "content": "c", "tags": ["a", "b"],
            "created_at": "2026-05-10T10:00:00Z"
        }
        """.utf8)
        let note = try isoDecoder().decode(ResearchNote.self, from: json)
        XCTAssertEqual(note.projectId, "p-1")   // ← project_id
        XCTAssertEqual(note.taskId, "t-3")       // ← task_id
        XCTAssertEqual(note.noteType, "insight") // ← note_type
        XCTAssertEqual(note.tags, ["a", "b"])
    }

    func testResearchSourceDecodesSnakeCaseAndOptionalURL() throws {
        let json = Data("""
        {
            "id": "s-1", "project_id": "p-1", "source_type": "web",
            "label": "Site", "description": "d",
            "created_at": "2026-05-10T10:00:00Z"
        }
        """.utf8)
        let source = try isoDecoder().decode(ResearchSource.self, from: json)
        XCTAssertEqual(source.projectId, "p-1")    // ← project_id
        XCTAssertEqual(source.sourceType, "web")    // ← source_type
        XCTAssertNil(source.url)                    // absent optional
    }

    func testResearchChecklistDecodesNestedItems() throws {
        let json = Data("""
        {
            "id": "cl-1", "project_id": "p-1", "task_id": null,
            "title": "Verify", "created_at": "2026-05-10T10:00:00Z",
            "items": [
                {"id": "i-1", "label": "Check A", "checked": true, "notes": ""},
                {"id": "i-2", "label": "Check B", "checked": false, "notes": "todo"}
            ]
        }
        """.utf8)
        let checklist = try isoDecoder().decode(ResearchChecklist.self, from: json)
        XCTAssertEqual(checklist.projectId, "p-1")
        XCTAssertNil(checklist.taskId)          // explicit null → nil
        XCTAssertEqual(checklist.items.count, 2)
        XCTAssertTrue(checklist.items[0].checked)
        XCTAssertEqual(checklist.items[1].notes, "todo")
    }
}
