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

    func testNoteServiceWiresBacklinksAndForwardLinks() throws {
        // #1433: the two note-relation endpoints must be called through the typed
        // client (a hand-written service consumer = "wired" per check_ui_wiring).
        let source = try Self.appSource("Services/NoteService.swift")
        XCTAssertTrue(source.contains("client.api.backlinksApiNotesNoteIdBacklinksGet"))
        XCTAssertTrue(source.contains("client.api.forwardLinksApiNotesNoteIdForwardLinksGet"))
        XCTAssertTrue(source.contains("func backlinks(noteId: String)"))
        XCTAssertTrue(source.contains("func forwardLinks(noteId: String)"))
    }

    func testNoteStoreExposesLinksAndDetailViewSurfacesThem() throws {
        // The store is the single accessor; the detail view renders the section.
        let storeSource = try Self.appSource("Models/NoteStore.swift")
        XCTAssertTrue(storeSource.contains("func links(for noteId: String)"))
        XCTAssertTrue(storeSource.contains("noteService.backlinks(noteId: noteId)"))
        XCTAssertTrue(storeSource.contains("noteService.forwardLinks(noteId: noteId)"))

        let detailSource = try Self.appSource("Views/Inspector/Notes/NoteDetailView.swift")
        XCTAssertTrue(detailSource.contains("linksSection(item)"))
        XCTAssertTrue(detailSource.contains("Backlinks"))
        XCTAssertTrue(detailSource.contains("Forward links"))

        // The inspector pane must feed the loader (otherwise the section is dead).
        let paneSource = try Self.appSource("Views/Inspector/Notes/NotesInspectorPane.swift")
        XCTAssertTrue(paneSource.contains("@Environment(NoteStore.self) private var noteStore"))
        XCTAssertTrue(paneSource.contains("InspectorListDetailSplit {"))
        XCTAssertFalse(paneSource.contains("LibraryManager.shared"))
        XCTAssertTrue(paneSource.contains("onLoadLinks:"))
        XCTAssertTrue(paneSource.contains("noteStore.links(for: noteId)"))
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
        let source = try Self.appSource("Views/Inspector/Document/Notes/DocumentNotesTab.swift")

        // Loading and creation now go through NoteStore after the store migration.
        XCTAssertTrue(source.contains("await noteStore.loadNotes(forFolder: document.id)"))
        XCTAssertTrue(source.contains("await noteStore.loadNotes(forPage: document.id)"))
        XCTAssertTrue(source.contains("try await noteStore.createForFolder(document.id, body: body)"))
        XCTAssertTrue(source.contains("try await noteStore.createForPage(document.id, body: body)"))
        XCTAssertTrue(source.contains("await loadNotes()"))
    }

    func testNotesInspectorUsesLowerDetailSplit() throws {
        let source = try Self.appSource("Views/Inspector/Notes/NotesInspectorPane.swift")

        XCTAssertTrue(source.contains("InspectorListDetailSplit {"))
        XCTAssertFalse(source.contains("PlatformHSplitView {"))
    }

    func testNotesBrowserShowsScopeLabelsForScopedNotes() throws {
        // scopeLabel is a computed property on FocusedNote; NotesBrowserView consumes it.
        let viewSource = try Self.appSource("Views/Library/Notes/NotesBrowserView.swift")
        XCTAssertTrue(viewSource.contains("item.scopeLabel"))
        let noteSource = try Self.appSource("Views/Inspector/Notes/FocusedNote.swift")
        XCTAssertTrue(noteSource.contains("if note.folderId?.isEmpty == false { return \"Folder\" }"))
        XCTAssertTrue(noteSource.contains("if note.pageId?.isEmpty == false { return \"Page\" }"))
    }
}
