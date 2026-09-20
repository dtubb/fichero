@testable import Fichero
import Testing

/// spec: kg-tables `kg.tables.entities-master-claims-detail` (#4886, ruled): an
/// Entities pane above, a Claims pane below — selecting an entity narrows the
/// Claims pane to that entity's claims. Pure decisions only; the store-backed
/// wiring test lives in `ClaimsLibraryContentEntityScopeWiringTests.swift`
/// (needs the mock-transport `ClaimStore`, XCTest-style, matching
/// `ClaimStoreTests.swift`'s own harness).
struct ClaimsLibraryContentScopeTests {

    // MARK: - effectiveScope

    @Test("no entity focused — the folder path is unchanged (today's behavior)")
    func noFocusFollowsFolder() {
        #expect(
            ClaimsLibraryContent.effectiveScope(
                focusedEntityId: nil, folderId: "folder-1", showingAllOverride: false
            ) == .folder("folder-1")
        )
        #expect(
            ClaimsLibraryContent.effectiveScope(
                focusedEntityId: nil, folderId: nil, showingAllOverride: false
            ) == .folder(nil)
        )
    }

    @Test("an entity focused — the entity scope wins over the folder")
    func focusWinsOverFolder() {
        #expect(
            ClaimsLibraryContent.effectiveScope(
                focusedEntityId: "e1", folderId: "folder-1", showingAllOverride: false
            ) == .entity("e1")
        )
    }

    @Test("Show All overrides an active focus — back to the folder even though an entity is focused")
    func overrideWinsOverFocus() {
        #expect(
            ClaimsLibraryContent.effectiveScope(
                focusedEntityId: "e1", folderId: "folder-1", showingAllOverride: true
            ) == .folder("folder-1")
        )
    }

    @Test("Show All with no focus at all is the same as no focus (no-op override)")
    func overrideWithNoFocusIsHarmless() {
        #expect(
            ClaimsLibraryContent.effectiveScope(
                focusedEntityId: nil, folderId: "folder-1", showingAllOverride: true
            ) == .folder("folder-1")
        )
    }

    // MARK: - showingAllResets

    @Test("a genuinely new focus resets the override")
    func newFocusResets() {
        #expect(ClaimsLibraryContent.showingAllResets(from: "e1", to: "e2"))
        #expect(ClaimsLibraryContent.showingAllResets(from: nil, to: "e1"))
        #expect(ClaimsLibraryContent.showingAllResets(from: "e1", to: nil))
    }

    @Test("the SAME focus firing again (a re-render, not a new selection) does NOT reset the override")
    func sameFocusDoesNotReset() {
        #expect(!ClaimsLibraryContent.showingAllResets(from: "e1", to: "e1"))
        #expect(!ClaimsLibraryContent.showingAllResets(from: nil, to: nil))
    }
}
