@testable import Fichero
import XCTest

/// The #1696 pane-visibility invariant: mutations go through `settingVisible`,
/// which never lets all three content panes hide at once. Pure value type — no
/// ContentView / SceneStorage needed.
final class PaneVisibilityTests: XCTestCase {

    func testHidingALastPaneIsRefused() {
        // Only canvas visible — hiding it would empty the content area → refused.
        let only = PaneVisibility(grid: false, canvas: true, reading: false)
        XCTAssertEqual(only.settingVisible(.canvas, false), only)
        XCTAssertTrue(only.settingVisible(.canvas, false).isAnyVisible)
    }

    func testHidingAPaneWhenOthersRemainSucceeds() {
        let two = PaneVisibility(grid: true, canvas: true, reading: false)
        let hidGrid = two.settingVisible(.grid, false)
        XCTAssertFalse(hidGrid.grid)
        XCTAssertTrue(hidGrid.canvas)
        XCTAssertTrue(hidGrid.isAnyVisible)
    }

    func testShowingAHiddenPaneAlwaysSucceeds() {
        let one = PaneVisibility(grid: false, canvas: true, reading: false)
        let shown = one.settingVisible(.reading, true)
        XCTAssertTrue(shown.reading)
        XCTAssertTrue(shown.canvas)
    }

    func testSettingAPaneToItsCurrentValueIsANoOp() {
        let all = PaneVisibility(grid: true, canvas: true, reading: true)
        XCTAssertEqual(all.settingVisible(.grid, true), all)
    }

    func testVisibleReadsEachPane() {
        let v = PaneVisibility(grid: true, canvas: false, reading: true)
        XCTAssertTrue(v.visible(.grid))
        XCTAssertFalse(v.visible(.canvas))
        XCTAssertTrue(v.visible(.reading))
    }

    /// Even from a (legacy) all-hidden state, hiding stays refused — the recovery
    /// to a visible pane is the widescreen-entry net, not `settingVisible`.
    func testAllHiddenStateStaysRefusedOnFurtherHide() {
        let none = PaneVisibility(grid: false, canvas: false, reading: false)
        XCTAssertEqual(none.settingVisible(.grid, false), none)
        // Showing recovers it.
        XCTAssertTrue(none.settingVisible(.grid, true).grid)
    }
}
