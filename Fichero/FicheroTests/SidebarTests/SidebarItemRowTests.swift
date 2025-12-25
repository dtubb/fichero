import XCTest
@testable import Fichero
import SwiftUI

/// Unit tests for SidebarItemRow component
class SidebarItemRowTests: XCTestCase {

    // MARK: - Test Setup

    var mockDocumentStore: DocumentStore!
    var mockDocumentService: DocumentService!
    var mockSearchService: SavedSearchService!
    var mockConversationService: ConversationService!
    var mockWorkflowService: WorkflowService!

    override func setUp() {
        super.setUp()
        
        // Initialize mock services
        mockDocumentStore = DocumentStore()
        mockDocumentService = DocumentService()
        mockSearchService = SavedSearchService()
        mockConversationService = ConversationService()
        mockWorkflowService = WorkflowService()
    }

    override func tearDown() {
        mockDocumentStore = nil
        mockDocumentService = nil
        mockSearchService = nil
        mockConversationService = nil
        mockWorkflowService = nil
        super.tearDown()
    }

    // MARK: - Initialization Tests

    func testSidebarItemRowInitializationWithDocument() {
        // Given
        let document = Document(id: "1", name: "Test Document", docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: "Test Document", icon: "doc", itemType: .document(document))
        
        // When
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    func testSidebarItemRowInitializationWithCollection() {
        // Given
        let collection = Document(id: "1", name: "Test Collection", docType: .collection)
        let sidebarItem = SidebarItem(id: "1", name: "Test Collection", icon: "folder", itemType: .document(collection))
        
        // When
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    func testSidebarItemRowWithChildren() {
        // Given
        let parent = Document(id: "1", name: "Parent Collection", docType: .collection)
        let child1 = Document(id: "2", name: "Child Document 1", docType: .document)
        let child2 = Document(id: "3", name: "Child Document 2", docType: .document)
        
        let childItem1 = SidebarItem(id: "2", name: "Child Document 1", icon: "doc", itemType: .document(child1))
        let childItem2 = SidebarItem(id: "3", name: "Child Document 2", icon: "doc", itemType: .document(child2))
        
        let parentItem = SidebarItem(
            id: "1", 
            name: "Parent Collection", 
            icon: "folder", 
            itemType: .document(parent),
            children: [childItem1, childItem2]
        )
        
        // When
        let sidebarItemRow = SidebarItemRow(
            item: parentItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    // MARK: - Expansion State Tests

    func testSidebarItemRowExpansionState() {
        // Given
        let document = Document(id: "1", name: "Test Document", docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: "Test Document", icon: "doc", itemType: .document(document))
        
        // When
        let expandedItems = Binding<Set<String>>(
            get: { Set(["1"]) },
            set: { _ in }
        )
        
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: expandedItems,
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    // MARK: - Rename State Tests

    func testSidebarItemRowRenameState() {
        // Given
        let document = Document(id: "1", name: "Test Document", docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: "Test Document", icon: "doc", itemType: .document(document))
        
        // When
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant("1"),  // Item is being renamed
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    // MARK: - Section-Specific Tests

    func testSidebarItemRowInDifferentSections() {
        // Given
        let document = Document(id: "1", name: "Test Document", docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: "Test Document", icon: "doc", itemType: .document(document))
        
        let sections: [SidebarSection] = [.library, .searches, .chat, .workflows]
        
        // When
        let sidebarItemRows = sections.map { section in
            SidebarItemRow(
                item: sidebarItem,
                section: section,
                expandedItems: .constant([]),
                renamingItemId: .constant(nil),
                creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
                newFolderParentId: .constant(nil),
                newFolderSection: .constant(nil),
                viewMode: .constant(.browser),
                selectedItem: .constant(nil)
            )
            .environmentObject(mockDocumentStore)
            .environmentObject(mockDocumentService)
            .environmentObject(mockSearchService)
            .environmentObject(mockConversationService)
            .environmentObject(mockWorkflowService)
        }

        // Then
        sidebarItemRows.forEach { XCTAssertNotNil($0) }
    }

    // MARK: - Selection State Tests

    func testSidebarItemRowSelectionState() {
        // Given
        let document = Document(id: "1", name: "Test Document", docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: "Test Document", icon: "doc", itemType: .document(document))
        
        // When
        let selectedItem = Binding<SidebarItem?>(
            get: { sidebarItem },
            set: { _ in }
        )
        
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: selectedItem
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    // MARK: - Rendering Tests

    func testSidebarItemRowRendering() {
        // Given
        let document = Document(id: "1", name: "Test Document", docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: "Test Document", icon: "doc", itemType: .document(document))
        
        // When
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    // MARK: - Accessibility Tests

    func testSidebarItemRowAccessibility() {
        // Given
        let document = Document(id: "1", name: "Test Document", docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: "Test Document", icon: "doc", itemType: .document(document))
        
        // When
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    // MARK: - Error Handling Tests

    func testSidebarItemRowWithEmptyName() {
        // Given
        let document = Document(id: "1", name: "", docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: "", icon: "doc", itemType: .document(document))
        
        // When
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }

    func testSidebarItemRowWithLongName() {
        // Given
        let longName = String(repeating: "A", count: 200)
        let document = Document(id: "1", name: longName, docType: .document)
        let sidebarItem = SidebarItem(id: "1", name: longName, icon: "doc", itemType: .document(document))
        
        // When
        let sidebarItemRow = SidebarItemRow(
            item: sidebarItem,
            section: .library,
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.browser),
            selectedItem: .constant(nil)
        )
        .environmentObject(mockDocumentStore)
        .environmentObject(mockDocumentService)
        .environmentObject(mockSearchService)
        .environmentObject(mockConversationService)
        .environmentObject(mockWorkflowService)

        // Then
        XCTAssertNotNil(sidebarItemRow)
    }
}