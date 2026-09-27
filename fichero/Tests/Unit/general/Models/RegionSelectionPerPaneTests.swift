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

    // MARK: - Identity, not position (#5020, commit 2)

    private func box(_ text: String, y: Double) -> OCRGeometryBox {
        OCRGeometryBox(text: text, bbox: [0.1, y, 0.3, 0.05], level: "line", confidence: nil,
                       pageIndex: nil, charStart: nil, charEnd: nil)
    }

    /// The artifact's order in one pane, the segment seam's in another -- or one list from before an
    /// edit and one from after. The same box is found in each.
    @Test("a box selected in one list is found again in the same list in another order")
    func foundByIdentityInAReorderedList() {
        let a = box("Dredge No. 1", y: 0.1), b = box("Dredge No. 3", y: 0.3), c = box("Dredge No. 2", y: 0.2)
        let selection = RegionSelection()
        selection.select(1, artifactId: "a1", documentId: "d1", in: [a, b, c])
        #expect(selection.resolvedIndices(in: [a, b, c]) == [1])
        #expect(selection.resolvedIndices(in: [b, a, c]) == [0])
        #expect(selection.resolvedIndices(in: [c, a, b]) == [2])
    }

    /// The "below and right" of #5020: the old index now names the NEXT box. It must name nothing.
    @Test("a box the list no longer holds is dropped, never replaced by whatever sits at its index")
    func aGoneBoxIsDroppedNotReplaced() {
        let a = box("one", y: 0.1), b = box("two", y: 0.2), c = box("three", y: 0.3)
        let selection = RegionSelection()
        selection.select(1, artifactId: "a1", documentId: "d1", in: [a, b, c])
        #expect(selection.resolvedIndices(in: [a, c]) == [])
    }

    @Test("toggling off drops the box's identity with its index")
    func toggleKeepsKeysInStep() {
        let a = box("one", y: 0.1), b = box("two", y: 0.2), c = box("three", y: 0.3)
        let selection = RegionSelection()
        selection.selectAll([0, 2], artifactId: "a1", documentId: "d1", in: [a, b, c])
        selection.toggle(0, artifactId: "a1", documentId: "d1", in: [a, b, c])
        #expect(selection.resolvedIndices(in: [c, b, a]) == [0])
    }

    @Test("a writer that passed no list still selects by position")
    func noListFallsBackToPosition() {
        let selection = RegionSelection()
        selection.select(1, artifactId: "a1", documentId: "d1")
        #expect(selection.resolvedIndices(in: [box("x", y: 0.1), box("y", y: 0.2)]) == [1])
        #expect(selection.resolvedIndices(in: [box("x", y: 0.1)]) == [])
    }
}
