@testable import Fichero
import Testing

/// The 2×2 grid rules (Daniel, 2026-08-23: "two vertical and two horizontal"
/// must coexist — splitting one axis used to DELETE the other).
struct SplitPaneStateTests {
    @Test("splitting one axis keeps the other — the grid exists")
    func axesCoexist() {
        var state = SplitPaneState()
        state.toggleVertical()
        state.toggleHorizontal()
        #expect(state.verticalPaneCount == 2)
        #expect(state.horizontalPaneCount == 2)
        #expect(state.isGrid)
    }

    @Test("thirds are a single-axis affair — a grid axis cycles 2 → 1")
    func gridCapsAxesAtTwo() {
        var state = SplitPaneState()
        state.toggleVertical()
        state.toggleHorizontal()
        state.toggleVertical()
        #expect(state.verticalPaneCount == 1, "in a grid, toggling a 2-axis collapses it, never a third")
        #expect(state.horizontalPaneCount == 2)
    }

    @Test("a lone axis still cycles 1 → 2 → 3 → 1")
    func singleAxisStillReachesThree() {
        var state = SplitPaneState()
        state.toggleVertical()
        state.toggleVertical()
        #expect(state.verticalPaneCount == 3)
        state.toggleVertical()
        #expect(state.verticalPaneCount == 1)
    }

    @Test("X collapses the horizontal axis first, one pane at a time")
    func collapseOrderIsHorizontalFirst() {
        var state = SplitPaneState()
        state.toggleVertical()
        state.toggleHorizontal()
        state.collapseOnePane()
        #expect(state.horizontalPaneCount == 1)
        #expect(state.verticalPaneCount == 2)
        state.collapseOnePane()
        #expect(state.verticalPaneCount == 1)
        #expect(!state.hasVertical && !state.hasHorizontal)
    }
}
