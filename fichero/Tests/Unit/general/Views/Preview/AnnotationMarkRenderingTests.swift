import CoreGraphics
@testable import Fichero
import XCTest

/// Per-kind saved-markup rendering (Daniel, 2026-08-30, reading-markup
/// rulings): the pure math behind "markup should LOOK like what it is" —
/// hex color parsing, underline/strikethrough bar geometry, check glyphs,
/// margin-note classification (ruling 3), the comma-separated tag entry
/// (ruling 4), and the word-boundary marquee's selection (ruling 2).
final class AnnotationMarkRenderingTests: XCTestCase {

    // MARK: - Hex color parsing

    func testRgbaParsesSixDigitHexWithFullAlpha() {
        let rgba = AnnotationMarkGeometry.rgba(hex: "#FFD60A")
        XCTAssertNotNil(rgba)
        XCTAssertEqual(rgba?.red ?? 0, 1.0, accuracy: 0.001)
        XCTAssertEqual(rgba?.green ?? 0, 214.0 / 255, accuracy: 0.001)
        XCTAssertEqual(rgba?.blue ?? 0, 10.0 / 255, accuracy: 0.001)
        XCTAssertEqual(rgba?.alpha ?? 0, 1.0, accuracy: 0.001)
    }

    func testRgbaParsesEightDigitHexAlpha() {
        let rgba = AnnotationMarkGeometry.rgba(hex: "#00000080")
        XCTAssertEqual(rgba?.alpha ?? 0, 128.0 / 255, accuracy: 0.001)
    }

    func testRgbaRejectsGarbageInsteadOfGuessing() {
        // A bad color renders as the default — never a crash, never a
        // silently-substituted wrong color (prefer-raise-over-fallback: nil
        // IS the honest answer here, the caller owns the default).
        XCTAssertNil(AnnotationMarkGeometry.rgba(hex: nil))
        XCTAssertNil(AnnotationMarkGeometry.rgba(hex: ""))
        XCTAssertNil(AnnotationMarkGeometry.rgba(hex: "FFD60A"))     // no #
        XCTAssertNil(AnnotationMarkGeometry.rgba(hex: "#FFD6"))      // wrong length
        XCTAssertNil(AnnotationMarkGeometry.rgba(hex: "#GGGGGG"))    // not hex
    }

    // MARK: - Per-kind bar geometry

    func testUnderlineBarHugsTheBottomEdge() {
        let rect = CGRect(x: 10, y: 20, width: 100, height: 30)
        let bar = AnnotationMarkGeometry.underlineBar(in: rect)
        XCTAssertEqual(bar, CGRect(x: 10, y: 48, width: 100, height: 2))
    }

    func testStrikethroughBarCrossesTheVerticalMiddle() {
        let rect = CGRect(x: 10, y: 20, width: 100, height: 30)
        let bar = AnnotationMarkGeometry.strikethroughBar(in: rect)
        XCTAssertEqual(bar.midY, rect.midY, accuracy: 0.001)
        XCTAssertEqual(bar.height, 2)
        XCTAssertEqual(bar.minX, rect.minX)
        XCTAssertEqual(bar.width, rect.width)
    }

    // MARK: - Check glyphs (ruling 1's ✓ ✓✓ ✓✓✓)

    func testCheckGlyphRepeatsAndClamps() {
        XCTAssertEqual(AnnotationMarkGeometry.checkGlyph(rating: 1), "✓")
        XCTAssertEqual(AnnotationMarkGeometry.checkGlyph(rating: 2), "✓✓")
        XCTAssertEqual(AnnotationMarkGeometry.checkGlyph(rating: 3), "✓✓✓")
        // Out-of-range ratings clamp instead of exploding the margin.
        XCTAssertEqual(AnnotationMarkGeometry.checkGlyph(rating: 0), "✓")
        XCTAssertEqual(AnnotationMarkGeometry.checkGlyph(rating: 9), "✓✓✓")
        XCTAssertEqual(AnnotationMarkGeometry.checkGlyph(rating: nil), "✓")
    }

    // MARK: - Margin-note classification (ruling 3)

    func testNotesInTheOuterTwelvePercentAreMarginNotes() {
        // Left margin: a narrow note whose center sits at x ≈ 0.05.
        XCTAssertTrue(AnnotationMarkGeometry.isMarginNote(rect: [0.02, 0.3, 0.06, 0.05]))
        // Right margin: center ≈ 0.95.
        XCTAssertTrue(AnnotationMarkGeometry.isMarginNote(rect: [0.92, 0.3, 0.06, 0.05]))
        // Body text: center ≈ 0.5 is NOT a margin note.
        XCTAssertFalse(AnnotationMarkGeometry.isMarginNote(rect: [0.4, 0.3, 0.2, 0.05]))
        // Straddling the margin edge: the CENTER decides. Center at 0.12
        // exactly still counts (inclusive) …
        XCTAssertTrue(AnnotationMarkGeometry.isMarginNote(rect: [0.06, 0.3, 0.12, 0.05]))
        // … while a wide box merely TOUCHING the margin does not.
        XCTAssertFalse(AnnotationMarkGeometry.isMarginNote(rect: [0.1, 0.3, 0.4, 0.05]))
        // Degenerate rects never classify.
        XCTAssertFalse(AnnotationMarkGeometry.isMarginNote(rect: [0.02, 0.3]))
    }

    // MARK: - Tag parsing (ruling 4, coding v1)

    func testTagParsingTrimsDropsEmptiesAndDeduplicates() {
        XCTAssertEqual(
            AnnotationTagParsing.parse("  poverty , Kinship,, poverty, KINSHIP , land "),
            ["poverty", "Kinship", "land"]
        )
        XCTAssertEqual(AnnotationTagParsing.parse(""), [])
        XCTAssertEqual(AnnotationTagParsing.parse(" , ,, "), [])
        XCTAssertEqual(AnnotationTagParsing.parse("one"), ["one"])
    }

    // MARK: - Word-boundary marquee selection (ruling 2)

    private func box(_ bbox: [Double], level: String) -> OCRGeometryBox {
        OCRGeometryBox(text: "w", bbox: bbox, level: level)
    }

    func testWordBandSelectsOnlyWordLevelBoxesItTouches() {
        let boxes = [
            box([0.0, 0.0, 0.5, 0.1], level: "line"),   // 0 — line, never selected
            box([0.05, 0.02, 0.1, 0.05], level: "word"), // 1 — inside band
            box([0.2, 0.02, 0.1, 0.05], level: "word"),  // 2 — inside band
            box([0.7, 0.02, 0.1, 0.05], level: "word"),  // 3 — outside band
            box([0.05, 0.5, 0.1, 0.05], level: "word")   // 4 — below band
        ]
        let band = [0.0, 0.0, 0.4, 0.1]
        // FULL-list indices come back — the engine addresses boxes by their
        // position in the artifact's whole list, lines included.
        XCTAssertEqual(AnnotationWordSelection.wordIndices(inBand: band, boxes: boxes), [1, 2])
    }

    func testWordBandWithNoWordsSelectsNothing() {
        let boxes = [box([0.0, 0.0, 0.5, 0.1], level: "line")]
        XCTAssertEqual(AnnotationWordSelection.wordIndices(inBand: [0, 0, 1, 1], boxes: boxes), [])
        // Degenerate band selects nothing rather than everything.
        XCTAssertEqual(
            AnnotationWordSelection.wordIndices(inBand: [0.1], boxes: [box([0, 0, 1, 1], level: "word")]),
            []
        )
    }

    // MARK: - AnnotationMark from the domain model

    func testMarkReadsTheTypedAnchorRectAndDefaults() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            anchor: AnnotationAnchor(rect: [0.1, 0.2, 0.3, 0.05], space: "normalized"),
            kind: .underline,
            text: nil,
            color: "#30D158"
        )
        let mark = AnnotationMark(annotation: annotation)
        XCTAssertEqual(mark.kind, .underline)
        XCTAssertEqual(mark.rect ?? [], [0.1, 0.2, 0.3, 0.05])
        XCTAssertEqual(mark.color, "#30D158")
        XCTAssertEqual(mark.text, "")
    }
}
