import XCTest
@testable import Fichero

/// Simple unit tests for sidebar state managers
@MainActor
class StateManagerTests: XCTestCase {

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
            section: .library,
            itemType: .document(document)
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
            section: .library,
            itemType: .document(document)
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
