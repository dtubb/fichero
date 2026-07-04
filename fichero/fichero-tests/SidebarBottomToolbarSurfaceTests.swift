import XCTest

/// Source-surface test for the sidebar bottom toolbar's mini-toolbar
/// unification (#3058, parent #2670): the bar routes through the shared
/// `AdaptiveMiniToolbarRow` with an overflow menu mirroring the secondary
/// actions, keeping the existing PaneFilterBar (mac) / glass (iOS) chrome.
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
        let source = try Self.appSource("Views/Sidebar/SidebarViewExtensions.swift")
        XCTAssertTrue(source.contains("AdaptiveMiniToolbarRow {"))
        XCTAssertTrue(source.contains("overflowMenu: {"))
        XCTAssertTrue(source.contains("private var overflowMenu: some View"))
        // PaneFilterBar (macOS/visionOS) + glass container (iOS) chrome preserved.
        XCTAssertTrue(source.contains("PaneFilterBar { adaptiveActionRow }"))
        XCTAssertTrue(source.contains(".glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))"))
    }

    func testOverflowMirrorsSecondaryActions() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarViewExtensions.swift")
        // These `Label(...)` forms are unique to the overflow (the inline bar uses
        // icon-only `Image` labels), so they prove the overflow mirrors secondary.
        XCTAssertTrue(source.contains("Label(\"Export\", systemImage: \"square.and.arrow.up\")"))
        XCTAssertTrue(source.contains("Label(\"Import Files\", systemImage: \"square.and.arrow.down\")"))
        XCTAssertTrue(source.contains("Label(\"New Workflow\", systemImage: \"bolt\")"))
    }

    func testEssentialTierHoldsNewItemAndDelete() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarViewExtensions.swift")
        let start = try XCTUnwrap(source.range(of: "private var essentialButtons: some View"))
        let end = try XCTUnwrap(source.range(of: "private var secondaryButtons: some View"))
        let block = String(source[start.upperBound..<end.lowerBound])
        XCTAssertTrue(block.contains("New Item"))
        XCTAssertTrue(block.contains("Remove selected item"))
    }
}
