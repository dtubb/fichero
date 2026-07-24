import XCTest

/// Source-surface test for the sidebar bottom toolbar's mini-toolbar
/// unification (#3058, parent #2670): the bar routes through the shared
/// `AdaptiveMiniToolbarRow` with an overflow menu mirroring the secondary
/// actions, using the shared PaneFilterBar chrome on every platform.
/// Mirrors `WorkflowImportExportSurfaceTests` (deterministic, token-free).
final class SidebarBottomToolbarSurfaceTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testBottomBarRoutesThroughAdaptiveMiniToolbarRow() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        XCTAssertTrue(source.contains("AdaptiveMiniToolbarRow {"))
        XCTAssertTrue(source.contains("overflowMenu: {"))
        XCTAssertTrue(source.contains("private var overflowMenu: some View"))
        // PaneFilterBar owns the shared Liquid Glass/material chrome.
        XCTAssertTrue(source.contains("PaneFilterBar { adaptiveActionRow }"))
    }

    func testOverflowMirrorsSecondaryActions() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        // These `Label(...)` forms are unique to the overflow (the inline bar uses
        // icon-only `Image` labels), so they prove the overflow mirrors secondary.
        XCTAssertTrue(source.contains("Label(\"Export\", systemImage: \"square.and.arrow.up\")"))
        XCTAssertTrue(source.contains("Label(\"Import Files\", systemImage: \"square.and.arrow.down\")"))
        XCTAssertTrue(source.contains("Label(\"New Workflow\", systemImage: \"bolt\")"))
    }

    func testEssentialTierHoldsNewItemAndDelete() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        let start = try XCTUnwrap(source.range(of: "private var essentialButtons: some View"))
        let end = try XCTUnwrap(source.range(of: "private var secondaryButtons: some View"))
        let block = String(source[start.upperBound..<end.lowerBound])
        XCTAssertTrue(block.contains("New Item"))
        XCTAssertTrue(block.contains("Remove selected item"))
    }

    /// #4061: the sidebar filter field lives inside the shared bottom
    /// `MiniToolbar` — one unified bottom toolbar owns the filter + the
    /// sidebar-scoped actions. The filter `TextField` + its clear button
    /// must be members of `SidebarBottomToolbar`, routed through the shared
    /// `AdaptiveMiniToolbarRow` essential tier.
    func testSidebarFilterLivesInSharedBottomMiniToolbar() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        // The toolbar holds a binding to the filter text — same state/bindings
        // as the old standalone filter bar (no logic change, just relocation).
        XCTAssertTrue(source.contains("var sidebarFilterText: Binding<String>"))
        // The filter field is a member of the toolbar, in the essential tier.
        XCTAssertTrue(source.contains("private var filterField: some View"))
        XCTAssertTrue(source.contains("TextField(\"Filter\", text: sidebarFilterText)"))
        XCTAssertTrue(source.contains("accessibilityIdentifier(\"sidebarFilterField\")"))
        // The clear button is part of the same field, shown only with text.
        XCTAssertTrue(source.contains("help(\"Clear filter\")"))
        XCTAssertTrue(source.contains("accessibilityLabel(\"Clear filter\")"))
        // The filter field is placed in the essential tier, ahead of the
        // New-item / Delete verbs — one unified row, not a separate bar.
        let essentialStart = try XCTUnwrap(source.range(of: "private var essentialButtons: some View"))
        let essentialEnd = try XCTUnwrap(source.range(of: "private var secondaryButtons: some View"))
        let essentialBlock = String(source[essentialStart.upperBound..<essentialEnd.lowerBound])
        XCTAssertTrue(essentialBlock.contains("filterField"), "filter field must live in the essential tier")
        XCTAssertTrue(essentialBlock.contains("New Item"), "New Item verb stays in the essential tier")
        XCTAssertTrue(essentialBlock.contains("Remove selected item"), "Delete verb stays in the essential tier")
    }

    /// #4061: the standalone sidebar filter chrome is gone. The old
    /// `sidebarFilterBar` member must no longer exist in
    /// `SidebarView+ViewComponents.swift` — the bottom toolbar owns the
    /// filter now, so there is no second `PaneFilterBar` stacked above it.
    func testStandaloneSidebarFilterBarIsGone() throws {
        let componentsSource = try Self.appSource(
            "Views/Sidebar/Sections/SidebarView+ViewComponents.swift"
        )
        XCTAssertFalse(componentsSource.contains("sidebarFilterBar"),
                       "standalone sidebarFilterBar must be removed — filter now lives in the bottom toolbar (#4061)")
        XCTAssertFalse(componentsSource.contains("TextField(\"Filter\", text: $sidebarFilterText)"),
                       "the filter TextField must not live in SidebarView+ViewComponents — it moved to SidebarBottomToolbar (#4061)")
        // The bottom toolbar receives the filter binding.
        XCTAssertTrue(componentsSource.contains("sidebarFilterText: $sidebarFilterText"),
                      "SidebarBottomToolbar must receive the sidebarFilterText binding")
    }
}
