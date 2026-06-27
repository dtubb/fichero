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
}
