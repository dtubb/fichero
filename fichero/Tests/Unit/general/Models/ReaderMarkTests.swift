@testable import Fichero
import Foundation
import Testing

/// #6454: a selection in the Reader becomes one `editorial.record` request per line, in code points, on the reading shown.
@MainActor
@Suite("Mark a stretch from the Reader (#6454)")
struct ReaderMarkTests {
    private let lines = [
        ReaderMark.Line(segmentId: "s1", representationId: "r1", text: "alpha beta"),
        ReaderMark.Line(segmentId: "s2", representationId: "r2", text: "gamma delta")
    ]

    @Test("a stretch inside one line is one request with its span")
    func oneLine() {
        let made = ReaderMark.requests(.unclear, lines: lines, selection: NSRange(location: 6, length: 4))
        let expected = EditorialRecordRequest(
            segmentId: "s1", kind: "unclear", representationId: "r1", charStart: 6, charEnd: 10, place: nil
        )
        #expect(made == [expected])
    }

    @Test("a stretch over two lines is one request per line, each on its own reading")
    func twoLines() {
        // "alpha beta\ngamma delta": the newline sits at 10; the selection runs from 'b'(6) to after 'gam'(14).
        let made = ReaderMark.requests(.lost, lines: lines, selection: NSRange(location: 6, length: 8))
        #expect(made.map(\.segmentId) == ["s1", "s2"])
        #expect(made.map(\.representationId) == ["r1", "r2"])
        #expect(made.map(\.charStart) == [6, 0])
        #expect(made.map(\.charEnd) == [10, 3])
        #expect(made.allSatisfy { $0.kind == "lost" })
    }

    @Test("an empty selection and a lone newline mark nothing")
    func nothing() {
        #expect(ReaderMark.requests(.supplied, lines: lines, selection: NSRange(location: 3, length: 0)).isEmpty)
        #expect(ReaderMark.requests(.supplied, lines: lines, selection: NSRange(location: 10, length: 1)).isEmpty)
    }

    @Test("the span counts code points, not UTF-16 units")
    func codePoints() {
        // 😀 is one code point and two UTF-16 units: the selection of "x😀y" past the first unit is code points 1...3.
        let line = [ReaderMark.Line(segmentId: "s", representationId: "r", text: "x😀y")]
        let made = ReaderMark.requests(.unclear, lines: line, selection: NSRange(location: 1, length: 3))
        #expect(made.first?.charStart == 1)
        #expect(made.first?.charEnd == 3)
    }

    @Test("the three kinds, and the menu's chord and reason")
    func kindsAndMenu() {
        #expect(ReaderMark.Kind.allCases.map(\.rawValue) == ["unclear", "lost", "supplied"])
        #expect(ReaderMarkMenu.reason == "Select text in the Reader to mark it")
    }
}
