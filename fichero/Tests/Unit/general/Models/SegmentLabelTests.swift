@testable import Fichero
import FicheroAPIClient
import XCTest

/// On-image labels in the line's RESOLVED direction (#5199, Daniel on the calfa chinese-vertical page: the
/// hover label drew '登庸九' across a vertical column). Read from the engine's own answer for the real
/// imported pages, recorded by `test_reader_directions.py`. What breaks without these: a column's label is
/// laid across it, a Syriac label runs left to right, or a mixed line reorders the words around it.
final class SegmentLabelTests: XCTestCase {
    private func pageText(_ name: String) throws -> Components.Schemas.DerivedText {
        let url = try AppSource.sibling("Tests").appendingPathComponent("Fixtures/segments/\(name).page-text.json")
        return try JSONDecoder().decode(Components.Schemas.DerivedText.self, from: Data(contentsOf: url))
    }

    func testEveryLineOfTheVerticalChinesePageIsAColumn() throws {
        let directions = SegmentLabel.directions(from: try pageText("calfa_chinese-vertical_chi1087-0065"))
        XCTAssertFalse(directions.isEmpty)
        XCTAssertEqual(Set(directions.values), ["ttb"], "the engine's answer, not a guess from the characters")
        let label = SegmentLabel.layout("登庸九", direction: "ttb")
        XCTAssertTrue(label.vertical)
        XCTAssertEqual(label.text, "登\n庸\n九", "one character per row, read down")
    }

    func testTheSyriacPagesLinesAreRightToLeftEachAnIsolate() throws {
        let directions = SegmentLabel.directions(from: try pageText("syriac_onb-syr1-0001"))
        XCTAssertEqual(Set(directions.values), ["rtl", "ltr"], "Syriac lines, and the Latin folio number")
        let label = SegmentLabel.layout("ܚܨܪܘܢ", direction: "rtl")
        XCTAssertTrue(label.rightToLeft && !label.vertical)
        XCTAssertEqual(label.text, "\u{2067}ܚܨܪܘܢ\u{2069}", "a right-to-left isolate: it never reorders its neighbours")
        XCTAssertEqual(SegmentLabel.layout("1v", direction: "ltr").text, "\u{2066}1v\u{2069}")
        XCTAssertEqual(SegmentLabel.layout("1v", direction: nil).text, "\u{2068}1v\u{2069}", "unresolved: first strong decides")
    }
}
