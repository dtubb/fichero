@testable import Fichero
import XCTest

/// Line text is drawn with the bundled script fonts' cascade wherever it appears (#5842, `layers.text.font-from-script-and-period`):
/// a Syriac or MUFI letter the system font lacks must not show as a box in Correct This Line or in the reader-disagreement
/// popover. Source-shape guard, as `TranscriptionFontWiringShapeTests`.
@MainActor
final class LineTextFontShapeTests: XCTestCase {
    private let cascade = "BundledFonts.shared.font(.body)"

    func testCorrectThisLineDrawsItsWordsInTheCascade() throws {
        // Whitespace-insensitive: a re-indent of the view must not break the guard.
        let source = try AppSource.code("Views/Segments/CorrectThisLine.swift")
            .components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
        XCTAssertTrue(source.contains("TextField(\"Words\", text: $words) .font(\(cascade))"))
        XCTAssertTrue(source.contains("Text(line.text ?? \"\") .font(\(cascade))"))
    }

    func testTheDisagreementPopoverDrawsAVariantInTheCascade() throws {
        let source = try AppSource.code("Views/Reader/Disagreement/ReaderDisagreementView.swift")
        XCTAssertTrue(source.contains("Text(row.text).font(\(cascade))"))
    }
}
