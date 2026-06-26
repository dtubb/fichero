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

        // Loading and creation now go through NoteStore after the store migration.
        XCTAssertTrue(source.contains("await noteStore.loadNotes(forFolder: document.id)"))
        XCTAssertTrue(source.contains("await noteStore.loadNotes(forPage: document.id)"))
        XCTAssertTrue(source.contains("try await noteStore.createForFolder(document.id, body: body)"))
        XCTAssertTrue(source.contains("try await noteStore.createForPage(document.id, body: body)"))
        XCTAssertTrue(source.contains("await loadNotes()"))
    }

    func testNotesBrowserShowsScopeLabelsForScopedNotes() throws {
        // scopeLabel is a computed property on FocusedNote; NotesBrowserView consumes it.
        let viewSource = try Self.appSource("Views/Notes/NotesBrowserView.swift")
        XCTAssertTrue(viewSource.contains("item.scopeLabel"))
        let noteSource = try Self.appSource("Views/Library/FocusedNote.swift")
        XCTAssertTrue(noteSource.contains("if note.folderId?.isEmpty == false { return \"Folder\" }"))
        XCTAssertTrue(noteSource.contains("if note.pageId?.isEmpty == false { return \"Page\" }"))
    }
}
