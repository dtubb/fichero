import XCTest

/// Source-surface tests for the Library bottom action bar's mini-toolbar
/// unification (#3057, parent #2670): the bar routes through the shared
/// `AdaptiveMiniToolbarRow` and its overflow menu mirrors the secondary
/// actions, while keeping the existing glass chrome + touch-target metrics.
/// Mirrors `WorkflowImportExportSurfaceTests` (deterministic, token-free).
final class LibraryBottomActionBarSurfaceTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testBottomBarRoutesThroughAdaptiveMiniToolbarRow() throws {
        let source = try Self.appSource("Views/Library/LibraryView.swift")
        // The bar is rewrapped on the shared component, not a hand-rolled HStack.
        XCTAssertTrue(source.contains("AdaptiveMiniToolbarRow {"))
        XCTAssertTrue(source.contains("overflowMenu: {"))
        XCTAssertTrue(source.contains("bottomBarOverflowMenu"))
        // Existing glass chrome + shared touch-target metrics preserved (#2474/#2550).
        XCTAssertTrue(source.contains(".glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))"))
        XCTAssertTrue(source.contains("bottomBarTouchTarget"))
    }

    func testOverflowMenuMirrorsSecondaryActions() throws {
        let source = try Self.appSource("Views/Library/LibraryView.swift")
        // The overflow menu carries the secondary verbs as Labels with the SAME
        // underlying actions as the inline buttons.
        XCTAssertTrue(source.contains("Label(\"Export BibTeX\", systemImage: \"square.and.arrow.up\")"))
        XCTAssertTrue(source.contains("Label(\"Run Workflow\", systemImage: \"bolt\")"))
        XCTAssertTrue(source.contains("exportSelectedBibtex()"))
        XCTAssertTrue(source.contains("showWorkflowPicker = true"))
    }

    func testEssentialTierHoldsPrimaryVerbs() throws {
        let source = try Self.appSource("Views/Library/LibraryView.swift")
        let start = try XCTUnwrap(source.range(of: "private var essentialBarButtons: some View"))
        let end = try XCTUnwrap(source.range(of: "private var secondaryBarButtons: some View"))
        let block = String(source[start.upperBound..<end.lowerBound])
        // New Folder / Delete / Import are the always-inline essential verbs.
        XCTAssertTrue(block.contains("New Folder"))
        XCTAssertTrue(block.contains("Delete"))
        XCTAssertTrue(block.contains("Import"))
    }
}
