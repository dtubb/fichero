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
        parentId: String? = nil
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
}

// MARK: - SidebarItemBuilder Hierarchy Tests

struct SidebarItemBuilderTests {

    private let testLibraryId = UUID()
    private let now = Date()

    private func makeDocument(
        id: String,
        name: String,
        docType: DocType = .folder,
        parentId: String? = nil
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

    @Test("buildLibraryHierarchy excludes non-folder documents")
    func excludesFiles() {
        let file = makeDocument(id: "f1", name: "file.pdf", docType: .file)
        let result = SidebarItemBuilder.buildLibraryHierarchy(from: [file], libraryId: testLibraryId)
        #expect(result.isEmpty)
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
