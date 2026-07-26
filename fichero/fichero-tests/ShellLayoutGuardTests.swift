import XCTest

/// Regression guard for the 3-column shell layout (#3069): the main
/// NavigationSplitView must use the `.balanced` style so the sidebar stays a
/// disjoint column BESIDE the content/library list — never overlaid on top of
/// it (which clipped the list's leading edge). Source-surface (deterministic,
/// no running app), mirroring `WorkflowImportExportSurfaceTests`.
final class ShellLayoutGuardTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testShellUsesBalancedSplitViewStyle() throws {
        // The NavigationSplitView and its style moved into the Layout/ split
        // (408e4ae81); ContentView.swift keeps only `body`.
        let source = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        XCTAssertTrue(
            source.contains(".navigationSplitViewStyle(.balanced)"),
            "The main NavigationSplitView must be .balanced so the sidebar stays a "
                + "disjoint column beside the content list and never overlays it (#3069)."
        )
        // Never regress to the overlay style, which occludes the content list.
        XCTAssertFalse(
            source.contains(".navigationSplitViewStyle(.prominentDetail)"),
            "prominentDetail overlays the sidebar on the detail — the #3069 bug."
        )
    }
}
