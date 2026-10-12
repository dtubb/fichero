import FicheroAPIClient
import Foundation
@testable import Fichero
import Testing

/// The engine for these tests: only the transport is stubbed; the services and the generated client are the real
/// ones. It records each request with its JSON body.
private final class ItemVerbsEngine: URLProtocol {
    struct Seen { let method: String; let path: String; let body: [String: Any] }
    private static let lock = NSLock()
    nonisolated(unsafe) private static var seen: [Seen] = []

    static func reset() {
        lock.lock()
        seen = []
        lock.unlock()
    }

    static func recorded() -> [Seen] {
        lock.lock()
        defer { lock.unlock() }
        return seen
    }

    override static func canInit(with request: URLRequest) -> Bool { request.url?.host == "item-verbs.test" }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let path = request.url?.path ?? ""
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.lock.lock()
        Self.seen.append(Seen(method: request.httpMethod ?? "", path: path, body: body))
        Self.lock.unlock()
        var status = 200
        var json = "{}"
        if path == "/api/documents/batch-exclude" {
            json = #"{"updated":0,"document_ids":[]}"#
        } else if path.hasSuffix("/ungroup") {
            json = "[]"
        } else {
            status = 404
            json = #"{"detail":"no stub"}"#
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

/// #5652 slice 4, group 1: Rename, Delete, Exclude / Include, Bookmark…, Add to Workspace…, Export a Copy…, Group
/// and Ungroup are one item each, which the sidebar's and the Items list's context menus and Edit / File render on
/// one `ItemVerbsTarget`. What breaks without these: an item on when it can do nothing (or off with no word), a title
/// that says Exclude over documents already excluded, the bar acting on the sidebar when Items has focus, or the
/// shared operation sending the wrong scope or name.
@MainActor
@Suite("The item verbs, one component each (#5652 slice 4)", .serialized)
struct ItemVerbsMenuTests {
    private let page = Document(id: "p1", docType: .file, fileType: .image, name: "0970.jpg")
    private let excludedPage = Document(id: "p2", docType: .file, fileType: .image, name: "0971.jpg",
                                        excludeFromProcessing: true, excludeFromSearch: true)
    private let folder = Document(id: "f1", docType: .folder, name: "Letters")

    private func target(_ documents: [Document], allActions: Bool = true) -> ItemVerbsTarget {
        var target = ItemVerbsTarget(ids: documents.map(\.id), documents: documents)
        guard allActions else { return target }
        target.deletableCount = documents.count
        target.delete = {}
        target.setExcluded = { _, _ in }
        if documents.count == 1 {
            target.rename = {}
            target.bookmark = {}
            target.addToWorkspace = {}
            if documents.first?.docType != .folder { target.export = {} }
        }
        return target
    }

    private func services() -> (DocumentService, DocumentStore) {
        ItemVerbsEngine.reset()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ItemVerbsEngine.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://item-verbs.test")!, libraryPath: "/tmp/item-verbs.fichero",
            session: URLSession(configuration: configuration)
        )
        return (DocumentService(ficheroClient: client), DocumentStore(apiClient: APIClient(client: client)))
    }

    @Test("with nothing selected every verb is off, and says so once")
    func nothingSelected() {
        #expect(ItemVerbs.renameReason(nil) == ItemVerbs.nothingSelected)
        #expect(ItemVerbs.deleteReason(nil) == ItemVerbs.nothingSelected)
        #expect(ItemVerbs.excludeReason(nil) == ItemVerbs.nothingSelected)
        #expect(ItemVerbs.bookmarkReason(nil) == ItemVerbs.nothingSelected)
        #expect(ItemVerbs.exportReason(nil) == ItemVerbs.nothingSelected)
        #expect(ItemVerbs.renameReason(ItemVerbsTarget(ids: [], documents: [])) == ItemVerbs.nothingSelected)
    }

    @Test("one document: every verb acts")
    func oneDocument() {
        let one = target([page])
        #expect(ItemVerbs.renameReason(one) == nil)
        #expect(ItemVerbs.deleteReason(one) == nil)
        #expect(ItemVerbs.excludeReason(one) == nil)
        #expect(ItemVerbs.bookmarkReason(one) == nil)
        #expect(ItemVerbs.addToWorkspaceReason(one) == nil)
        #expect(ItemVerbs.exportReason(one) == nil)
        #expect(ItemVerbs.deleteTitle(one.deletableCount) == "Delete")
    }

    @Test("several documents: Delete and Exclude act on all, the one-document verbs say why not")
    func severalDocuments() {
        let two = target([page, excludedPage])
        #expect(ItemVerbs.deleteReason(two) == nil)
        #expect(ItemVerbs.deleteTitle(two.deletableCount) == "Delete 2 Items")
        #expect(ItemVerbs.excludeReason(two) == nil)
        #expect(ItemVerbs.renameReason(two) == "Select one item to rename")
        #expect(ItemVerbs.bookmarkReason(two) == "Select one document to bookmark")
        #expect(ItemVerbs.addToWorkspaceReason(two) == "Select one document to add to a workspace")
        #expect(ItemVerbs.exportReason(two) == "Select one document to export")
    }

    @Test("a folder has no file to export; a pane that cannot act on a verb says where it can")
    func folderAndPaneReasons() {
        #expect(ItemVerbs.exportReason(target([folder])) == "A folder has no file to export")
        let bare = target([page], allActions: false)
        #expect(ItemVerbs.renameReason(bare) == "This item cannot be renamed")
        #expect(ItemVerbs.deleteReason(bare) == "Nothing selected can be deleted")
        #expect(ItemVerbs.excludeReason(bare) == "Select documents in Items to exclude them")
        #expect(ItemVerbs.bookmarkReason(bare) == "Select the document in Items to bookmark it")
        let workflow = ItemVerbsTarget(ids: ["wf-1"], documents: [])
        #expect(ItemVerbs.excludeReason(workflow) == "Only documents and folders can be excluded")
    }

    @Test("Exclude says Include once every document is already excluded, and the press sets the other way")
    func exclusionWords() {
        #expect(ItemVerbs.exclusionTitle([page], .processing) == "Exclude from Processing")
        #expect(ItemVerbs.exclusionTitle([excludedPage], .processing) == "Include in Processing")
        #expect(ItemVerbs.exclusionTitle([excludedPage], .search) == "Include in Search")
        #expect(ItemVerbs.exclusionTitle([excludedPage], .everywhere) == "Include Everywhere")
        // A mixed selection is not all excluded: the press excludes the rest.
        #expect(ItemVerbs.exclusionTitle([page, excludedPage], .everywhere) == "Exclude Everywhere")
        #expect(ItemVerbs.pressExcludes([page, excludedPage], .processing))
        #expect(!ItemVerbs.pressExcludes([excludedPage], .search))
        #expect(ItemVerbs.Exclusion.everywhere.scopes == [.processing, .search])
    }

    /// Group 7: the dataset rows' fixed verbs and the Inspector's one-document toggle take the same words.
    @Test("the words for a known way are the same the menus use for documents")
    func exclusionWordsForAKnownWay() {
        #expect(ItemVerbs.exclusionTitle(.processing, including: false) == "Exclude from Processing")
        #expect(ItemVerbs.exclusionTitle(.processing, including: true) == "Include in Processing")
        #expect(ItemVerbs.exclusionTitle(.everywhere, including: true) == ItemVerbs.exclusionTitle([excludedPage], .everywhere))
        #expect(ItemVerbs.exclusionImage(.processing, including: true) == ItemVerbs.exclusionImage([excludedPage], .processing))
    }

    @Test("a surface with no store of its own (the dataset rows) still excludes through the one operation")
    func setExcludedWithoutAStore() async throws {
        let (service, _) = services()
        try await ItemVerbs.setExcluded(["p1"], excluded: false, .everywhere, using: service, refreshing: nil)
        let sent = ItemVerbsEngine.recorded().filter { $0.path == "/api/documents/batch-exclude" }
        #expect(sent.map { $0.body["scope"] as? String } == ["processing", "search"])
        #expect(sent.allSatisfy { ($0.body["excluded"] as? Bool) == false })
    }

    @Test("titles use the ellipsis character where more is asked, never three dots")
    func terminology() {
        for title in [ItemVerbs.bookmarkTitle, ItemVerbs.addToWorkspaceTitle, ItemVerbs.exportTitle] {
            #expect(title.hasSuffix("…") && !title.contains("..."), "\(title)")
        }
        #expect(ItemGrouping.groupTitle == "Group" && ItemGrouping.ungroupTitle == "Ungroup")
        #expect(ItemGrouping.name(count: 3) == "Group of 3")
    }

    @Test("the bar acts on the focused Items list first, else the sidebar's selection through its own actions")
    func barTarget() {
        let items = target([page])
        #expect(FocusedItemVerbs.target(items: items, actions: nil, info: nil) == items)
        #expect(FocusedItemVerbs.target(items: nil, actions: nil, info: nil) == nil)

        var renamed = 0
        var deleted = 0
        let actions = SidebarActions(
            createFolder: {}, importFiles: { _ in }, renameItem: { renamed += 1 }, deleteItem: { deleted += 1 },
            createChat: {}, createWorkflow: {}, createChain: {}, createComparison: {}, createSchedule: {},
            createTrigger: {}, openSelectionInNewTab: {}, openSelectionInNewWindow: {}
        )
        let row = SidebarItem(
            id: "doc:p1", name: page.name, icon: "doc", category: .folder, itemType: .document(page),
            children: nil, libraryId: UUID(), folderPath: "/", sortOrder: 0, isFolder: false
        )
        let info = SidebarSelectionInfo(selectedItem: row, canRename: true, canDelete: true, deletableCount: 1)
        let sidebar = FocusedItemVerbs.target(items: nil, actions: actions, info: info)
        #expect(sidebar?.documents.map(\.id) == ["p1"])
        sidebar?.rename?()
        sidebar?.delete?()
        #expect(renamed == 1 && deleted == 1)
        // The pickers and Export a Copy are the Items list's: the sidebar's selection says so.
        #expect(ItemVerbs.bookmarkReason(sidebar) == "Select the document in Items to bookmark it")
        #expect(ItemVerbs.exportReason(sidebar) == "Select the document in Items to export it")
    }

    @Test("Exclude Everywhere sends both scopes for the selected documents")
    func setExcludedSendsBothScopes() async throws {
        let (service, store) = services()
        try await ItemVerbs.setExcluded(["p1", "p2"], excluded: true, .everywhere, using: service, refreshing: store)
        let sent = ItemVerbsEngine.recorded().filter { $0.path == "/api/documents/batch-exclude" }
        #expect(sent.map { $0.body["scope"] as? String } == ["processing", "search"])
        #expect(sent.allSatisfy { ($0.body["document_ids"] as? [String]) == ["p1", "p2"] })
        #expect(sent.allSatisfy { ($0.body["excluded"] as? Bool) == true })
    }

    @Test("Group names the node by its count; Ungroup asks the engine for that group")
    func grouping() async throws {
        let (service, store) = services()
        await #expect(throws: (any Error).self) {
            // The stub refuses the create: what matters is what was asked.
            try await ItemGrouping.group(["p1", "p2"], using: service, refreshing: store)
        }
        let create = try #require(ItemVerbsEngine.recorded().first { $0.path == "/api/documents/groups" })
        #expect(create.body["name"] as? String == "Group of 2")
        #expect(create.body["child_ids"] as? [String] == ["p1", "p2"])

        try await ItemGrouping.ungroup("g1", using: service, refreshing: store)
        #expect(ItemVerbsEngine.recorded().contains { $0.method == "POST" && $0.path == "/api/documents/groups/g1/ungroup" })
    }
}
