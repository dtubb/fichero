@testable import Fichero
import Foundation
import XCTest

/// #4229 — dropping on a sidebar folder highlighted (and appeared to select)
/// the folder's entire child subtree.
///
/// Mechanism: `.sidebarDropHighlight` sat on the OUTER `DisclosureGroup` of an
/// expandable row, so its accent-fill overlay painted the group's full frame —
/// which, expanded, is the folder plus every child row. At 0.45 accent
/// opacity that wash is indistinguishable from a mass selection; a mid-drag
/// tree rebuild could also strand `isTargeted` true, making the "selection"
/// persistent. Two invariants pin the fix (structural pins — the view's frame
/// geometry has no cheaper observable seam; #4241's snapshot test is the
/// durable follow-up):
///
/// 1. The highlight modifier is attached INSIDE the DisclosureGroup label —
///    only the target row lights — while `.onDrop` stays on the group so the
///    chevron/indent strip keeps its #571 drop surface.
/// 2. `handleRowDrop` resets `isDropTargeted` at the drop, so no stuck wash;
///    and no sidebar drop path writes selection state.
final class SidebarDropHighlightScopeTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// Source with all whitespace removed, so structural assertions are not
    /// hostage to indentation.
    private func compact(_ source: String) -> String {
        source.filter { !$0.isWhitespace }
    }

    func testExpandableRowHighlightIsScopedToTheLabelNotTheGroup() throws {
        let source = try Self.appSource(
            "Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift"
        )
        let compacted = compact(source)
        // The label applies the highlight (all three row shapes)…
        XCTAssertTrue(
            compacted.contains("fullWidthLabel.sidebarDropHighlight("),
            "drop highlight must wrap the LABEL — on the DisclosureGroup it " +
            "painted the whole child subtree (#4229)"
        )
        // …and never a closing brace (the DisclosureGroup) — that attachment
        // is the exact regression shape: the accent wash over folder + subtree.
        XCTAssertFalse(
            compacted.contains("}.sidebarDropHighlight("),
            "highlight is back on a container's closing brace — the subtree " +
            "wash regression (#4229)"
        )
        // The wider drop surface stays on the group (#571).
        XCTAssertTrue(source.contains(".onDrop("), "group keeps its drop surface")
    }

    func testRowDropResetsHoverTargetingAtTheDrop() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift")
        let handler = try XCTUnwrap(
            source.range(of: "func handleRowDrop").map { String(source[$0.lowerBound...]) }
        )
        XCTAssertTrue(
            handler.contains("isDropTargeted = false"),
            "the drop must clear the hover wash itself — a mid-drag rebuild " +
            "can strand isTargeted true, which reads as a stuck selection (#4229)"
        )
    }

    func testSidebarDropPathsNeverWriteSelectionState() throws {
        // The drop pipeline moves documents; it must not touch what is
        // selected. Scan every sidebar drop-path source for selection writes.
        for path in [
            "Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift",
            "Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift"
        ] {
            let source = try Self.appSource(path)
            for forbidden in [
                "selectedItemId =",
                "selectedDestinations =",
                "selectedDestinations.insert",
                "selectedDestinations.formUnion",
                "selectedDestination ="
            ] {
                XCTAssertFalse(
                    source.contains(forbidden),
                    "\(path) writes selection (`\(forbidden)`) — a drop must " +
                    "never alter the selection set (#4229)"
                )
            }
        }
    }
}
