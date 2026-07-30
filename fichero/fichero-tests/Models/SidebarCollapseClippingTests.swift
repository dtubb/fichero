@testable import Fichero
import XCTest

/// #4301 — collapsing the sidebar left the bottom toolbar row painted over
/// the content column.
///
/// Cause: `sidebarStyle()` forced `.frame(minWidth: 200)` INSIDE the sidebar
/// column while the column's real minimum (owned by
/// `.navigationSplitViewColumnWidth(min:)`) is 160 and the collapse animates
/// the column toward 0. The content kept laying out 200pt wide; the List
/// clips itself, but the bottom toolbar strip does not, so its overflow
/// stayed on screen after collapse.
///
/// Contract pinned here (source-level, like SidebarLibraryBucketsTests):
///   1. The inner min-width frame must not come back — the column minimum
///      lives in ONE place, `ContentView+SidebarLayout`.
///   2. The sidebar column content is `.clipped()` so nothing in the sidebar
///      can ever paint outside its column bounds.
final class SidebarCollapseClippingTests: XCTestCase {

    func testSidebarStyleDoesNotForceAnInnerMinimumWidth() throws {
        let source = try appSource("Views/Sidebar/Sections/SidebarViewExtensions.swift")
        XCTAssertFalse(
            source.contains(".frame(minWidth: SidebarConstants.minimumWidth)"),
            "#4301: an inner minWidth frame fights the column collapse and leaves overflow painted"
        )
    }

    func testSidebarColumnContentIsClipped() throws {
        let source = try appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift")
        XCTAssertTrue(
            source.contains(".clipped()"),
            "#4301: sidebar column content must be clipped so collapse never leaves painted overflow"
        )
    }

    func testColumnMinimumStaysOwnedBySplitView() throws {
        let source = try appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift")
        XCTAssertTrue(
            source.contains("min: ContentView.sidebarMinWidth"),
            "the one owner of the sidebar minimum is navigationSplitViewColumnWidth"
        )
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
