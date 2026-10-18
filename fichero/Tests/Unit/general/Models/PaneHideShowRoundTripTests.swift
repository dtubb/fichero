@testable import Fichero
import XCTest

/// #5027 (`panes.visibility.hide-show-round-trip`): hiding a kind then showing it brings back the SAME pane,
/// in the same place. Without it the shown pane is a fresh leaf appended after the others, with a new id and no size.
final class PaneHideShowRoundTripTests: XCTestCase {
    private func browse() -> PaneList {
        PaneList([
            .leaf(.library, config: PaneConfig(paneFraction: 0.15)),
            .leaf(.preview),
            .leaf(.reading),
        ])
    }

    func testHideThenShowReturnsTheSameList() {
        let start = browse()
        let back = start.settingVisible(.library, false).settingVisible(.library, true)
        XCTAssertEqual(back, start)
    }

    func testAHiddenPaneIsGoneFromTheListButKeepsItsIdAndSize() {
        let start = browse()
        let id = start.leafIDs(of: .library)[0]
        let hidden = start.settingVisible(.library, false)
        XCTAssertEqual(hidden.leafCount, 2)
        XCTAssertFalse(hidden.kinds.contains(.library))
        XCTAssertEqual(hidden.hiddenPanes?.first?.node.id, id)
        XCTAssertEqual(hidden.settingVisible(.library, true).config(for: id)?.paneFraction, 0.15)
    }

    func testAMiddlePaneComesBackInTheMiddle() {
        let start = browse()
        let back = start.settingVisible(.preview, false).settingVisible(.preview, true)
        XCTAssertEqual(back.nodes.map(\.id), start.nodes.map(\.id))
    }

    func testTwoPanesOfAKindBothComeBack() {
        let start = PaneList([.leaf(.preview), .leaf(.library), .leaf(.preview)])
        let back = start.settingVisible(.preview, false).settingVisible(.preview, true)
        XCTAssertEqual(back, start)
    }

    func testHidingTheLastVisiblePaneIsRefused() {
        let only = PaneList([.leaf(.library)])
        XCTAssertEqual(only.settingVisible(.library, false), only)
    }

    func testShowingNeverHiddenKindStillAppendsAFreshPane() {
        let shown = PaneList([.leaf(.library)]).settingVisible(.reading, true)
        XCTAssertEqual(shown.nodes.count, 2)
        XCTAssertNil(shown.hiddenPanes)
    }

    func testAPaneHiddenFromASplitReturnsWithItsIdAtTheEnd() {
        let inner = PaneNode.leaf(.reading)
        let list = PaneList([.leaf(.library), .split(id: UUID(), axis: .vertical, children: [.leaf(.preview), inner])])
        let back = list.settingVisible(.reading, false).settingVisible(.reading, true)
        XCTAssertEqual(back.leafIDs(of: .reading), [inner.id])
    }

    func testOldSavedListsDecodeWithoutTheStash() throws {
        let data = try JSONEncoder().encode(browse())
        XCTAssertNil(try JSONDecoder().decode(PaneList.self, from: data).hiddenPanes)
    }
}
