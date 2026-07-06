@testable import Fichero
import XCTest

final class SplitPaneStateTests: XCTestCase {
    func testVerticalToggleCyclesThroughTwoThreeAndOnePanes() {
        var state = SplitPaneState()

        state.toggleVertical()
        XCTAssertEqual(state.verticalPaneCount, 2)
        XCTAssertEqual(state.horizontalPaneCount, 1)
        XCTAssertTrue(state.hasVertical)
        XCTAssertEqual(state.paneCount, 2)

        state.toggleVertical()
        XCTAssertEqual(state.verticalPaneCount, 3)
        XCTAssertEqual(state.horizontalPaneCount, 1)
        XCTAssertTrue(state.hasVertical)
        XCTAssertEqual(state.paneCount, 3)

        state.toggleVertical()
        XCTAssertEqual(state.verticalPaneCount, 1)
        XCTAssertEqual(state.horizontalPaneCount, 1)
        XCTAssertFalse(state.hasVertical)
        XCTAssertEqual(state.paneCount, 1)
    }

    func testHorizontalToggleClearsVerticalStateAndCyclesThroughThreePanes() {
        var state = SplitPaneState()

        state.toggleVertical()
        state.toggleHorizontal()

        XCTAssertEqual(state.verticalPaneCount, 1)
        XCTAssertEqual(state.horizontalPaneCount, 2)
        XCTAssertTrue(state.hasHorizontal)
        XCTAssertEqual(state.paneCount, 2)

        state.toggleHorizontal()
        XCTAssertEqual(state.horizontalPaneCount, 3)
        XCTAssertTrue(state.hasHorizontal)
        XCTAssertEqual(state.paneCount, 3)
    }

    func testCollapseOnePaneStepsBackToTwoThenOne() {
        var state = SplitPaneState()
        state.toggleVertical()
        state.toggleVertical()

        state.collapseOnePane()
        XCTAssertEqual(state.verticalPaneCount, 2)
        XCTAssertTrue(state.hasVertical)
        XCTAssertEqual(state.paneCount, 2)

        state.collapseOnePane()
        XCTAssertEqual(state.verticalPaneCount, 1)
        XCTAssertFalse(state.hasVertical)
        XCTAssertEqual(state.paneCount, 1)

        state.collapseOnePane()
        XCTAssertEqual(state.verticalPaneCount, 1)
        XCTAssertEqual(state.horizontalPaneCount, 1)
    }

    /// The horizontal branch of `collapseOnePane` (vertical already at 1) — the
    /// previously-uncovered `horizontalPaneCount > 1` path.
    func testCollapseOnePaneStepsBackHorizontalWhenVerticalIsUnsplit() {
        var state = SplitPaneState()
        state.toggleHorizontal()
        state.toggleHorizontal()
        XCTAssertEqual(state.horizontalPaneCount, 3)

        state.collapseOnePane()
        XCTAssertEqual(state.horizontalPaneCount, 2)
        XCTAssertEqual(state.verticalPaneCount, 1)
        XCTAssertTrue(state.hasHorizontal)

        state.collapseOnePane()
        XCTAssertEqual(state.horizontalPaneCount, 1)
        XCTAssertFalse(state.hasHorizontal)
        XCTAssertEqual(state.paneCount, 1)
    }

    /// Only one axis is ever split at a time: toggling vertical must reset an
    /// active horizontal split back to 1 (the mirror of the horizontal test).
    func testToggleVerticalClearsActiveHorizontalSplit() {
        var state = SplitPaneState()
        state.toggleHorizontal()
        state.toggleHorizontal()
        XCTAssertEqual(state.horizontalPaneCount, 3)

        state.toggleVertical()
        XCTAssertEqual(state.verticalPaneCount, 2)
        XCTAssertEqual(state.horizontalPaneCount, 1)
        XCTAssertFalse(state.hasHorizontal)
        XCTAssertTrue(state.hasVertical)
        XCTAssertEqual(state.paneCount, 2)
    }

    /// A fresh 1×1 state reports no split on either axis.
    func testDefaultStateHasNoSplit() {
        let state = SplitPaneState()
        XCTAssertFalse(state.hasVertical)
        XCTAssertFalse(state.hasHorizontal)
        XCTAssertEqual(state.paneCount, 1)
    }
}
