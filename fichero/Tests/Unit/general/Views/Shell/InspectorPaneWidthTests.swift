@testable import Fichero
import Foundation
import XCTest

/// #4287 — the inspector's width cap was too narrow: text wrapped even when
/// the user dragged the pane wider. Mac-native rule: the SPLITTER owns width
/// within sane min/max; inner content fills what it's given.
final class InspectorPaneWidthTests: XCTestCase {

    func testSplitterCapIsGenerous() {
        // 420 was the artificial ceiling that forced wrapping on wide windows.
        // The cap exists only to stop a drag from swallowing the window.
        XCTAssertGreaterThanOrEqual(ContentView.inspectorMaxWidth, 800)
        XCTAssertLessThan(
            ContentView.inspectorMinWidth, ContentView.inspectorMaxWidth
        )
    }

    func testRestoreClampUsesTheSplitterBoundsNotAHardcodedCap() {
        // The onAppear restore used to clamp to a stray hardcoded 400 —
        // TIGHTER than the splitter's own max — silently shrinking a
        // user-dragged width on every launch. The clamp is now the exact
        // splitter bounds.
        XCTAssertEqual(
            ContentView.restoredInspectorWidth(700), 700,
            "a width the splitter allows must survive restore"
        )
        XCTAssertEqual(
            ContentView.restoredInspectorWidth(10_000), ContentView.inspectorMaxWidth
        )
        XCTAssertEqual(
            ContentView.restoredInspectorWidth(0), ContentView.inspectorMinWidth
        )
        XCTAssertEqual(
            ContentView.restoredInspectorWidth(-50), ContentView.inspectorMinWidth,
            "corrupted persisted values clamp to the floor, never crash"
        )
    }

    /// #6009: the bounds sit on the inspector content's root (last modifier in the `.inspector` closure), not inside the
    /// container under the environment and geometry wrappers, where the column was not resizable.
    func testTheColumnBoundsAreTheLastModifierOnTheInspectorContent() throws {
        let root = try AppSource.text("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        let recorded = try XCTUnwrap(root.range(of: ".recordsPaneFrame(UIPane.inspector.frameKey, in: windowState)"))
        let bounds = try XCTUnwrap(root.range(of: ".inspectorColumnBounds()"))
        XCTAssertLessThan(recorded.lowerBound, bounds.lowerBound)
        let container = try AppSource.text("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift")
        XCTAssertEqual(container.components(separatedBy: "inspectorColumnWidth(").count - 1, 1,
                       "one place sets the column's bounds")
    }
}
