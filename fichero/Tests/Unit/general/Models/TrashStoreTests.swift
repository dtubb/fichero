//
//  TrashStoreTests.swift
//  FicheroTests
//
//  The app half of the Trash (`docs/contributor_manual/specs/safety/trash.md`, #2077, #5243):
//  `safety.trash.a-place-in-the-sidebar`, `safety.trash.lists-what-and-why`, `safety.trash.put-back`,
//  `safety.trash.empty-names-moved-items`. Driven through the real store and the generated client
//  against a stub scoped to /api/documents/trash and /restore, replying with the shapes the engine's
//  own `api/routes/document/trash.py` answers, so no other suite's requests race it.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class TrashMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    nonisolated(unsafe) static var requests: [String] = []
    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/documents/trash") || path.hasSuffix("/restore")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = TrashMockURLProtocol.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet)); return }
        TrashMockURLProtocol.requests.append("\(request.httpMethod ?? "") \(request.url?.path ?? "")")
        do { let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

/// Engine-shaped JSON for the Trash routes.
private enum TrashJSON {
    static func item(
        _ id: String, _ name: String, docType: String = "file", itemCount: Int = 0,
        fromWhere: String = "Box 3", reason: String = "deleted", why: String = "Deleted by ana"
    ) -> String {
        """
        {"id": "\(id)", "name": "\(name)", "doc_type": "\(docType)",
         "deleted_at": "2026-10-10T14:02:00Z", "deleted_by": "ana", "item_count": \(itemCount),
         "from_folder_id": "box-3", "from_folder_path": "Box 3", "from_folder_state": "live",
         "from_where": "\(fromWhere)", "reason": "\(reason)",
         "moved_to_project": \(reason == "moved" ? "\"Istmina\"" : "null"), "moved_on": null,
         "transfer_id": null, "why": "\(why)",
         "document": {"id": "\(id)", "name": "\(name)", "expected_thumbnail_path": "t", "expected_display_path": "d"}}
        """
    }

    static func list(_ items: [String]) -> String {
        #"{"items": ["# + items.joined(separator: ",") + #"], "count": \#(items.count), "total": \#(items.count), "withheld": 0}"#
    }

    static let folder = item("folder", "Letters", docType: "folder", itemCount: 40)
    static let moved = item(
        "page", "page-12.jpg", fromWhere: "Box 3 / Letters", reason: "moved", why: "Moved to Istmina on 10 Oct 2026"
    )

    static let putBack = """
    {"restored_document_ids": ["page"], "folder_id": "sources", "folder_name": "Sources", "into_sources": true,
     "folder_in_trash_id": "folder", "message": "Put back in Sources: its folder is in the Trash."}
    """

    static let preview = """
    {"items": 2, "documents": 42, "statements": 3,
     "moved": [{"project": "Istmina", "count": 1, "moved_on": "2026-10-10T14:02:00Z",
                "sentence": "1 of these was moved to Istmina on 10 Oct 2026; emptying makes that move permanent."}],
     "sentence": "Delete 2 items for good? This cannot be undone."}
    """

    static let emptied = """
    {"items": 2, "documents": 42, "statements": 3, "moved": [], "sentence": "Delete 2 items for good? This cannot be undone.",
     "deleted_document_ids": ["folder", "page"], "entities_pruned": 0}
    """
}

@MainActor
@Suite(.serialized, .tags(.sidebar))
struct TrashStoreTests {
    private let projectId = UUID(uuidString: "6F2A0A6E-2C2B-4B49-9E9B-000000005243")!

    /// `listing` is what GET /api/documents/trash answers, each time it is asked.
    private func makeStore(listing: @escaping () -> String) -> TrashStore {
        TrashMockURLProtocol.requests = []
        TrashMockURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            switch (request.httpMethod ?? "GET", path) {
            case ("GET", "/api/documents/trash"): return Self.reply(request, 200, listing())
            case ("GET", "/api/documents/trash/empty"): return Self.reply(request, 200, TrashJSON.preview)
            case ("POST", "/api/documents/trash/empty"): return Self.reply(request, 200, TrashJSON.emptied)
            default: return Self.reply(request, 200, TrashJSON.putBack)
            }
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [TrashMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: configuration)
        )
        return TrashStore(client: client)
    }

    private static func reply(_ request: URLRequest, _ status: Int, _ json: String) -> (HTTPURLResponse, Data) {
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        return (response, Data(json.utf8))
    }

    @Test("safety.trash.lists-what-and-why: the Trash lists what, when, who, where it was, and why")
    func listsWhatAndWhy() async {
        // WHY: the Trash is where a person decides what to bring back; without where a thing was and
        // why it is here, a page a move sent here reads as one someone deleted.
        let store = makeStore { TrashJSON.list([TrashJSON.folder, TrashJSON.moved]) }
        await store.load()

        #expect(TrashMockURLProtocol.requests == ["GET /api/documents/trash"])
        #expect(store.entries.map(\.name) == ["Letters", "page-12.jpg"])
        let folder = store.entries[0]
        #expect(folder.isFolder && folder.itemCount == 40 && folder.contentsText == "40 items inside")
        #expect(folder.deletedBy == "ana" && folder.deletedAt != nil)
        #expect(folder.why == "Deleted by ana" && !folder.wasMoved)
        #expect(folder.whereAndWhenText.hasPrefix("From Box 3 · "))
        let moved = store.entries[1]
        #expect(moved.why == "Moved to Istmina on 10 Oct 2026" && moved.wasMoved)
        #expect(moved.contentsText == nil)
        #expect(!store.isEmpty && store.errorMessage == nil)
    }

    @Test("a reload merges by id: the unchanged entry stays, a gone one leaves, a new one arrives in place")
    func reloadMergesOneEntryAtATime() async {
        // WHY: a delete elsewhere reloads the Trash; a wholesale replace would reset the person's
        // selection and scroll (no wholesale re-render).
        var listing = TrashJSON.list([TrashJSON.folder, TrashJSON.moved])
        let store = makeStore { listing }
        await store.load()
        let folderBefore = store.entries[0]

        listing = TrashJSON.list([TrashJSON.item("new", "new.jpg"), TrashJSON.folder])
        await store.load()

        #expect(store.entries.map(\.id) == ["new", "folder"])
        #expect(store.entries[1] == folderBefore)
    }

    @Test("safety.trash.put-back: Put Back removes that entry and shows the engine's sentence")
    func putBackRemovesTheEntryAndSaysWhere() async {
        // WHY: the person must be told when a thing went to Sources rather than its own folder, or
        // they would look for it where it was.
        let store = makeStore { TrashJSON.list([TrashJSON.folder, TrashJSON.moved]) }
        await store.load()

        let said = await store.putBack(["page"])

        #expect(TrashMockURLProtocol.requests.last == "POST /api/documents/page/restore")
        #expect(said == "Put back in Sources: its folder is in the Trash.")
        #expect(store.notice == "Put back in Sources: its folder is in the Trash.")
        #expect(store.entries.map(\.id) == ["folder"])
    }

    @Test("safety.trash.empty-names-moved-items: Empty Trash asks first, naming the moved items, then empties")
    func emptyTrashAsksFirstThenEmpties() async {
        // WHY: emptying cannot be undone and makes a move permanent; nothing may go before the person
        // has read that and said yes.
        let store = makeStore { TrashJSON.list([TrashJSON.folder, TrashJSON.moved]) }
        await store.load()

        await store.askToEmpty()
        let question = store.emptyQuestion
        #expect(question?.question == "Delete 2 items for good? This cannot be undone.")
        #expect(question?.movedSentences == [
            "1 of these was moved to Istmina on 10 Oct 2026; emptying makes that move permanent."
        ])
        #expect(!TrashMockURLProtocol.requests.contains("POST /api/documents/trash/empty"))
        #expect(store.entries.count == 2)

        store.cancelEmpty()
        #expect(store.emptyQuestion == nil && store.entries.count == 2)

        await store.askToEmpty()
        await store.confirmEmpty()
        #expect(TrashMockURLProtocol.requests.last == "POST /api/documents/trash/empty")
        #expect(store.isEmpty && store.emptyQuestion == nil)
        #expect(store.notice == "Deleted 42 items for good.")
    }

    @Test("Put Back and Empty Trash… are enabled only when they can act")
    func verbsEnableWhenTheyCanAct() {
        // WHY: the Edit menu and the context menu render the same components; a verb that could not
        // act must read as disabled in both.
        let empty = TrashStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero"))
        let full = TrashStore(
            client: FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero"),
            entries: [TrashEntry(id: "a", name: "a.jpg", fromWhere: "Box 3", why: "Deleted by ana")]
        )
        #expect(!PutBackButton.isEnabled(nil))
        #expect(!PutBackButton.isEnabled(TrashActionsTarget(store: full, selection: [])))
        #expect(PutBackButton.isEnabled(TrashActionsTarget(store: full, selection: ["a"])))
        #expect(!PutBackButton.isEnabled(TrashActionsTarget(store: full, selection: ["not-in-the-trash"])))
        #expect(!EmptyTrashButton.isEnabled(nil))
        #expect(!EmptyTrashButton.isEnabled(empty))
        #expect(EmptyTrashButton.isEnabled(full))
    }

    @Test("safety.trash.a-place-in-the-sidebar: each project's Trash row has its own destination")
    func eachProjectHasItsOwnTrashRow() {
        // WHY: a project's Trash lists only that project's deleted items; two projects' rows sharing a
        // selection identity would open the wrong Trash.
        let other = UUID()
        let mine = SidebarDestination.trash(libraryId: projectId)
        #expect(SidebarDestination(serializedID: mine.serializedID) == mine)
        #expect(mine != SidebarDestination.trash(libraryId: other))
        #expect(SidebarDestination.trashLibraryId(forSerializedID: mine.serializedID) == projectId)
        #expect(SidebarDestination.trashLibraryId(forSerializedID: "library:\(projectId.uuidString)") == nil)
        #expect(SidebarDestination.trashLibraryId(forSerializedID: nil) == nil)
        // The Library pane lists the project, never an outline fetched for "trash:<uuid>".
        #expect(
            SidebarSourceOpen.libraryPaneFolderId(
                selectedItemId: mine.serializedID, viewMode: .library(nil), libraryId: other
            ) == SidebarDestination.library(projectId).serializedID
        )
        #expect(!SidebarView.droppedRowIsMomentarilyMissing(mine, cachedItemMissing: true, wasRecentlyDeleted: false))
        #expect(SidebarTrashRow.name == "Trash")
        #expect(SidebarTrashRow.systemImage(isEmpty: true) == "trash")
        #expect(SidebarTrashRow.systemImage(isEmpty: false) == "trash.fill")
    }

    @Test("the Trash row ends every project's section, the always-there project's too")
    func trashRowEndsEveryProjectSection() throws {
        // WHY: ruled 2026-10-10: the Trash is the last row of each project's section and of the top
        // section; both draw `unifiedLibrarySections`, so the row must be drawn there, after Models.
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift"
            ),
            encoding: .utf8
        )
        let sections = try #require(source.components(separatedBy: "func unifiedLibrarySections(").dropFirst().first)
        let body = sections.components(separatedBy: "private func flattenedLibraryItems(").first ?? ""
        let models = try #require(body.range(of: "SidebarTrainingNode(store: library.trainedModelsStore"))
        let trash = try #require(body.range(of: "SidebarTrashRow(store: library.trashStore, libraryId: libraryId)"))
        #expect(models.upperBound < trash.lowerBound)
    }
}
