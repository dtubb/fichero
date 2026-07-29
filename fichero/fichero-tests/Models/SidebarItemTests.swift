//
//  SidebarItemTests.swift
//  FicheroTests
//
//  Tests for SidebarItem factory methods, ItemCategory properties,
//  and SidebarItemBuilder hierarchy building logic.
//

import Foundation
import Testing
@testable import Fichero

// MARK: - ItemCategory Tests

struct ItemCategoryTests {

    @Test("All cases have non-empty icons")
    func allCasesHaveIcons() {
        for category in ItemCategory.allCases {
            #expect(!category.icon.isEmpty, "\(category.rawValue) should have an icon")
        }
    }

    @Test("Category id equals rawValue")
    func idEqualsRawValue() {
        for category in ItemCategory.allCases {
            #expect(category.id == category.rawValue)
        }
    }

    @Test("Specific icon values")
    func specificIcons() {
        #expect(ItemCategory.folder.icon == "folder")
        #expect(ItemCategory.search.icon == "magnifyingglass")
        #expect(ItemCategory.chat.icon == "bubble.left.and.bubble.right")
        #expect(ItemCategory.workflow.icon == "arrow.triangle.branch")
        #expect(ItemCategory.automation.icon == "clock.arrow.2.circlepath")
        #expect(ItemCategory.batch.icon == "square.stack.3d.up")
        #expect(ItemCategory.activity.icon == "waveform.path.ecg")
        #expect(ItemCategory.library.icon == "book.closed")
    }
}

// MARK: - SidebarItem Factory Tests

struct SidebarItemFactoryTests {

    private let testLibraryId = UUID()
    private let now = Date()

    private func makeDocument(
        id: String = "doc-1",
        name: String = "Test Doc",
        docType: DocType = .file,
        parentId: String? = nil,
        sortOrder: Int = 0
    ) -> Document {
        Document(
            id: id,
            parentId: parentId,
            docType: docType,
            fileType: nil,
            name: name,
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            sortOrder: sortOrder,
            createdAt: now,
            updatedAt: now,
            expectedThumbnailPath: nil,
            expectedDisplayPath: nil
        )
    }

    private func makeWorkflow(
        id: String = "wf-1",
        name: String = "Test Workflow",
        folderPath: String = "/",
        sortOrder: Int = 0
    ) -> WorkflowSidebarItem {
        WorkflowSidebarItem(
            id: id,
            name: name,
            description: nil,
            nodeCount: 3,
            edgeCount: 2,
            isEnabled: true,
            folderPath: folderPath,
            sortOrder: sortOrder,
            createdAt: now,
            updatedAt: now
        )
    }

    private func makeSearch(
        id: String = "search-1",
        name: String = "Test Search",
        folderPath: String = "/",
        sortOrder: Int = 0
    ) -> SavedSearch {
        SavedSearch(
            id: id,
            name: name,
            query: "test query",
            filters: SearchFilters(),
            icon: "magnifyingglass",
            isSmartSearch: false,
            folderPath: folderPath,
            sortOrder: sortOrder,
            createdAt: now
        )
    }

    private func makeConversation(
        id: String = "chat-1",
        title: String = "Test Chat",
        folderPath: String = "/",
        sortOrder: Int = 0
    ) -> Conversation {
        Conversation(
            id: id,
            title: title,
            messages: [],
            documentScope: [],
            folderPath: folderPath,
            sortOrder: sortOrder,
            createdAt: now,
            updatedAt: now
        )
    }

    // MARK: - fromDocument

    @Test("fromDocument sets correct id prefix")
    func fromDocumentId() {
        let doc = makeDocument(id: "abc")
        let item = SidebarItem.fromDocument(doc, libraryId: testLibraryId)
        #expect(item.id == "doc:abc")
    }

    @Test("fromDocument uses document name")
    func fromDocumentName() {
        let doc = makeDocument(name: "My File")
        let item = SidebarItem.fromDocument(doc, libraryId: testLibraryId)
        #expect(item.name == "My File")
    }

    @Test("fromDocument marks folders as isFolder")
    func fromDocumentFolder() {
        let folder = makeDocument(docType: .folder)
        let item = SidebarItem.fromDocument(folder, libraryId: testLibraryId)
        #expect(item.isFolder == true)
        #expect(item.category == .folder)
    }

    @Test("fromDocument marks files as not isFolder")
    func fromDocumentFile() {
        let file = makeDocument(docType: .file)
        let item = SidebarItem.fromDocument(file, libraryId: testLibraryId)
        #expect(item.isFolder == false)
    }

    @Test("fromDocument uses parentId as folderPath")
    func fromDocumentFolderPath() {
        let doc = makeDocument(parentId: "parent-123")
        let item = SidebarItem.fromDocument(doc, libraryId: testLibraryId)
        #expect(item.folderPath == "parent-123")
    }

    @Test("fromDocument defaults folderPath to / when no parentId")
    func fromDocumentDefaultFolderPath() {
        let doc = makeDocument(parentId: nil)
        let item = SidebarItem.fromDocument(doc, libraryId: testLibraryId)
        #expect(item.folderPath == "/")
    }

    @Test("#572 fromDocument propagates sortOrder from Document to SidebarItem")
    func fromDocumentPropagatesSortOrder() {
        // Before #572 / sidebar plan Step 3, `SidebarItem.fromDocument`
        // hardcoded sortOrder to 0 with the comment "Documents don't have
        // sort_order (yet)". Sibling types (searches, workflows, chats)
        // already propagated it from the backend. This test pins the
        // Document path so a future regression can't silently drop the
        // field back to zero.
        let doc = makeDocument(id: "doc-42", sortOrder: 7)
        let item = SidebarItem.fromDocument(doc, libraryId: testLibraryId)
        #expect(item.sortOrder == 7)
    }

    @Test("#572 fromDocument defaults sortOrder to 0 when Document has default")
    func fromDocumentDefaultSortOrder() {
        let doc = makeDocument(id: "doc-99")
        let item = SidebarItem.fromDocument(doc, libraryId: testLibraryId)
        #expect(item.sortOrder == 0)
    }

    // MARK: - fromWorkflow

    @Test("fromWorkflow sets correct id prefix and icon")
    func fromWorkflow() {
        let wf = makeWorkflow(id: "wf-42")
        let item = SidebarItem.fromWorkflow(wf, libraryId: testLibraryId)
        #expect(item.id == "workflow:wf-42")
        #expect(item.icon == "arrow.triangle.branch")
        #expect(item.category == .workflow)
        #expect(item.isFolder == false)
    }

    // MARK: - fromSearch

    @Test("fromSearch sets correct id prefix and category")
    func fromSearch() {
        let search = makeSearch(id: "s-1")
        let item = SidebarItem.fromSearch(search, libraryId: testLibraryId)
        #expect(item.id == "search:s-1")
        #expect(item.category == .search)
    }

    // MARK: - fromConversation

    @Test("fromConversation sets correct id prefix and category")
    func fromConversation() {
        let chat = makeConversation(id: "c-1", title: "Chat Title")
        let item = SidebarItem.fromConversation(chat, libraryId: testLibraryId)
        #expect(item.id == "chat:c-1")
        #expect(item.name == "Chat Title")
        #expect(item.category == .chat)
    }

    // MARK: - folder factory

    @Test("Folder factory creates folder item")
    func folderFactory() {
        let item = SidebarItem.folder(
            name: "Archive",
            folderPath: "/archive",
            category: .search,
            libraryId: testLibraryId
        )
        #expect(item.id == "folder:/archive:Search")
        #expect(item.name == "Archive")
        #expect(item.isFolder == true)
        #expect(item.icon == "folder")
    }

    // MARK: - SidebarItem.folderKind (#585, sidebar plan Step 9)

    @Test("#585 folderKind: document folder → .document")
    func folderKindDocumentFolder() {
        let doc = makeDocument(docType: .folder)
        let item = SidebarItem.fromDocument(doc, libraryId: testLibraryId)
        #expect(item.folderKind == .document)
    }

    @Test("#585 folderKind: document file (not folder) → nil")
    func folderKindDocumentFile() {
        let doc = makeDocument(docType: .file)
        let item = SidebarItem.fromDocument(doc, libraryId: testLibraryId)
        #expect(item.folderKind == nil)
    }

    @Test("#585 folderKind: virtual folder in search section → .savedSearch")
    func folderKindSearchFolder() {
        let item = SidebarItem.folder(
            name: "Production",
            folderPath: "/production",
            category: .search,
            libraryId: testLibraryId
        )
        #expect(item.folderKind == .savedSearch)
    }

    @Test("#585 folderKind: virtual folder in chat section → .conversation")
    func folderKindChatFolder() {
        let item = SidebarItem.folder(
            name: "Research",
            folderPath: "/research",
            category: .chat,
            libraryId: testLibraryId
        )
        #expect(item.folderKind == .conversation)
    }

    @Test("#585 folderKind: virtual folder in workflow section → .workflow")
    func folderKindWorkflowFolder() {
        let item = SidebarItem.folder(
            name: "Automation",
            folderPath: "/automation",
            category: .workflow,
            libraryId: testLibraryId
        )
        #expect(item.folderKind == .workflow)
    }

    @Test("#585 folderKind: saved search leaf (not folder) → nil")
    func folderKindSavedSearchLeaf() {
        let search = makeSearch(id: "s-1")
        let item = SidebarItem.fromSearch(search, libraryId: testLibraryId)
        #expect(item.folderKind == nil)
    }

    @Test("#585 folderKind: library header → nil")
    func folderKindLibraryHeader() {
        let item = SidebarItem(
            id: "lib:abc",
            name: "Library",
            icon: "book",
            category: .library,
            itemType: .libraryHeader,
            children: nil,
            libraryId: testLibraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
        #expect(item.folderKind == nil)
    }

    // MARK: - isExpandable

    @Test("isExpandable true when children exist")
    func expandableWithChildren() {
        let child = SidebarItem.folder(name: "Sub", folderPath: "/sub", category: .folder, libraryId: testLibraryId)
        let parent = SidebarItem.folder(
            name: "Parent", folderPath: "/parent", category: .folder, libraryId: testLibraryId,
            children: [child]
        )
        #expect(parent.isExpandable == true)
    }

    @Test("isExpandable false when no children")
    func expandableNoChildren() {
        let item = SidebarItem.folder(name: "Leaf", folderPath: "/leaf", category: .folder, libraryId: testLibraryId)
        #expect(item.isExpandable == false)
    }

    @Test("isExpandable false when children is empty array")
    func expandableEmptyChildren() {
        let item = SidebarItem.folder(
            name: "Empty", folderPath: "/empty", category: .folder, libraryId: testLibraryId,
            children: []
        )
        #expect(item.isExpandable == false)
    }

    @Test("isExpandable true for a document with unloaded children")
    func expandableFromChildCountWithoutLoadedChildren() {
        let document = Document(
            id: "folder-1",
            docType: .folder,
            name: "Folder",
            childCount: 2
        )
        let item = SidebarItem.fromDocument(document, libraryId: testLibraryId)
        #expect(item.isExpandable == true)
    }
}

// MARK: - SidebarItemBuilder Hierarchy Tests

struct SidebarItemBuilderTests {

    private let testLibraryId = UUID()
    private let now = Date()

    private func makeDocument(
        id: String,
        name: String,
        docType: DocType = .folder,
        fileType: FileType? = nil,
        parentId: String? = nil,
        sequence: Int? = nil,
        structure: [DocumentStructureNode] = [],
        sortOrder: Int = 0
    ) -> Document {
        Document(
            id: id,
            parentId: parentId,
            docType: docType,
            fileType: fileType,
            name: name,
            path: nil,
            sequence: sequence,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            structure: structure,
            childCount: 0,
            sortOrder: sortOrder,
            createdAt: now,
            updatedAt: now,
            expectedThumbnailPath: nil,
            expectedDisplayPath: nil
        )
    }

    private func makeWorkflow(
        id: String,
        name: String,
        folderPath: String = "/",
        sortOrder: Int = 0
    ) -> WorkflowSidebarItem {
        WorkflowSidebarItem(
            id: id,
            name: name,
            description: nil,
            nodeCount: 1,
            edgeCount: 0,
            isEnabled: true,
            folderPath: folderPath,
            sortOrder: sortOrder,
            createdAt: now,
            updatedAt: now
        )
    }

    // MARK: - buildLibraryHierarchy

    @Test("buildLibraryHierarchy returns empty for no documents")
    func emptyDocuments() {
        let result = SidebarItemBuilder.buildLibraryHierarchy(from: [], libraryId: testLibraryId)
        #expect(result.isEmpty)
    }

    @Test("buildLibraryHierarchy excludes non-sidebar file leaves like text")
    func excludesTextFiles() {
        let generic = makeDocument(id: "f1", name: "notes.txt", docType: .file, fileType: .text)
        let result = SidebarItemBuilder.buildLibraryHierarchy(
            from: [generic],
            libraryId: testLibraryId
        )
        #expect(result.isEmpty, "text files must not appear in the sidebar")
    }

    @Test("buildLibraryHierarchy includes images as leaf rows")
    func includesImages() {
        let image = makeDocument(id: "f2", name: "photo.jpg", docType: .file, fileType: .image)
        let result = SidebarItemBuilder.buildLibraryHierarchy(
            from: [image],
            libraryId: testLibraryId
        )
        #expect(result.count == 1)
        #expect(result[0].name == "photo.jpg")
        #expect(result[0].children == nil)
    }

    @Test("buildLibraryHierarchy includes PDFs as containers (#568, #570)")
    func includesPdfs() {
        let pdf = makeDocument(id: "pdf-1", name: "paper.pdf", docType: .file, fileType: .pdf)
        let result = SidebarItemBuilder.buildLibraryHierarchy(from: [pdf], libraryId: testLibraryId)

        #expect(result.count == 1, "PDF should appear in the sidebar as a container")
        #expect(result[0].name == "paper.pdf")
        #expect(result[0].children == nil, "PDF without pages has no children")
    }

    @Test("buildLibraryHierarchy: PDF shows page child rows when no structure exists")
    func pdfShowsPagesInSidebar() {
        let pdf = makeDocument(id: "pdf-1", name: "paper.pdf", docType: .file, fileType: .pdf)
        let page1 = makeDocument(id: "p1", name: "paper.pdf - Page 1", docType: .page, parentId: "pdf-1", sequence: 1)
        let page2 = makeDocument(id: "p2", name: "paper.pdf - Page 2", docType: .page, parentId: "pdf-1", sequence: 2)
        let page3 = makeDocument(id: "p3", name: "paper.pdf - Page 3", docType: .page, parentId: "pdf-1", sequence: 3)

        let result = SidebarItemBuilder.buildLibraryHierarchy(
            from: [page3, pdf, page1, page2],
            libraryId: testLibraryId
        )

        #expect(result.count == 1)
        #expect(result[0].name == "paper.pdf")
        #expect(result[0].children?.map(\.name) == ["1", "2", "3"])
    }

    @Test("buildLibraryHierarchy: structured PDF shows its outline, not flat pages (#2260)")
    func structuredPdfPrefersOutlineOverPages() {
        let node = DocumentStructureNode(
            id: "n1",
            title: "Chapter 1",
            kind: "chapter",
            level: 0,
            pageRange: .init(start: 1, end: 3),
            basis: nil,
            confidence: nil,
            sourcePageLabel: nil,
            children: []
        )
        let pdf = makeDocument(
            id: "pdf-1", name: "paper.pdf", docType: .file, fileType: .pdf, structure: [node]
        )
        let page1 = makeDocument(id: "p1", name: "paper.pdf - Page 1", docType: .page, parentId: "pdf-1", sequence: 1)

        let result = SidebarItemBuilder.buildLibraryHierarchy(
            from: [pdf, page1],
            libraryId: testLibraryId
        )

        // When a programmatic outline exists, the structure rows win and flat
        // pages are NOT also listed (no double-listing).
        #expect(result.count == 1)
        #expect(result[0].children?.count == 1)
        #expect(result[0].children?[0].id == "structure:pdf-1:n1")
    }

    @Test("buildLibraryHierarchy — PDF in a folder shows under its folder")
    func pdfNestedInsideFolder() {
        let folder = makeDocument(id: "folder-1", name: "Papers", docType: .folder)
        let pdf = makeDocument(id: "pdf-1", name: "paper.pdf", docType: .file, fileType: .pdf, parentId: "folder-1")

        let result = SidebarItemBuilder.buildLibraryHierarchy(
            from: [folder, pdf],
            libraryId: testLibraryId
        )

        #expect(result.count == 1)
        #expect(result[0].name == "Papers")
        #expect(result[0].children?.count == 1)
        #expect(result[0].children?[0].name == "paper.pdf")
    }

    @Test("buildLibraryHierarchy places Inbox first with tray.fill icon")
    func inboxFirst() {
        let inbox = makeDocument(id: "inbox-1", name: "Inbox", docType: .folder)
        let other = makeDocument(id: "folder-1", name: "Archive", docType: .folder)
        let result = SidebarItemBuilder.buildLibraryHierarchy(from: [other, inbox], libraryId: testLibraryId)

        #expect(result.count == 2)
        #expect(result[0].name == "Inbox")
        #expect(result[0].icon == "tray.fill")
        #expect(result[1].name == "Archive")
    }

    @Test("buildLibraryHierarchy nests children under parent")
    func nestedHierarchy() {
        let parent = makeDocument(id: "p1", name: "Parent", docType: .folder, parentId: nil)
        let child = makeDocument(id: "c1", name: "Child", docType: .folder, parentId: "p1")

        let result = SidebarItemBuilder.buildLibraryHierarchy(from: [parent, child], libraryId: testLibraryId)

        #expect(result.count == 1)
        #expect(result[0].name == "Parent")
        #expect(result[0].children?.count == 1)
        #expect(result[0].children?[0].name == "Child")
    }

    // MARK: - childOrder sort priority (#572, sidebar plan Step 11)

    @Test("childOrder: lower sortOrder comes before higher regardless of name")
    func childOrderUsesSortOrderFirst() {
        // Able has sortOrder=0, Zara has sortOrder=1. The backend assigns
        // sortOrder sequentially from 0, so Able comes first despite coming
        // last alphabetically's reverse — this pins the "lower means earlier"
        // direction of the comparison.
        let able = makeDocument(id: "a1", name: "Able", docType: .folder, sortOrder: 0)
        let zara = makeDocument(id: "z1", name: "Zara", docType: .folder, sortOrder: 1)
        #expect(SidebarItemBuilder.childOrder(able, zara) == true)
        #expect(SidebarItemBuilder.childOrder(zara, able) == false)
    }

    @Test("childOrder: explicit reorder within parent respects sortOrder")
    func childOrderExplicitReorder() {
        let first = makeDocument(id: "f1", name: "B", docType: .folder, sortOrder: 2)
        let second = makeDocument(id: "f2", name: "A", docType: .folder, sortOrder: 3)
        // first (sortOrder 2) comes before second (sortOrder 3) despite
        // "B" > "A" alphabetically.
        #expect(SidebarItemBuilder.childOrder(first, second) == true)
    }

    @Test("childOrder: falls back to sequence when both sortOrders are 0 (PDF pages)")
    func childOrderFallsBackToSequence() {
        // Both pages default sortOrder 0 → sequence wins → page 2 before page 5
        let page2 = makeDocument(id: "p2", name: "Page 2", docType: .page, sequence: 2)
        let page5 = makeDocument(id: "p5", name: "Page 5", docType: .page, sequence: 5)
        #expect(SidebarItemBuilder.childOrder(page2, page5) == true)
    }

    @Test("childOrder: falls back to name when sortOrder and sequence both absent")
    func childOrderFallsBackToName() {
        let alpha = makeDocument(id: "a1", name: "Alpha", docType: .folder)
        let beta = makeDocument(id: "b1", name: "Beta", docType: .folder)
        #expect(SidebarItemBuilder.childOrder(alpha, beta) == true)
    }

    @Test("childOrder: equal sortOrder values fall through to sequence/name (not stuck)")
    func childOrderEqualSortOrderFallthrough() {
        // Both sortOrder 7 — tie — must fall through to name comparison,
        // not claim the first argument is "before" the second.
        let alpha = makeDocument(id: "a1", name: "Alpha", docType: .folder, sortOrder: 7)
        let beta = makeDocument(id: "b1", name: "Beta", docType: .folder, sortOrder: 7)
        #expect(SidebarItemBuilder.childOrder(alpha, beta) == true)
        #expect(SidebarItemBuilder.childOrder(beta, alpha) == false)
    }

    // MARK: - buildWorkflowHierarchy

    @Test("buildWorkflowHierarchy with root items")
    func workflowRootItems() {
        let workflows = [
            makeWorkflow(id: "w1", name: "First", sortOrder: 1),
            makeWorkflow(id: "w2", name: "Second", sortOrder: 0),
        ]
        let result = SidebarItemBuilder.buildWorkflowHierarchy(from: workflows, libraryId: testLibraryId)

        #expect(result.count == 2)
        // Should be sorted by sortOrder
        #expect(result[0].name == "Second")
        #expect(result[1].name == "First")
    }

    @Test("buildWorkflowHierarchy creates folder for non-root paths")
    func workflowWithFolders() {
        let workflows = [
            makeWorkflow(id: "w1", name: "Root WF", folderPath: "/"),
            makeWorkflow(id: "w2", name: "Nested WF", folderPath: "/production"),
        ]
        let result = SidebarItemBuilder.buildWorkflowHierarchy(from: workflows, libraryId: testLibraryId)

        // Should have root WF + production folder
        #expect(result.count == 2)

        let folder = result.first { $0.isFolder }
        #expect(folder?.name == "production")
        #expect(folder?.children?.count == 1)
        #expect(folder?.children?[0].name == "Nested WF")
    }

    @Test("buildWorkflowHierarchy creates nested folder structure")
    func workflowNestedFolders() {
        let workflows = [
            makeWorkflow(id: "w1", name: "Deep WF", folderPath: "/a/b"),
        ]
        let result = SidebarItemBuilder.buildWorkflowHierarchy(from: workflows, libraryId: testLibraryId)

        // Should create /a folder containing /a/b folder containing the workflow
        #expect(result.count == 1)
        let folderA = result[0]
        #expect(folderA.name == "a")
        #expect(folderA.isFolder == true)

        let folderB = folderA.children?[0]
        #expect(folderB?.name == "b")
        #expect(folderB?.isFolder == true)

        let wf = folderB?.children?[0]
        #expect(wf?.name == "Deep WF")
    }

    // MARK: - buildSearchHierarchy

    @Test("buildSearchHierarchy returns flat list for root items")
    func searchRootItems() {
        let searches = [
            SavedSearch(id: "s1", name: "Search A", query: "q", filters: SearchFilters(),
                       icon: "magnifyingglass", isSmartSearch: false,
                       folderPath: "/", sortOrder: 0, createdAt: now),
        ]
        let result = SidebarItemBuilder.buildSearchHierarchy(from: searches, libraryId: testLibraryId)
        #expect(result.count == 1)
        #expect(result[0].name == "Search A")
        #expect(result[0].category == .search)
    }
}
