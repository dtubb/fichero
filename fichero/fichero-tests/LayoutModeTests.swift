@testable import Fichero
import XCTest

/// Tests for the `LayoutMode` enum that drives the main-content area's
/// content-vs-preview split. Tiny enum but central — toolbar picker,
/// View menu, and @SceneStorage all key off these raw values.
final class LayoutModeTests: XCTestCase {

    func testAllCasesCovered() {
        XCTAssertEqual(LayoutMode.allCases.count, 3)
        XCTAssertTrue(LayoutMode.allCases.contains(.none))
        XCTAssertTrue(LayoutMode.allCases.contains(.standard))
        XCTAssertTrue(LayoutMode.allCases.contains(.widescreen))
    }

    // Raw values are what @SceneStorage persists. If any of these
    // change accidentally, every user's saved window state breaks.
    func testRawValuesAreStable() {
        XCTAssertEqual(LayoutMode.none.rawValue, "None")
        XCTAssertEqual(LayoutMode.standard.rawValue, "Standard")
        XCTAssertEqual(LayoutMode.widescreen.rawValue, "Widescreen")
    }

    func testIdReturnsRawValue() {
        for mode in LayoutMode.allCases {
            XCTAssertEqual(mode.id, mode.rawValue)
        }
    }

    // SF Symbols — wrong name = blank icon = silent UI bug.
    func testIconNames() {
        XCTAssertEqual(LayoutMode.none.icon, "square")
        XCTAssertEqual(LayoutMode.standard.icon, "rectangle.split.1x2")
        XCTAssertEqual(LayoutMode.widescreen.icon, "rectangle.split.2x1")
    }

    func testDescriptions() {
        XCTAssertFalse(LayoutMode.none.description.isEmpty)
        XCTAssertFalse(LayoutMode.standard.description.isEmpty)
        XCTAssertFalse(LayoutMode.widescreen.description.isEmpty)
    }

    func testKeyboardShortcuts() {
        XCTAssertEqual(LayoutMode.none.keyboardShortcut, "0")
        XCTAssertEqual(LayoutMode.standard.keyboardShortcut, "1")
        XCTAssertEqual(LayoutMode.widescreen.keyboardShortcut, "2")
    }

    func testWidescreenPanePlanKeepsCanvasAndReadingWhenLibraryIsHidden() {
        let plan = WidescreenPanePlan.make(
            showDocumentGrid: false,
            showDocumentCanvas: true,
            showReadingPane: true
        )

        XCTAssertFalse(plan.showsLibraryPane)
        XCTAssertTrue(plan.showsCanvasPane)
        XCTAssertTrue(plan.showsReadingPane)
        XCTAssertFalse(plan.showsLibraryDivider)
        XCTAssertTrue(plan.showsCanvasReadingDivider)
    }

    func testWidescreenPanePlanShowsLibraryDividerOnlyWhenLibraryHasANeighbor() {
        let listOnly = WidescreenPanePlan.make(
            showDocumentGrid: true,
            showDocumentCanvas: false,
            showReadingPane: false
        )
        XCTAssertFalse(listOnly.showsLibraryDivider)

        let listWithCanvas = WidescreenPanePlan.make(
            showDocumentGrid: true,
            showDocumentCanvas: true,
            showReadingPane: false
        )
        XCTAssertTrue(listWithCanvas.showsLibraryDivider)
        XCTAssertFalse(listWithCanvas.showsCanvasReadingDivider)
    }
}
