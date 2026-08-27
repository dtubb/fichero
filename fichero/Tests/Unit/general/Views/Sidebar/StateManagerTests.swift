@testable import Fichero
import XCTest

/// Simple unit tests for sidebar state managers
@MainActor
class StateManagerTests: XCTestCase {

    // MARK: - Sidebar Item Presentation Tests

    func testSidebarItemUsesTypeSpecificTint() {
        let document = Document(id: "doc-1", docType: .file, name: "Test")
        let search = SavedSearch(id: "search-1", name: "Saved")
        let documentItem = SidebarItem.fromDocument(document, libraryId: UUID())
        let searchItem = SidebarItem.fromSearch(search, libraryId: UUID())

        XCTAssertEqual(documentItem.sidebarTint, .accent)
        XCTAssertEqual(searchItem.sidebarTint, .teal)
    }

    func testSidebarItemTintUsesItemTypeRatherThanCategory() {
        let search = SavedSearch(id: "search-1", name: "Saved")
        let item = SidebarItem(
            id: "search:selected",
            name: search.name,
            icon: search.icon,
            category: .folder,
            itemType: .savedSearch(search),
            children: nil,
            progress: nil,
            libraryId: UUID(),
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )

        XCTAssertEqual(item.sidebarTint, .teal)
    }

    func testSidebarItemCategoryTintsRemainDistinctForAgenticTypes() {
        XCTAssertEqual(ItemCategory.chat.sidebarTint, .indigo)
        XCTAssertEqual(ItemCategory.workflow.sidebarTint, .purple)
        XCTAssertEqual(ItemCategory.automation.sidebarTint, .orange)
        XCTAssertEqual(ItemCategory.activity.sidebarTint, .green)
    }

    // MARK: - RenameStateManager Tests

    func testRenameStateInitialization() {
        let state = RenameStateManager()
        XCTAssertNil(state.renamingItemId)
        XCTAssertEqual(state.editingName, "")
    }

    func testRenameStateStartRename() {
        let state = RenameStateManager()
        state.startRename(itemId: "test-123", currentName: "Test Document")

        XCTAssertEqual(state.renamingItemId, "test-123")
        XCTAssertEqual(state.editingName, "Test Document")
    }

    func testRenameStateCancelRename() {
        let state = RenameStateManager()
        state.startRename(itemId: "test-123", currentName: "Test")
        state.cancelRename()

        XCTAssertNil(state.renamingItemId)
        XCTAssertEqual(state.editingName, "")
    }

    // MARK: - DeleteStateManager Tests

    func testDeleteStateInitialization() {
        let state = DeleteStateManager()
        XCTAssertNil(state.itemToDelete)
        XCTAssertFalse(state.showingDeleteConfirmation)
        XCTAssertFalse(state.showingDeleteError)
        XCTAssertEqual(state.deleteErrorMessage, "")
    }

    func testDeleteStateShowConfirmation() {
        let state = DeleteStateManager()
        let document = Document(id: "doc-1", docType: .file, name: "Test")
        let item = SidebarItem(
            id: "doc-1",
            name: "Test",
            icon: "doc",
            category: .folder,
            itemType: .document(document),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: UUID(),
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )

        state.showDeleteConfirmation(for: item)

        XCTAssertNotNil(state.itemToDelete)
        XCTAssertTrue(state.showingDeleteConfirmation)
    }

    func testDeleteStateCancelDelete() {
        let state = DeleteStateManager()
        let document = Document(id: "doc-1", docType: .file, name: "Test")
        let item = SidebarItem(
            id: "doc-1",
            name: "Test",
            icon: "doc",
            category: .folder,
            itemType: .document(document),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: UUID(),
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )

        state.showDeleteConfirmation(for: item)
        state.cancelDelete()

        XCTAssertNil(state.itemToDelete)
        XCTAssertFalse(state.showingDeleteConfirmation)
    }

    func testDeleteStateShowError() {
        let state = DeleteStateManager()
        state.showError(message: "Test error")

        XCTAssertEqual(state.deleteErrorMessage, "Test error")
        XCTAssertTrue(state.showingDeleteError)
        XCTAssertFalse(state.showingDeleteConfirmation)
    }

    func testDeleteStateCancelDeleteClearsError() {
        let state = DeleteStateManager()
        state.showError(message: "Test error")
        state.cancelDelete()

        XCTAssertEqual(state.deleteErrorMessage, "")
        XCTAssertFalse(state.showingDeleteError)
    }
}
