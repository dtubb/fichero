//
//  DragDropTests.swift
//  FicheroTests
//
//  Unit tests for drag-and-drop infrastructure:
//    - DragDropModel state transitions
//    - URL validation (file-URL filter used by drop handlers)
//    - ID prefix stripping (extractActualId equivalent)
//    - Circular-drop detection (containsDescendant equivalent)
//
//  These tests cover the logic exercised by Section 12.1 of the QA checklist
//  without requiring a live network connection or SwiftUI view instantiation.

@testable import Fichero
import Foundation
import Testing

// MARK: - DragDropModel Tests

@MainActor
struct DragDropModelTests {

    @Test("Initial state is idle")
    func initialState() {
        let model = DragDropModel()
        #expect(!model.isProcessingDrop)
        #expect(model.dropProgress == 0.0)
        #expect(model.dropError == nil)
        #expect(model.dropSuccessCount == 0)
        #expect(model.dropFailureCount == 0)
    }

    @Test("startProcessing sets isProcessingDrop and resets counters")
    func startProcessing() {
        let model = DragDropModel()
        model.dropSuccessCount = 3
        model.dropFailureCount = 1
        model.startProcessing()

        #expect(model.isProcessingDrop)
        #expect(model.dropProgress == 0.0)
        #expect(model.dropSuccessCount == 0)
        #expect(model.dropFailureCount == 0)
    }

    @Test("endProcessing clears isProcessingDrop")
    func endProcessing() {
        let model = DragDropModel()
        model.startProcessing()
        model.endProcessing()
        #expect(!model.isProcessingDrop)
    }

    @Test("updateProgress stores value")
    func updateProgress() {
        let model = DragDropModel()
        model.updateProgress(0.75)
        #expect(model.dropProgress == 0.75)
    }

    @Test("incrementSuccessCount and incrementFailureCount accumulate")
    func counters() {
        let model = DragDropModel()
        model.incrementSuccessCount()
        model.incrementSuccessCount()
        model.incrementFailureCount()
        #expect(model.dropSuccessCount == 2)
        #expect(model.dropFailureCount == 1)
    }

    @Test("setError stores error; clearError removes it")
    func errorLifecycle() {
        let model = DragDropModel()
        let error = ErrorModel(type: .fileSystem, severity: .medium, title: "Import Failed", message: "Cannot access file")
        model.setError(error)
        #expect(model.dropError != nil)
        model.clearError()
        #expect(model.dropError == nil)
    }

    @Test("reset returns model to initial state")
    func resetState() {
        let model = DragDropModel()
        model.startProcessing()
        model.updateProgress(0.5)
        model.incrementSuccessCount()
        model.reset()

        #expect(!model.isProcessingDrop)
        #expect(model.dropProgress == 0.0)
        #expect(model.dropSuccessCount == 0)
        #expect(model.dropFailureCount == 0)
    }

    @Test("operation tracking: start and end operations")
    func operationTracking() {
        let model = DragDropModel()
        #expect(model.getActiveOperationCount() == 0)

        let id1 = model.startOperation()
        let id2 = model.startOperation()
        #expect(model.getActiveOperationCount() == 2)

        model.endOperation(id1)
        #expect(model.getActiveOperationCount() == 1)

        model.endOperation(id2)
        #expect(model.getActiveOperationCount() == 0)
    }

    @Test("reset clears active operations")
    func resetClearsOperations() {
        let model = DragDropModel()
        _ = model.startOperation()
        _ = model.startOperation()
        model.reset()
        #expect(model.getActiveOperationCount() == 0)
    }
}

// MARK: - Drop URL Validation Tests

struct DropURLValidationTests {

    /// Mirrors the filter used in SidebarItemRow.handleExternalFileDrop
    private func filterFileURLs(_ urls: [URL]) -> [URL] {
        urls.filter { $0.isFileURL }
    }

    @Test("file:// URLs pass the isFileURL filter")
    func fileURLsPass() {
        let url = URL(fileURLWithPath: "/tmp/test.pdf")
        let result = filterFileURLs([url])
        #expect(result.count == 1)
    }

    @Test("directory file:// URLs also pass isFileURL (folders are importable)")
    func directoryURLsPass() {
        let url = URL(fileURLWithPath: "/tmp")
        #expect(url.isFileURL)
        let result = filterFileURLs([url])
        #expect(result.count == 1)
    }

    @Test("https:// URLs are rejected by isFileURL filter")
    func httpsURLsRejected() throws {
        let url = try #require(URL(string: "https://example.com/doc.pdf"))
        let result = filterFileURLs([url])
        #expect(result.isEmpty)
    }

    @Test("mixed URL list: only file URLs survive")
    func mixedURLFiltering() throws {
        let fileURL = URL(fileURLWithPath: "/tmp/test.txt")
        let httpsURL = try #require(URL(string: "https://example.com/doc.pdf"))
        let result = filterFileURLs([fileURL, httpsURL])
        #expect(result.count == 1)
        #expect(result[0].isFileURL)
    }

    @Test("empty URL list returns empty")
    func emptyURLList() {
        let result = filterFileURLs([])
        #expect(result.isEmpty)
    }
}

// MARK: - ID Prefix Stripping Tests

/// Exercises the real `extractActualId(from:)` in
/// `SidebarItemRow+Helpers.swift` (free function, not a replica).
struct IDPrefixStrippingTests {

    @Test("doc-prefixed ID strips to raw ID")
    func stripDocPrefix() {
        #expect(extractActualId(from: "doc:abc-123") == "abc-123")
    }

    @Test("folder-prefixed ID strips to raw ID")
    func stripFolderPrefix() {
        #expect(extractActualId(from: "folder:/archive:Search") == "/archive")
    }

    @Test("ID with no prefix is returned as-is")
    func noPrefix() {
        #expect(extractActualId(from: "plain-id-999") == "plain-id-999")
    }

    @Test("workflow-prefixed ID strips to raw ID")
    func stripWorkflowPrefix() {
        #expect(extractActualId(from: "workflow:wf-42") == "wf-42")
    }

    @Test("Cross-view drag: bare UUID from library grid passes through unchanged")
    func crossViewDragBareUUID() {
        // The library grid's `.draggable(doc.id)` (LibraryView+DisplayModes
        // .swift:25,110) emits the bare UUID as its Transferable payload.
        // When the sidebar's `.onDrop(of: [.utf8PlainText, ...])` receives
        // it, the same `extractActualId` normaliser must leave a bare UUID
        // untouched so `moveDocument` gets the right identifier.
        let bareUUID = "8B2F4D6A-1C3E-4F5B-9A7D-0E2C6F8B4A9D"
        #expect(extractActualId(from: bareUUID) == bareUUID)
    }
}

// MARK: - SidebarItemKind Classification Tests (Step 9)

struct SidebarItemKindTests {

    @Test("doc: prefix → .document")
    func docPrefix() {
        #expect(SidebarItemKind(prefixedId: "doc:abc-123") == .document)
    }

    @Test("search: prefix → .savedSearch")
    func searchPrefix() {
        #expect(SidebarItemKind(prefixedId: "search:sv-42") == .savedSearch)
    }

    @Test("chat: prefix → .conversation")
    func chatPrefix() {
        #expect(SidebarItemKind(prefixedId: "chat:c-99") == .conversation)
    }

    @Test("workflow: prefix → .workflow")
    func workflowPrefix() {
        #expect(SidebarItemKind(prefixedId: "workflow:wf-1") == .workflow)
    }

    @Test("chain/schedule/trigger/folder prefixes each resolve to their kind")
    func otherPrefixes() {
        #expect(SidebarItemKind(prefixedId: "chain:x") == .chain)
        #expect(SidebarItemKind(prefixedId: "schedule:s1") == .schedule)
        #expect(SidebarItemKind(prefixedId: "trigger:t1") == .trigger)
        #expect(SidebarItemKind(prefixedId: "folder:/archive") == .folder)
    }

    @Test("bare UUID (no colon) → .document (library grid cross-view drag)")
    func bareUUIDIsDocument() {
        // Library grid emits `doc.id` as a bare UUID via `.draggable`.
        // Classify as .document so the drop handler routes via documentStore.
        #expect(SidebarItemKind(prefixedId: "8B2F4D6A-1C3E-4F5B-9A7D-0E2C6F8B4A9D") == .document)
    }

    @Test("empty string → .unknown")
    func emptyString() {
        #expect(SidebarItemKind(prefixedId: "") == .unknown)
    }

    @Test("unrecognised prefix → .unknown (defensive default)")
    func unknownPrefix() {
        #expect(SidebarItemKind(prefixedId: "asteroid:xyz") == .unknown)
    }
}

// MARK: - Sidebar Drop Classifier Tests

/// Covers the routing-decision logic that was iterating every few minutes
/// on 2026-04-17 (`.mov` bounces, folder bounces, `.jpg` bounces). Pure
/// classification with no NSItemProvider instantiation so the decision
/// is pinned here instead of being rediscovered each time a new UTI
/// pattern turns up.
struct SidebarDropRouteTests {

    private func capability(url: Bool, string: Bool) -> SidebarDropProviderCapability {
        SidebarDropProviderCapability(canLoadURL: url, canLoadString: string)
    }

    @Test("Empty provider list → .reject (no bounce unless there's truly nothing)")
    func emptyProviderList() {
        #expect(sidebarDropRoute(for: []) == .reject)
    }

    @Test("Internal sidebar drag: text-only provider → .internalMove")
    func textOnlyIsInternalMove() {
        // `.draggable(item.id)` emits String via Transferable's utf8-
        // plain-text representation — no URL conformance.
        let providers = [capability(url: false, string: true)]
        #expect(sidebarDropRoute(for: providers) == .internalMove)
    }

    @Test("Finder file drag: URL-loadable provider → .finderImport")
    func urlProviderIsFinderImport() {
        // Finder drags of common file types always expose a URL.
        let providers = [capability(url: true, string: false)]
        #expect(sidebarDropRoute(for: providers) == .finderImport)
    }

    @Test("Finder drag that also advertises string representation → .finderImport")
    func urlAndStringIsStillFinderImport() {
        // Finder drags of URL-backed items commonly also advertise a
        // text representation (the URL's absolute string). The classifier
        // must route these as .finderImport, not .internalMove — earlier
        // revisions got this wrong and JPG drags bounced back.
        let providers = [capability(url: true, string: true)]
        #expect(sidebarDropRoute(for: providers) == .finderImport)
    }

    @Test("Mixed providers: ANY text-only provider → .internalMove")
    func mixedWithTextOnlyPrefersInternal() {
        // Edge case: internal sidebar drag while a Finder drag is also
        // somehow on the pasteboard. The text-only provider (sidebar
        // item ID) is the unambiguous signal of internal intent, so
        // prefer internal routing.
        let providers = [
            capability(url: true, string: true),   // Finder-shaped
            capability(url: false, string: true)   // internal-shaped
        ]
        #expect(sidebarDropRoute(for: providers) == .internalMove)
    }

    @Test("Provider that can't load URL OR string → .finderImport (optimistic)")
    func unknownProviderAccepted() {
        // Some macOS drag sources delay capability advertisement; the
        // canLoadObject flags can both return false but the provider
        // could still produce bytes if asked. Optimistic accept — let
        // the async loader figure it out rather than bouncing the
        // drop up front.
        let providers = [capability(url: false, string: false)]
        #expect(sidebarDropRoute(for: providers) == .finderImport)
    }

    @Test("Finder .mov / .jpg / folder all route as .finderImport")
    func commonFinderFormatsImport() {
        // Pinning the specific regressions Daniel hit:
        //   - .mov originally missed because provider didn't advertise
        //     public.file-url up front (#600).
        //   - folder originally missed because of the same asymmetry.
        //   - .jpg bounced because UTI-based filtering missed it.
        // All three arrive with canLoadURL=true; the classifier should
        // send every one of them through .finderImport.
        for advertised in [
            capability(url: true, string: false),  // .mov Finder drag
            capability(url: true, string: true),   // .jpg Finder drag (has URL string repr)
            capability(url: true, string: false)   // folder Finder drag
        ] {
            #expect(sidebarDropRoute(for: [advertised]) == .finderImport)
        }
    }
}

// MARK: - URL-Load Strategy Tests

/// Pins the NSItemProvider URL-load decision tree. Daniel's 2026-04-17
/// log captured a Finder JPG drag whose provider advertised only
/// `public.jpeg` — `canLoadObject(URL.self)` returned false even
/// though `loadFileRepresentation(forTypeIdentifier: "public.jpeg")`
/// DID produce a file URL. Each rewrite of the drop handler has
/// flipped between getting this decision right and wrong; these tests
/// lock the rules in so the regression can't sneak back.
struct URLLoadStrategyTests {

    @Test("canLoadURL=true → .useLoadObject (preferred fast path)")
    func canLoadURLPrefersLoadObject() {
        let strategy = urlLoadStrategy(canLoadURL: true, utis: [])
        #expect(strategy == .useLoadObject)
    }

    @Test("canLoadURL=true with UTIs still prefers loadObject")
    func canLoadURLPrefersLoadObjectEvenWithUTIs() {
        // If the provider says it can yield URL directly, use that —
        // don't bother with the representation-iteration fallback.
        let strategy = urlLoadStrategy(
            canLoadURL: true,
            utis: ["public.file-url", "public.image", "public.jpeg"]
        )
        #expect(strategy == .useLoadObject)
    }

    @Test("canLoadURL=false with content UTI → .tryRepresentations([uti])")
    func contentUTIFallback() {
        // The exact shape from Daniel's 2026-04-17 Finder JPG drag:
        //   [0] UTIs: [public.jpeg]  URL:false  String:false
        // Must fall through to loadFileRepresentation(forTypeIdentifier:).
        let strategy = urlLoadStrategy(canLoadURL: false, utis: ["public.jpeg"])
        #expect(strategy == .tryRepresentations(["public.jpeg"]))
    }

    @Test("canLoadURL=false, no UTIs → .reject")
    func nothingAdvertisedRejects() {
        // Degenerate provider: can't load URL, advertises no UTIs.
        // Nothing we can try — reject deterministically.
        let strategy = urlLoadStrategy(canLoadURL: false, utis: [])
        #expect(strategy == .reject)
    }

    @Test("Multiple UTIs preserve provider's advertisement order")
    func multiUTIOrderPreserved() {
        // Iteration order matters: providers often list their
        // preferred representation first. Don't sort or dedupe —
        // the caller iterates in order and returns on first success.
        let utis = ["public.file-url", "public.image", "public.jpeg"]
        let strategy = urlLoadStrategy(canLoadURL: false, utis: utis)
        #expect(strategy == .tryRepresentations(utis))
    }

    @Test("Movie content UTI (public.movie) falls through to representations")
    func movieContentUTIFallback() {
        // Daniel's .mov-bounce regression (#600): Finder advertised
        // `public.movie` but not public.file-url. Without the
        // representation fallback the drop silently bounced.
        let strategy = urlLoadStrategy(canLoadURL: false, utis: ["public.movie"])
        #expect(strategy == .tryRepresentations(["public.movie"]))
    }

    @Test("Folder content UTI (public.folder) falls through to representations")
    func folderContentUTIFallback() {
        // Finder folder drags sometimes advertise only `public.folder`
        // without URL conformance. Representation fallback picks it up.
        let strategy = urlLoadStrategy(canLoadURL: false, utis: ["public.folder"])
        #expect(strategy == .tryRepresentations(["public.folder"]))
    }
}

// MARK: - Sidebar Reorder Helper Tests

/// Covers the pure helper that translates a SwiftUI `.onMove` event into
/// the ordered list of document IDs to persist. Keeps the index-math
/// and kind-gate logic out of the view layer so regressions (e.g. the
/// "flash-once-then-dies" symptom the old `.onMove` impl had) can be
/// caught by the test suite before hitting Daniel's build.
struct SidebarReorderedDocIdsTests {

    private let libraryId = UUID()

    private func doc(_ id: String, name: String, sortOrder: Int = 0) -> SidebarItem {
        SidebarItem(
            id: "doc:\(id)",
            name: name,
            icon: "doc",
            category: .folder,
            itemType: .document(Document(
                id: id,
                docType: .file,
                name: name,
                sortOrder: sortOrder
            )),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: sortOrder,
            isFolder: false
        )
    }

    private func savedSearch(_ id: String, name: String) -> SidebarItem {
        SidebarItem(
            id: "search:\(id)",
            name: name,
            icon: "magnifyingglass",
            category: .search,
            itemType: .savedSearch(SavedSearch(id: id, name: name, query: "")),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }

    @Test("Moving a single document down yields the new ordered IDs")
    func moveOneDown() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B"), doc("c", name: "C")]
        // Move index 0 to after index 2 → ["b", "c", "a"]
        let result = try #require(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 3
        ))
        #expect(result == ["b", "c", "a"])
    }

    @Test("Moving a document up yields the new ordered IDs")
    func moveOneUp() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B"), doc("c", name: "C")]
        // Move index 2 to before index 0 → ["c", "a", "b"]
        let result = try #require(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 2),
            to: 0
        ))
        #expect(result == ["c", "a", "b"])
    }

    @Test("No-op move (same position) returns nil")
    func noOpMoveReturnsNil() {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        // Moving index 0 to position 0 or 1 (either side of itself) → no change
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 0
        ) == nil)
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 1
        ) == nil)
    }

    @Test("Mixed children (doc + saved search) rejected — no reorder endpoint")
    func mixedKindsRejected() {
        // The reorder endpoint today accepts document IDs only. Rows
        // under a virtual-folder header (e.g. saved searches) must
        // not try to call it — the backend would 404 or mis-sort.
        let children = [doc("a", name: "A"), savedSearch("s", name: "S")]
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 2
        ) == nil)
    }

    @Test("Empty source IndexSet returns nil")
    func emptySourceReturnsNil() {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(),
            to: 1
        ) == nil)
    }

    @Test("Moving multiple siblings together preserves group order")
    func multiMove() throws {
        let children = [
            doc("a", name: "A"), doc("b", name: "B"),
            doc("c", name: "C"), doc("d", name: "D")
        ]
        // Move indices {0, 1} to after index 3 → ["c", "d", "a", "b"]
        let result = try #require(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet([0, 1]),
            to: 4
        ))
        #expect(result == ["c", "d", "a", "b"])
    }
}

// MARK: - Circular Drop Detection Tests

/// Replicates the logic from SidebarItemRow.containsDescendant(_:in:)
struct CircularDropDetectionTests {

    private let libraryId = UUID()

    private func makeFolder(id: String, name: String, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: id,
            name: name,
            icon: "folder",
            category: .folder,
            itemType: .document(Document(id: id, docType: .folder, name: name)),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )
    }

    private func containsDescendant(_ targetId: String, in item: SidebarItem) -> Bool {
        if item.id == targetId { return true }
        if let children = item.children {
            for child in children where containsDescendant(targetId, in: child) {
                return true
            }
        }
        return false
    }

    @Test("item is considered a descendant of itself")
    func selfIsDescendant() {
        let folder = makeFolder(id: "f1", name: "Folder")
        #expect(containsDescendant("f1", in: folder))
    }

    @Test("direct child is a descendant")
    func directChild() {
        let child = makeFolder(id: "child", name: "Child")
        let parent = makeFolder(id: "parent", name: "Parent", children: [child])
        #expect(containsDescendant("child", in: parent))
    }

    @Test("nested grandchild is a descendant")
    func grandchild() {
        let grandchild = makeFolder(id: "gc", name: "Grandchild")
        let child = makeFolder(id: "child", name: "Child", children: [grandchild])
        let parent = makeFolder(id: "parent", name: "Parent", children: [child])
        #expect(containsDescendant("gc", in: parent))
    }

    @Test("sibling is NOT a descendant")
    func siblingIsNotDescendant() {
        let child1 = makeFolder(id: "c1", name: "Child 1")
        let child2 = makeFolder(id: "c2", name: "Child 2")
        let parent = makeFolder(id: "parent", name: "Parent", children: [child1, child2])
        // child2 is not a descendant of child1
        #expect(!containsDescendant("c2", in: child1))
        _ = parent // suppress unused warning
    }

    @Test("unrelated item is not a descendant")
    func unrelated() {
        let folder = makeFolder(id: "f1", name: "Folder")
        #expect(!containsDescendant("unrelated-id", in: folder))
    }
}
