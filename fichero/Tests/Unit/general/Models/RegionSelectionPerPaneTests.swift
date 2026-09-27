@testable import Fichero
import Testing

/// #5020, ruled 2026-09-27: each Source-view pane owns its region selection, and the Inspector and
/// the markup row follow the FOCUSED pane. Applies two standing rulings -- panes are not linked
/// unless a person connects them (2026-09-19), and "visible surface, always" (2026-08-23).
///
/// What broke: ONE app-wide selection, so a click in the right-hand Preview lit a box in the
/// left-hand one too, and by an index that could name a different box there.
@MainActor
struct RegionSelectionPerPaneTests {
    private func window() -> WindowState { WindowState(libraryId: LibraryManager.globalLibraryId) }

    @Test("a click in one pane selects nothing in the other")
    func twoPanesTwoSelections() {
        let left = RegionSelection()
        let right = RegionSelection()
        right.select(4, artifactId: "a1", documentId: "d1")
        #expect(right.indices == [4])
        #expect(left.isEmpty)
        #expect(!left.isSelected(4, in: "a1"))
    }

    @Test("the window acts on the pane that was used last")
    func focusFollowsUse() {
        let state = window()
        let left = RegionSelection()
        let right = RegionSelection()
        state.focusRegionSelection(left)
        state.focusRegionSelection(right)
        #expect(state.focusedRegionSelection === right)
    }

    /// Opening a second Preview must not take the Inspector away from the one being worked in.
    @Test("a pane that merely appears does not steal the focus")
    func appearingDoesNotSteal() {
        let state = window()
        let working = RegionSelection()
        let opened = RegionSelection()
        state.offerRegionSelection(working)
        state.offerRegionSelection(opened)
        #expect(state.focusedRegionSelection === working)
    }

    @Test("closing a pane drops the focus only if it was that pane's")
    func releaseOnlyOwnFocus() {
        let state = window()
        let focused = RegionSelection()
        let other = RegionSelection()
        state.focusRegionSelection(focused)
        state.releaseRegionSelection(other)
        #expect(state.focusedRegionSelection === focused)
        state.releaseRegionSelection(focused)
        #expect(state.focusedRegionSelection == nil)
    }
}
