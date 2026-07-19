import XCTest

/// Guardrail for #3875 (icon-grid / list selection too dim). Daniel: a FOCUSED
/// pane must show a real Finder-blue selection, not a 12% wash; an UNFOCUSED
/// pane stays gray. These source-reading assertions lock the focused/unfocused
/// split and the strengthened fills so a future edit can't quietly revert the
/// selection to the old faint 0.12 accent wash.
final class LibrarySelectionStrengthTests: XCTestCase {
    func testFocusedSelectionFillIsStrongUnfocusedStaysGray() throws {
        let source = try Self.appSource("Views/Library/ViewModes/LibraryView+DisplayModes.swift")
        // Focused = strong accent; unfocused = faint gray. Kept on one line so
        // the pairing can't drift apart.
        XCTAssertTrue(
            source.contains("isPaneFocused ? Color.accentColor.opacity(0.85) : Color.secondary.opacity(0.12)"),
            "selectionFill must give the focused pane a strong accent fill and the unfocused pane a gray wash (#3875)."
        )
        // List rows must receive the strong selectionFill, not the old 12% accent wash.
        XCTAssertTrue(
            source.contains("tint: selectionFill"),
            "List rows must receive selectionFill (#3875)."
        )
        XCTAssertFalse(
            source.contains("selectionTint.opacity(0.12)"),
            "The old faint selectionTint.opacity(0.12) list-row wash must be gone (#3875)."
        )
    }

    func testIconTileSelectedFillIsStrengthened() throws {
        // #4024: DocumentThumbnailView/EntityThumbnailView (icon tiles) moved to LibraryThumbnailViews.swift.
        let source = try Self.appSource("Views/Library/LibraryThumbnailViews.swift")
        // Thumbnails keep their full-accent border but get a visible focused fill.
        XCTAssertTrue(
            source.contains("effectiveSelectedTint.opacity(0.2)"),
            "Selected icon tiles must use the strengthened 0.2 fill so focused selection reads clearly (#3875)."
        )
        XCTAssertFalse(
            source.contains("effectiveSelectedTint.opacity(0.1)"),
            "The old barely-visible 0.1 tile fill must be gone (#3875)."
        )
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
