@testable import Fichero
import XCTest

final class NoteServiceTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testNoteServiceUsesTypedClientAndNoRawHTTP() throws {
        let source = try Self.appSource("Services/NoteService.swift")

        XCTAssertTrue(source.contains("client.api.listNotesApiNotesGet"))
        XCTAssertTrue(source.contains("client.api.createNoteApiNotesPost"))
        XCTAssertTrue(source.contains("client.api.patchNoteApiNotesNoteIdPatch"))
        XCTAssertTrue(source.contains("client.api.deleteNoteApiNotesNoteIdDelete"))
        XCTAssertFalse(source.contains("URLRequest("))
        XCTAssertFalse(source.contains("URLSession"))
        XCTAssertFalse(source.contains("URL(string:"))
    }

    func testNoteServicePreservesPageAndFolderFieldsAndCreatesScopedNotes() throws {
        let source = try Self.appSource("Services/NoteService.swift")

        XCTAssertTrue(source.contains("return generated"))
        XCTAssertTrue(source.contains("await load(query: .init(pageId: pageId))"))
        XCTAssertTrue(source.contains("await load(query: .init(folderId: folderId))"))
        XCTAssertTrue(source.contains("pageId: pageId"))
        XCTAssertTrue(source.contains("folderId: folderId"))
    }

    func testDocumentNotesTabChoosesFolderAndPageScopeFromDocumentType() throws {
        let source = try Self.appSource("Views/Library/DocumentInspector/DocumentNotesTab.swift")

        XCTAssertTrue(source.contains("await service.load(folderId: document.id)"))
        XCTAssertTrue(source.contains("await service.load(pageId: document.id)"))
        XCTAssertTrue(source.contains("service.create(body: body, folderId: document.id)"))
        XCTAssertTrue(source.contains("service.create(body: body, pageId: document.id)"))
        XCTAssertTrue(source.contains("try await service.delete(noteId: noteId)"))
        XCTAssertTrue(source.contains("await loadNotes()"))
    }

    func testNotesBrowserShowsScopeLabelsForScopedNotes() throws {
        let source = try Self.appSource("Views/Notes/NotesBrowserView.swift")

        XCTAssertTrue(source.contains("if let scopeLabel = noteScopeLabel(note)"))
        XCTAssertTrue(source.contains("if note.folderId?.isEmpty == false { return \"Folder\" }"))
        XCTAssertTrue(source.contains("if note.pageId?.isEmpty == false { return \"Page\" }"))
    }
}
