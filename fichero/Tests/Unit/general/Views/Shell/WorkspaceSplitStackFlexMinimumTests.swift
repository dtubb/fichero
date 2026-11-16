@testable import Fichero
import Testing

/// The flexing pane keeps a usable width on an iPad (`shell.panes.ipad-row-fits-its-column`): the sized panes scale
/// down first, and the Mac keeps its 48-point floor.
struct WorkspaceSplitStackFlexMinimumTests {
    /// The Read workspace on an iPad mini with both side columns open: the Items/Reader column flexes beside a Preview
    /// that a drag left at nine tenths of the row. The column still gets 220 points.
    @Test func anIPadRowLeavesTheFlexingColumnUsable() {
        let total = 670.0
        let extents = WorkspaceSplitStack.resolvedExtents(
            [.flex, .fraction(0.7)], storedOverrides: [nil, 0.9 * total], total: total,
            flexMinimum: WorkspaceSplitStack.flexMinimum(onIOS: true)
        )
        let preview = extents[1] ?? 0
        #expect(abs(preview - (total - 220)) < 0.001)
    }

    /// A sized pane that already leaves room is not touched.
    @Test func aRowWithRoomIsUnchanged() {
        let extents = WorkspaceSplitStack.resolvedExtents(
            [.flex, .fraction(0.5)], total: 1_000, flexMinimum: WorkspaceSplitStack.flexMinimum(onIOS: true)
        )
        #expect(extents[1] == 500)
    }

    @Test func theMacKeepsItsFloor() {
        #expect(WorkspaceSplitStack.flexMinimum(onIOS: false) == 48)
    }

    /// Browse on an iPad mini: the icon strip's 15% of a 543-point row is drawn at the iOS floor, wide enough for its head.
    @Test func anIPadIconStripIsDrawnAtTheFloor() {
        let extents = WorkspaceSplitStack.resolvedExtents(
            [.fraction(0.15), .fraction(0.6), .flex], total: 543,
            minPerPane: WorkspaceSplitStack.minPerPane(onIOS: true),
            flexMinimum: WorkspaceSplitStack.flexMinimum(onIOS: true)
        )
        #expect((extents[0] ?? 0) >= 160)
        #expect(WorkspaceSplitStack.minPerPane(onIOS: false) == 48)
    }
}
