@testable import Fichero
import XCTest

/// The hover wash (#4097) and the hover name tooltip are REMOVED — by
/// Daniel's direction (2026-08-08): both made the NAME area read as a second
/// interactive target layered on the row, when the row itself is the only
/// target. This file used to pin the wash's behaviour; it now pins the
/// absence, so neither can quietly return.
///
/// The one hover behaviour that remains is the trailing open affordance
/// (#2496), driven by `isRowHovered` — which is why `.onHover` itself stays.
final class SidebarHoverWashTests: XCTestCase {

    private func rowSource() throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Sidebar/ItemRow/SidebarItemRow.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "SidebarItemRow.swift is empty — this guard measures nothing")
        return source
    }

    func testTheHoverWashIsGone() throws {
        let source = try rowSource()
        XCTAssertFalse(
            source.contains("LibrarySelectionStyle.hoverFill"),
            "The hover wash was removed (Daniel, 2026-08-08): the name area must not "
                + "light up under the pointer. The row's only highlight is List selection."
        )
        XCTAssertFalse(
            source.contains("func sidebarRowShowsHoverWash"),
            "The wash predicate was deleted with the wash — do not re-add one without "
                + "a new decision from Daniel."
        )
    }

    func testTheNameTooltipIsGone() throws {
        let source = try rowSource()
        XCTAssertFalse(
            source.contains(".help(renameState.renamingItemId == item.id ? \"\" : item.name)"),
            "The hover tooltip repeating the row name was removed (Daniel, 2026-08-08) — "
                + "hovering the name must not pop anything over it."
        )
    }

    func testHoverTrackingRemainsForTheTrailingAffordance() throws {
        let source = try rowSource()
        XCTAssertTrue(
            source.contains(".onHover { isRowHovered = $0 }"),
            "isRowHovered still drives the trailing open affordance (#2496); removing "
                + "the wash must not remove hover tracking."
        )
    }
}
