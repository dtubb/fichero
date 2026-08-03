@testable import Fichero
import XCTest

/// #3322 — one test per PRECISION RANK, because the ranks are the reason the
/// column exists.
///
/// `histdate._PRECISION_RANK` gives the engine six buckets, and each one is a
/// different claim about how much the source actually says:
///
/// | rank | precision | the claim |
/// |---|---|---|
/// | 0 | `day` | the document names a day |
/// | 1 | `month` | it names a month, not a day |
/// | 2 | `year` | it names a year, not a month |
/// | 3 | `circa` | someone estimated a year |
/// | 4 | (unrecognised) | dated, but by a precision this build cannot read |
/// | 5 | (no `date_jdn`) | not dated at all — the `created_at` fallback bucket |
///
/// `DocumentDateDisplayTests` proves the four STATES stay apart. This file
/// proves the ranks inside the dated state do too, and it exists because the
/// failure it guards is not a crash or a blank cell — it is a cell that reads
/// **more confidently than the manuscript does**. "circa 1740" rendered as
/// "1 January 1740" is a fabricated day, a fabricated month and a discarded
/// hedge, and it looks completely ordinary on screen. Nothing else in the app
/// would report it.
///
/// The mechanism that prevents it is that the client renders the engine's
/// `display` VERBATIM and owns no formatter. So every test here asserts two
/// things: the text is exactly what arrived, and it carries no component the
/// rank did not license.
final class DocumentDatePrecisionRenderingTests: XCTestCase {

    /// Build the payload the engine writes for a dated document at a given
    /// precision. `display` is `render_display`'s output — the only string the
    /// client is allowed to show.
    private func dated(
        original: String,
        display: String,
        precision: String,
        jdn: Int
    ) -> DocumentDateDisplay {
        DocumentDateDisplay.resolve(
            dateOriginal: original,
            dateJdn: jdn,
            dateMeta: ["status": "dated", "precision": precision, "display": display]
        )
    }

    /// Components a coarse date must never acquire on the way to the screen.
    /// Checked as substrings rather than by parsing, because the defect is
    /// textual: the day and the month name simply appear.
    private func assertNoInventedDayOrMonth(
        _ text: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        for monthName in ["January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"] {
            XCTAssertFalse(
                text.contains(monthName),
                "a year- or circa-precision date must not name a month; got \(text)",
                file: file, line: line
            )
        }
        XCTAssertFalse(
            text.contains("-01-01"),
            "1 January is what a year becomes when something formats it as a day; got \(text)",
            file: file, line: line
        )
    }

    // MARK: - Rank 0 — day

    /// A Gregorian day-precision date is the one case `render_display` returns
    /// UNCHANGED: the source already says everything, so there is nothing to
    /// annotate. The client must not annotate it either.
    func testDayPrecisionRendersTheSourceTextUnchanged() {
        let state = dated(original: "3 March 1791", display: "3 March 1791",
                          precision: "day", jdn: 2375292)

        XCTAssertEqual(state.text, "3 March 1791")
        XCTAssertTrue(state.isKnown)
    }

    /// A day-precision date in a non-Gregorian calendar arrives with the
    /// conversion already attached. The client shows the whole string — the
    /// conversion is part of the fact, not decoration to be stripped.
    func testDayPrecisionInAnotherCalendarKeepsTheEnginesConversion() {
        let display = "12 Thermidor An II (1794-07-30 Greg.)"
        let state = dated(original: "12 Thermidor An II", display: display,
                          precision: "day", jdn: 2376439)

        XCTAssertEqual(state.text, display)
        XCTAssertTrue(state.text.contains("An II"), "the source's own calendar must survive")
        XCTAssertTrue(state.text.contains("Greg."), "so must the conversion")
    }

    // MARK: - Rank 1 — month

    /// "March 1791" is a RANGE. It must keep reading as a month: no day may be
    /// promoted out of the range's start JDN, which is the value a client-side
    /// formatter would have had in hand.
    func testMonthPrecisionNamesNoDay() {
        let display = "March 1791 (1791-03-01 Greg.)"
        let state = dated(original: "March 1791", display: display,
                          precision: "month", jdn: 2375290)

        XCTAssertEqual(state.text, display, "rendered verbatim, range and all")
        XCTAssertFalse(state.text.contains("1 March"), "no day may be invented from the range start")
        XCTAssertFalse(state.text.contains("3 March"), "nor from anywhere else")
    }

    // MARK: - Rank 2 — year

    /// The canonical case. `render_display` collapses a year range to the bare
    /// year precisely so this cell can read "1791".
    func testYearPrecisionNamesNeitherMonthNorDay() {
        let state = dated(original: "1791", display: "1791 (1791 Greg.)",
                          precision: "year", jdn: 2375231)

        XCTAssertEqual(state.text, "1791 (1791 Greg.)")
        assertNoInventedDayOrMonth(state.text)
    }

    // MARK: - Rank 3 — circa

    /// The hedge is the fact. "circa 1740" is somebody's ESTIMATE, and a UI
    /// that renders it as a date has quietly promoted an estimate to a
    /// reading — the exact confident-sounding guess this project refuses to
    /// make. The word must survive to the screen.
    func testCircaKeepsItsHedgeAndGainsNoDay() {
        let display = "circa 1740 (1740 Greg.)"
        let state = dated(original: "circa 1740", display: display,
                          precision: "circa", jdn: 2355647)

        XCTAssertEqual(state.text, display)
        XCTAssertTrue(
            state.text.lowercased().contains("circa"),
            "dropping 'circa' turns an estimate into a reading; got \(state.text)"
        )
        assertNoInventedDayOrMonth(state.text)
    }

    /// The abbreviated form is the same claim and must be treated the same —
    /// the client does not normalise the source's wording.
    func testTheAbbreviatedCircaFormIsAlsoShownAsWritten() {
        let display = "ca. 1740 (1740 Greg.)"
        let state = dated(original: "ca. 1740", display: display,
                          precision: "circa", jdn: 2355647)

        XCTAssertEqual(state.text, display)
        assertNoInventedDayOrMonth(state.text)
    }

    // MARK: - Rank 4 — a precision this build does not recognise

    /// The engine buckets an unrecognised precision at rank 4 and still sorts
    /// it. The client has no opinion to add: it shows the engine's string.
    ///
    /// This is deliberately NOT treated like an unknown *status*. An unknown
    /// status means the client cannot tell whether there is a date at all;
    /// an unknown precision means there IS one, rendered by the engine, and
    /// only the coarseness label is unfamiliar. Falling back to "not examined"
    /// here would discard a real date over a vocabulary mismatch.
    func testAnUnrecognisedPrecisionStillShowsTheEnginesRendering() {
        let display = "1740s (1740 Greg.)"
        let state = dated(original: "1740s", display: display,
                          precision: "decade", jdn: 2355647)

        XCTAssertEqual(state.text, display)
        XCTAssertTrue(state.isKnown)
        XCTAssertFalse(state.text.contains("decade"), "no engine vocabulary reaches the user")
        assertNoInventedDayOrMonth(state.text)
    }

    // MARK: - Rank 5 — the created_at fallback bucket

    /// Rank 5 is where a document with no `date_jdn` sorts: the engine orders
    /// it by `created_at` converted to a JDN, so the list has one total order.
    ///
    /// That fallback is a SORT KEY and nothing else. The cell must never show
    /// it. An import date displayed in a column headed by the date of writing
    /// is a machine artefact wearing the costume of a historical fact — and it
    /// would be indistinguishable from a real date to the person reading it.
    func testTheSortFallbackNeverBecomesAVisibleDate() {
        let scannedIn2024 = "2024-06-01"
        let metas: [[String: Any]?] = [nil, ["status": "none_found"], ["status": "undated_explicit"]]

        for meta in metas {
            let state = DocumentDateDisplay.resolve(
                dateOriginal: nil, dateJdn: nil, dateMeta: meta
            )

            XCTAssertFalse(state.isKnown)
            XCTAssertFalse(state.text.contains(scannedIn2024))
            XCTAssertFalse(state.text.contains("2024"), "the import year is not the document's year")
            assertNoInventedDayOrMonth(state.text)
        }
    }

    /// An undated document must LOOK undated — it may not borrow the styling
    /// of a known date. `isKnown` is what the cell keys its treatment off, so
    /// this is the assertion that keeps the two visually apart.
    func testEveryUndatedRankReadsAsUndated() {
        let undated = [
            DocumentDateDisplay.resolve(dateOriginal: nil, dateJdn: nil, dateMeta: nil),
            DocumentDateDisplay.resolve(dateOriginal: nil, dateJdn: nil,
                                        dateMeta: ["status": "none_found"]),
            DocumentDateDisplay.resolve(dateOriginal: nil, dateJdn: nil,
                                        dateMeta: ["status": "undated_explicit"])
        ]

        for state in undated {
            XCTAssertFalse(state.isKnown)
            XCTAssertFalse(state.explanation.isEmpty, "each says WHY it is undated")
        }
    }

    // MARK: - The invariant that makes all of the above hold

    /// Whatever the rank, the text equals the engine's `display`. Stated once,
    /// over every rank at once, because the individual tests above would all
    /// keep passing if someone added a formatter that happened to agree with
    /// these particular fixtures. This one fails the moment the client starts
    /// producing the string itself.
    func testNoRankIsReformattedByTheClient() {
        let byRank: [(precision: String, display: String)] = [
            ("day", "3 March 1791"),
            ("month", "March 1791 (1791-03-01 Greg.)"),
            ("year", "1791 (1791 Greg.)"),
            ("circa", "circa 1740 (1740 Greg.)"),
            ("decade", "1740s (1740 Greg.)")
        ]

        for (precision, display) in byRank {
            let state = dated(original: "irrelevant — display wins",
                              display: display, precision: precision, jdn: 2375231)
            XCTAssertEqual(state.text, display, "precision \(precision) was reformatted")
        }
    }

    /// Two ranks of the SAME year must not collapse into one reading. If they
    /// did, the column would assert that a dated-to-the-day letter and a
    /// circa-dated fragment say the same thing about when they were written.
    func testTheRanksOfOneYearDoNotAllReadAlike() {
        let sameYear = [
            dated(original: "1 January 1740", display: "1 January 1740",
                  precision: "day", jdn: 2355647),
            dated(original: "January 1740", display: "January 1740 (1740-01-01 Greg.)",
                  precision: "month", jdn: 2355647),
            dated(original: "1740", display: "1740 (1740 Greg.)",
                  precision: "year", jdn: 2355647),
            dated(original: "circa 1740", display: "circa 1740 (1740 Greg.)",
                  precision: "circa", jdn: 2355647)
        ]

        XCTAssertEqual(
            Set(sameYear.map(\.text)).count, 4,
            "four different claims about 1740 must read as four different things"
        )
    }
}
