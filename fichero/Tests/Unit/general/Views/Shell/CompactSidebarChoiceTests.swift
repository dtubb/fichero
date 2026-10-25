@testable import Fichero
import SwiftUI
import XCTest

/// `m2p.ios.sidebar-to-library` (#5964): at compact width a sidebar choice moves the split view to the content column; at
/// regular width, and with no size class measured yet, nothing moves. Not run on the Pro (no simulator); the M4/builder runs it.
final class CompactSidebarChoiceTests: XCTestCase {
    func testCompactWidthMovesToTheContentColumnFromEitherColumn() {
        for current in [NavigationSplitViewColumn.sidebar, .content, .detail] {
            // The compact flow is iOS only (`shouldUseCompactNavigationFlow` is false on macOS): the Mac test run
            // proves nothing moves there, the simulator run proves the move.
            #if os(macOS)
            let expected = current
            #else
            let expected = NavigationSplitViewColumn.detail
            #endif
            XCTAssertEqual(
                ContentView.preferredCompactColumnAfterSidebarChoice(horizontalSizeClass: .compact, current: current),
                expected, "from \(current)")
        }
    }

    func testRegularWidthAndAnUnmeasuredSizeClassLeaveTheColumnAlone() {
        for current in [NavigationSplitViewColumn.sidebar, .content, .detail] {
            XCTAssertEqual(
                ContentView.preferredCompactColumnAfterSidebarChoice(horizontalSizeClass: .regular, current: current), current)
            XCTAssertEqual(
                ContentView.preferredCompactColumnAfterSidebarChoice(horizontalSizeClass: nil, current: current), current)
        }
    }

    /// Choosing the row that is already selected writes no selection, so the window re-runs its handlers on a counter:
    /// the sidebar's selection state bumps it on every project choice, selected already or not.
    func testChoosingAProjectAlwaysBumpsTheRevealCounter() {
        let state = SidebarSelectionState()
        let library = UUID()
        let before = state.revealGeneration
        state.selectProject(library)
        state.selectProject(library)  // the same row again
        XCTAssertEqual(state.revealGeneration, before &+ 2)
    }
}
