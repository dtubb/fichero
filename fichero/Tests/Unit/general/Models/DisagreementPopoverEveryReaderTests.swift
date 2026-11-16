import Foundation
import Testing

@testable import Fichero

/// `source.disagree.popover-lists-every-reader-and-the-lines-other-readings` (#6453): a word's popover counts "n of N"
/// over the readers that read the line, and lists each reader that did not, quietly, as "<label>: <why>".
@MainActor
struct DisagreementPopoverEveryReaderTests {
    nonisolated static let json = """
    {"page_id":"p","readers":[{"id":"k","label":"Kraken"},{"id":"v","label":"Apple Vision"},{"id":"q","label":"Qwen"}],
     "page_agreement":0.9,"normalised_as":"as_written","definition":"Agreement is 1 − d / L.",
     "lines":[{"segment_id":"l1","reference_reader":"k","text":"una casa","agreement":0.9,
      "absent":[{"reader":"q","why":"read the page, not tied to this line"}],
      "words":[{"text":"casa","char_start":4,"char_end":8,"agreement":0.5,
       "variants":[{"text":"casa","readers":["k"]},{"text":"cosa","readers":["v"]}]}]}]}
    """

    private func page() throws -> ReadingDisagreement { try ReadingDisagreement.decode(Data(Self.json.utf8)) }

    @Test func anAbsentReaderIsListedWithItsWhy() throws {
        #expect(try page().absentRows(inLine: 0) == ["Qwen: read the page, not tied to this line"])
    }

    @Test func nOfNCountsTheReadersOfTheLine() throws {
        let page = try page()
        let rows = page.variantRows(for: page.lines[0].words[0], inLine: 0)
        #expect(rows.map(\.count) == ["1 of 2", "1 of 2"])
    }

    @Test func aLineWithNoAbsentReaderCountsEveryReader() throws {
        let page = try page()
        #expect(page.variantRows(for: page.lines[0].words[0]).map(\.count) == ["1 of 3", "1 of 3"])
        #expect(page.absentRows(inLine: 5).isEmpty)
    }
}
