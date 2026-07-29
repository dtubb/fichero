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

// MARK: - Sidebar File Drop Target Tests

struct SidebarFileDropTargetTests {

    private let libraryId = UUID()

    private func makeFolder(id: String, name: String) -> SidebarItem {
        SidebarItem(
            id: "doc:\(id)",
            name: name,
            icon: "folder",
            category: .folder,
            itemType: .document(Document(id: id, docType: .folder, name: name)),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )
    }

    private func makeFile(id: String, name: String, parentId: String?) -> SidebarItem {
        SidebarItem(
            id: "doc:\(id)",
            name: name,
            icon: "doc.richtext",
            category: .folder,
            itemType: .document(
                Document(
                    id: id,
                    parentId: parentId,
                    docType: .file,
                    fileType: .pdf,
                    name: name
                )
            ),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }

    @Test("drop on file resolves to its parent folder row")
    func fileDropTargetsParentFolder() {
        let folder = makeFolder(id: "folder-1", name: "Inbox")
        let file = makeFile(id: "file-1", name: "page1.pdf", parentId: "folder-1")

        let resolved = sidebarParentFolderItem(of: file, in: [folder, file])

        #expect(resolved?.id == folder.id)
    }

    @Test("drop on root file keeps root fallback")
    func rootFileDropFallsBackToRoot() {
        let file = makeFile(id: "file-1", name: "page1.pdf", parentId: nil)

        #expect(sidebarParentFolderItem(of: file, in: [file]) == nil)
    }
}
