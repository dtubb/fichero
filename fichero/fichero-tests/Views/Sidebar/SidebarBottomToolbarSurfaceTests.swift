import XCTest

/// Source-surface test for the sidebar bottom toolbar's mini-toolbar
/// unification (#3058, parent #2670): the bar routes through the shared
/// `AdaptiveMiniToolbarRow` with an overflow menu mirroring the secondary
/// actions, using the shared PaneFilterBar chrome on every platform.
/// Mirrors `WorkflowImportExportSurfaceTests` (deterministic, token-free).
final class SidebarBottomToolbarSurfaceTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
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
        //
        // Export is deliberately NOT here (#4100): it was removed from BOTH
        // tiers, so the mirror property still holds — the overflow reflects the
        // inline verbs, and there are now two rather than three.
        XCTAssertTrue(source.contains("Label(\"Import Files\", systemImage: \"square.and.arrow.down\")"))
        XCTAssertTrue(source.contains("Label(\"New Workflow\", systemImage: \"bolt\")"))
    }

    /// #4100: the sidebar shipped an Export button that was permanently
    /// `.disabled(true)`, with `.help("Export (not yet wired)")` saying so out
    /// loud, in both the inline bar and the overflow menu.
    ///
    /// A control that can never do anything is placeholder chrome. Per the
    /// dead-simple-UX rule a feature is ON or OFF, and a greyed button that
    /// never ungreys reads as "broken", not "coming". File ▸ Export already
    /// exports (BibTeX, Markdown static site); #2309 tracks the sidebar-scoped
    /// handler, and the control returns when there is something behind it.
    ///
    /// Asserted on BOTH tiers because the overflow mirrors the inline bar —
    /// putting it back in only one is how a dead control survives half a fix.
    func testNoDeadExportControlInEitherTier() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertFalse(code.contains("not yet wired"), "no shipped control may advertise itself as unwired")
        XCTAssertFalse(code.contains("Label(\"Export\""), "the overflow Export entry is dead chrome")
        XCTAssertFalse(code.contains(".disabled(true)"), "a permanently disabled control must not ship")

        // The guard must not have gone blind on a moved or emptied file: the
        // verbs that DO belong here are still present.
        XCTAssertTrue(code.contains("Label(\"Import Files\""))
        XCTAssertTrue(code.contains("New Workflow"))
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
