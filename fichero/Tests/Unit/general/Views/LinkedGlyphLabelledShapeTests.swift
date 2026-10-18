@testable import Fichero
import XCTest

/// #5511 (6): the trailing linked glyph on document rows and thumbnails says what it means
/// (accessibility label plus help text), not an unexplained symbol. Source-shape guard.
@MainActor
final class LinkedGlyphLabelledShapeTests: XCTestCase {
    func testLinkedGlyphIsExplainedInRowAndThumbnail() throws {
        for path in ["Views/Library/LibraryViewComponents.swift", "Views/Library/LibraryThumbnailViews.swift"] {
            let source = try AppSource.code(path)
            let glyph = try XCTUnwrap(source.range(of: "Image(systemName: \"arrow.up.right.square\")"), path)
            let tail = String(source[glyph.upperBound...].prefix(400))
            XCTAssertTrue(tail.contains(".accessibilityLabel(\"Linked\")"), "\(path): linked glyph lost its label")
            XCTAssertTrue(tail.contains(".help(\"Linked:"), "\(path): linked glyph lost its help text")
        }
    }
}
