@testable import Fichero
import Foundation
import XCTest

/// Tests for SidebarState — sidebar expansion + drop + folder-creation
/// state machine. Locks the toggle/expand semantics, the
/// library-default-expanded behaviour, and the reset contracts.
///
/// Each test uses a fresh windowId so persisted UserDefaults state
/// can't bleed between tests (the class scopes keys per windowId).
@MainActor
final class SidebarStateTests: XCTestCase {

    private func freshWindowId() -> String {
        "test-\(UUID().uuidString)"
    }

    // MARK: - Item expansion

    func testItemExpansionStartsEmpty() {
        let state = SidebarState(windowId: freshWindowId())
        XCTAssertTrue(state.expandedItems.isEmpty)
        XCTAssertFalse(state.isExpanded("anything"))
    }

    func testToggleExpansionAdds() {
        let state = SidebarState(windowId: freshWindowId())
        state.toggleExpansion(for: "folder:/Library")
        XCTAssertTrue(state.isExpanded("folder:/Library"))
        XCTAssertEqual(state.expandedItems, ["folder:/Library"])
    }

    func testToggleExpansionRemoves() {
        let state = SidebarState(windowId: freshWindowId())
        state.toggleExpansion(for: "x")
        state.toggleExpansion(for: "x")
        XCTAssertFalse(state.isExpanded("x"))
    }

    func testToggleExpansionMultipleItems() {
        let state = SidebarState(windowId: freshWindowId())
        state.toggleExpansion(for: "a")
        state.toggleExpansion(for: "b")
        state.toggleExpansion(for: "c")
        XCTAssertEqual(state.expandedItems, ["a", "b", "c"])
        state.toggleExpansion(for: "b")
        XCTAssertEqual(state.expandedItems, ["a", "c"])
    }

    // MARK: - Library expansion (default: true)

    func testLibraryDefaultExpanded() {
        let state = SidebarState(windowId: freshWindowId())
        let libId = UUID()
        XCTAssertTrue(state.isLibraryExpanded(libId))
    }

    func testToggleLibraryExpansionCollapses() {
        let state = SidebarState(windowId: freshWindowId())
        let libId = UUID()
        state.toggleLibraryExpansion(for: libId)
        XCTAssertFalse(state.isLibraryExpanded(libId))
    }

    func testToggleLibraryExpansionReExpands() {
        let state = SidebarState(windowId: freshWindowId())
        let libId = UUID()
        state.toggleLibraryExpansion(for: libId)
        state.toggleLibraryExpansion(for: libId)
        XCTAssertTrue(state.isLibraryExpanded(libId))
    }

    // MARK: - Persistence round-trip

    func testExpansionPersistsAcrossInstancesSameWindowId() {
        let windowId = freshWindowId()
        do {
            let state = SidebarState(windowId: windowId)
            state.toggleExpansion(for: "persisted-item")
        }
        // New instance with same windowId reads the persisted state.
        let restored = SidebarState(windowId: windowId)
        XCTAssertTrue(restored.isExpanded("persisted-item"))

        // Cleanup
        UserDefaults.standard.removeObject(forKey: "sidebar.expanded.\(windowId)")
    }

    func testLibraryExpansionPersists() {
        let windowId = freshWindowId()
        let libId = UUID()
        do {
            let state = SidebarState(windowId: windowId)
            state.toggleLibraryExpansion(for: libId)  // collapse
        }
        let restored = SidebarState(windowId: windowId)
        XCTAssertFalse(restored.isLibraryExpanded(libId))

        UserDefaults.standard.removeObject(forKey: "sidebar.libraries.\(windowId)")
    }

    func testStaleUnifiedSectionsKeyPurgedOnInit() {
        // The unified-section headers were retired; any persisted expansion
        // dictionary from old builds must be removed at init.
        let windowId = freshWindowId()
        let staleKey = "sidebar.unified.sections.\(windowId)"
        UserDefaults.standard.set(["lib:documents": false], forKey: staleKey)

        _ = SidebarState(windowId: windowId)

        XCTAssertNil(UserDefaults.standard.object(forKey: staleKey))
    }

    // MARK: - Transient state defaults

    func testTransientDefaultsAreClean() {
        let state = SidebarState(windowId: freshWindowId())
        XCTAssertFalse(state.isChatDropTargeted)
        XCTAssertFalse(state.isLibraryDropTargeted)
        XCTAssertNil(state.renamingItemId)
        XCTAssertFalse(state.showingFileImporter)
        XCTAssertEqual(state.selectedImportMode, .link)
        XCTAssertFalse(state.showingNewFolderDialog)
        XCTAssertNil(state.newFolderParentId)
        XCTAssertNil(state.newFolderCategory)
        XCTAssertEqual(state.newFolderName, "")
        XCTAssertNil(state.newFolderErrorMessage)
        XCTAssertFalse(state.isCreatingFolder)
        XCTAssertNil(state.creatingFolderInlineId)
        XCTAssertFalse(state.showingScheduleCreation)
        XCTAssertFalse(state.showingTriggerCreation)
        XCTAssertNil(state.selectedWorkflowForAutomation)
        XCTAssertFalse(state.isProcessingDrop)
        XCTAssertEqual(state.dropProgress, 0.0)
        XCTAssertNil(state.dropErrorMessage)
        XCTAssertNil(state.renameErrorMessage)
        XCTAssertEqual(state.dropSuccessCount, 0)
        XCTAssertEqual(state.dropFailureCount, 0)
    }

    // MARK: - reset()

    func testResetClearsAllState() {
        let state = SidebarState(windowId: freshWindowId())
        // Pollute
        state.toggleExpansion(for: "x")
        state.toggleLibraryExpansion(for: UUID())
        state.isChatDropTargeted = true
        state.renamingItemId = "id"
        state.newFolderName = "x"
        state.renameErrorMessage = "boom"
        state.dropProgress = 0.5
        state.dropSuccessCount = 5
        state.dropFailureCount = 2

        state.reset()

        XCTAssertTrue(state.expandedItems.isEmpty)
        XCTAssertTrue(state.libraryExpansionStates.isEmpty)
        XCTAssertFalse(state.isChatDropTargeted)
        XCTAssertNil(state.renamingItemId)
        XCTAssertEqual(state.newFolderName, "")
        XCTAssertFalse(state.isProcessingDrop)
        XCTAssertEqual(state.dropProgress, 0.0)
        XCTAssertNil(state.renameErrorMessage)
        XCTAssertEqual(state.dropSuccessCount, 0)
        XCTAssertEqual(state.dropFailureCount, 0)
    }

    // MARK: - resetFolderCreationState()

    func testResetFolderCreationLeavesUnrelatedAlone() {
        let state = SidebarState(windowId: freshWindowId())
        state.toggleExpansion(for: "x")              // unrelated — keep
        state.isChatDropTargeted = true              // unrelated — keep
        state.showingNewFolderDialog = true
        state.newFolderParentId = "p"
        state.newFolderCategory = .search
        state.newFolderName = "X"
        state.newFolderErrorMessage = "err"
        state.isCreatingFolder = true
        state.creatingFolderInlineId = "c"

        state.resetFolderCreationState()

        // Folder-creation fields cleared
        XCTAssertFalse(state.showingNewFolderDialog)
        XCTAssertNil(state.newFolderParentId)
        XCTAssertNil(state.newFolderCategory)
        XCTAssertEqual(state.newFolderName, "")
        XCTAssertNil(state.newFolderErrorMessage)
        XCTAssertFalse(state.isCreatingFolder)
        XCTAssertNil(state.creatingFolderInlineId)

        // Unrelated state preserved
        XCTAssertTrue(state.isExpanded("x"))
        XCTAssertTrue(state.isChatDropTargeted)
    }

    // MARK: - Different windowIds isolated

    func testDifferentWindowIdsDontShareState() {
        let id1 = freshWindowId()
        let id2 = freshWindowId()
        let state1 = SidebarState(windowId: id1)
        let state2 = SidebarState(windowId: id2)

        state1.toggleExpansion(for: "only-in-1")

        XCTAssertTrue(state1.isExpanded("only-in-1"))
        XCTAssertFalse(state2.isExpanded("only-in-1"))

        UserDefaults.standard.removeObject(forKey: "sidebar.expanded.\(id1)")
    }

    // MARK: - Retired-key purge must not write when nothing to purge (#4104)

    /// SidebarState.init runs on every SidebarView.init (State(wrappedValue:)
    /// re-evaluates each parent body pass). An unguarded removeObject posts
    /// UserDefaults.didChangeNotification even for an absent key, which
    /// invalidated every @AppStorage/@SceneStorage in the window and spun the
    /// AttributeGraph at 100% CPU. These lock the guard.
    func testPurgeRetiredDefaultsIsNoOpWhenKeyAbsent() throws {
        let suite = "test.purge.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        XCTAssertFalse(
            SidebarState.purgeRetiredDefaults(windowId: "w", defaults: defaults),
            "absent key must not be written (a write re-dirties the AttributeGraph)"
        )
    }

    func testPurgeRetiredDefaultsRemovesOnceThenGoesQuiet() throws {
        let suite = "test.purge.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        defaults.set(["stale"], forKey: "sidebar.unified.sections.w")

        XCTAssertTrue(SidebarState.purgeRetiredDefaults(windowId: "w", defaults: defaults))
        XCTAssertNil(defaults.object(forKey: "sidebar.unified.sections.w"))
        XCTAssertFalse(
            SidebarState.purgeRetiredDefaults(windowId: "w", defaults: defaults),
            "second call must be a pure read"
        )
    }

    /// End-to-end guard: constructing SidebarState twice (as SwiftUI does on
    /// every body pass) must not post defaults-change notifications after the
    /// first pass — the exact per-frame write that caused the CPU spin.
    func testRepeatedInitDoesNotWriteDefaults() {
        let id = freshWindowId()
        _ = SidebarState(windowId: id)  // first pass may purge

        var changes = 0
        let observer = NotificationCenter.default.addObserver(
            forName: UserDefaults.didChangeNotification,
            object: UserDefaults.standard,
            queue: nil
        ) { _ in changes += 1 }
        defer { NotificationCenter.default.removeObserver(observer) }

        _ = SidebarState(windowId: id)
        _ = SidebarState(windowId: id)

        XCTAssertEqual(changes, 0, "re-init must be read-only — writes here loop the AttributeGraph")
    }
}
