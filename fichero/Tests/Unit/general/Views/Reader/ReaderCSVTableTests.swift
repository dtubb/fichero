@testable import Fichero
import XCTest

/// A `.csv` document reads as a TABLE in the reader (Daniel, 2026-09-04:
/// "will a reader show csv? should our reader have a csv option, to render it
/// properly?"). The parser is pure so the promise that matters — malformed
/// CSV falls back to the plain text rather than to a plausible-looking wrong
/// table — is a test, not a hope.
final class ReaderCSVTableTests: XCTestCase {

    // MARK: - Parsing

    func testPlainRowsParse() {
        XCTAssertEqual(
            ReaderCSVTable.parse("a,b\n1,2\n3,4"),
            [["a", "b"], ["1", "2"], ["3", "4"]]
        )
    }

    func testQuotedFieldsKeepTheirCommas() {
        XCTAssertEqual(
            ReaderCSVTable.parse("name,note\n\"Marshall, N.\",ledger"),
            [["name", "note"], ["Marshall, N.", "ledger"]]
        )
    }

    func testDoubledQuotesAreOneLiteralQuote() {
        XCTAssertEqual(
            ReaderCSVTable.parse("a,b\n\"say \"\"hi\"\"\",2"),
            [["a", "b"], ["say \"hi\"", "2"]]
        )
    }

    func testQuotedFieldsKeepTheirNewlines() {
        let rows = ReaderCSVTable.parse("a,b\n\"line one\nline two\",2")
        XCTAssertEqual(rows?.count, 2)
        XCTAssertEqual(rows?[1][0], "line one\nline two")
    }

    func testCarriageReturnsAreIgnored() {
        XCTAssertEqual(ReaderCSVTable.parse("a,b\r\n1,2\r\n"), [["a", "b"], ["1", "2"]])
    }

    /// CRLF is ONE extended grapheme cluster in Swift, so a `"\r"` case never
    /// matched a Windows line ending — the whole `\r\n` fell through and landed
    /// inside the field. A CSV exported from Excel parsed as a single row
    /// whose cells carried their own line breaks.
    func testACarriageReturnInsideAQuotedFieldIsKept() {
        let rows = ReaderCSVTable.parse("a,b\r\n\"line one\r\nline two\",2\r\n")
        XCTAssertEqual(rows?.count, 2)
        XCTAssertEqual(
            rows?[1][1], "2",
            "The row still terminates at the CRLF outside the quotes."
        )
        XCTAssertTrue(
            rows?[1][0].contains("line one") == true && rows?[1][0].contains("line two") == true,
            "A quoted field keeps its own line break rather than being split on it."
        )
    }

    func testATrailingNewlineIsNotAnEmptyRow() {
        XCTAssertEqual(ReaderCSVTable.parse("a,b\n1,2\n")?.count, 2)
    }

    // MARK: - What is NOT a table

    func testRaggedRowsAreRefused() {
        XCTAssertNil(
            ReaderCSVTable.parse("a,b,c\n1,2"),
            """
            A table drawn from ragged rows shifts values under the wrong \
            heading — for a ledger that is a wrong number, confidently placed.
            """
        )
    }

    func testProseIsNotATable() {
        XCTAssertNil(
            ReaderCSVTable.parse("This is a paragraph of prose.\nAnd another."),
            "One column throughout is prose, not a table."
        )
    }

    func testAnUnterminatedQuoteIsMalformed() {
        XCTAssertNil(ReaderCSVTable.parse("a,b\n\"never closed,2"))
    }

    func testEmptyTextIsNotATable() {
        XCTAssertNil(ReaderCSVTable.parse(""))
    }

    // MARK: - Rendering

    func testTheFirstRowBecomesTheHeader() {
        let html = ReaderCSVTable.html("name,total\nLeidy,12")
        XCTAssertNotNil(html)
        XCTAssertTrue(html?.contains("<th>name</th><th>total</th>") == true)
        XCTAssertTrue(html?.contains("<td>Leidy</td><td>12</td>") == true)
    }

    func testTheTitleIsRenderedWhenGiven() {
        let html = ReaderCSVTable.html("a,b\n1,2", title: "Ledger 1933")
        XCTAssertTrue(html?.contains("<h1>Ledger 1933</h1>") == true)
    }

    func testCellsAreEscapedRatherThanExecuted() {
        let html = ReaderCSVTable.html("a,b\n<script>alert(1)</script>,&")
        XCTAssertFalse(html?.contains("<script>") == true, "A cell is text, never markup.")
        XCTAssertTrue(html?.contains("&amp;") == true)
    }

    func testMalformedCSVRendersNothingSoTheReaderShowsTheText() {
        XCTAssertNil(
            ReaderCSVTable.html("just some prose"),
            "nil is the signal to fall back to the ordinary reader, which shows the same bytes."
        )
    }

    func testAVeryLongTableIsCappedAndSaysSo() {
        let rows = (0..<(ReaderCSVTable.maxRows + 20)).map { "\($0),x" }.joined(separator: "\n")
        let html = ReaderCSVTable.html("n,v\n" + rows)
        XCTAssertNotNil(html)
        XCTAssertTrue(html?.contains("Showing the first \(ReaderCSVTable.maxRows) of") == true)
    }

    func testTheRenderedPageDeclaresBothAppearances() {
        let html = ReaderCSVTable.html("a,b\n1,2")
        XCTAssertTrue(html?.contains("color-scheme: light dark") == true)
        XCTAssertTrue(html?.contains("-apple-system-body") == true, "Semantic system fonts only.")
    }
}
