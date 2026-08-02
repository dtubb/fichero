@testable import Fichero
import XCTest

/// #3322 — the four date states must survive to the UI.
///
/// The engine distinguishes `dated`, `undated_explicit`, `none_found` and
/// never-extracted deliberately. Rendering all four as an empty cell would kill
/// that distinction at the last inch, after the engine went to the trouble of
/// carrying it — and the two that matter most are the two easiest to conflate:
///
/// - **"the manuscript says n.d."** is evidence a historian cites,
/// - **"we have not looked yet"** is not evidence at all.
///
/// Every test here is about keeping states apart. There is deliberately no test
/// that merely checks a string renders, because "it shows something" was never
/// the risk.
final class DocumentDateDisplayTests: XCTestCase {

    private func resolve(
        original: String? = nil,
        jdn: Int? = nil,
        meta: [String: Any]? = nil
    ) -> DocumentDateDisplay {
        DocumentDateDisplay.resolve(dateOriginal: original, dateJdn: jdn, dateMeta: meta)
    }

    // MARK: - The four states are four states

    func testTheFourStatesAreAllDistinct() {
        let states: [DocumentDateDisplay] = [
            resolve(original: "12 Thermidor An II", jdn: 2376054,
                    meta: ["status": "dated", "display": "12 Thermidor An II (1794-07-30 Greg.)"]),
            resolve(meta: ["status": "undated_explicit"]),
            resolve(meta: ["status": "none_found"]),
            resolve(meta: nil)
        ]

        // Pairwise distinct — both as values and as the text a user reads,
        // because two states that render identically are one state.
        XCTAssertEqual(Set(states.map(\.text)).count, 4, "each state must read differently")
        for (i, a) in states.enumerated() {
            for b in states[(i + 1)...] {
                XCTAssertNotEqual(a, b)
            }
        }
    }

    /// The distinction the engine built this for.
    func testUndatedInSourceIsNotTheSameAsNotExamined() {
        let saysUndated = resolve(meta: ["status": "undated_explicit"])
        let neverRan = resolve(meta: nil)

        XCTAssertNotEqual(saysUndated, neverRan)
        XCTAssertNotEqual(saysUndated.text, neverRan.text)
        XCTAssertNotEqual(saysUndated.explanation, neverRan.explanation)
    }

    /// "We looked and found nothing" is also not "we never looked".
    func testNoDateFoundIsNotTheSameAsNotExamined() {
        XCTAssertNotEqual(resolve(meta: ["status": "none_found"]), resolve(meta: nil))
    }

    /// A nil `date_meta` is the ANSWER "never extracted", not a missing value.
    /// Defaulting it to an empty dictionary would make every unexamined
    /// document read as "extraction ran and found nothing".
    func testMissingMetaMeansNotExaminedRatherThanNoDateFound() {
        XCTAssertEqual(resolve(meta: nil), .notExamined)
        XCTAssertNotEqual(resolve(meta: nil), .noDateFound)
    }

    /// An empty dictionary is a real payload with no status — still unknown,
    /// but it must not crash or claim a date.
    func testEmptyMetaIsNotExamined() {
        XCTAssertEqual(resolve(meta: [:]), .notExamined)
    }

    // MARK: - The dated case never invents a format

    /// Precision governs the display SERVER-side (`histdate.render_display`),
    /// so the client renders the engine's string verbatim. A year-precision
    /// date must read "1791", and the only way to guarantee that here is to
    /// never reformat.
    func testDatedRendersTheEnginesDisplayVerbatim() {
        let display = "March 1791 (1791 Greg.)"
        XCTAssertEqual(
            resolve(original: "March 1791", jdn: 2375000, meta: ["status": "dated", "display": display]),
            .dated(text: display)
        )
    }

    func testAYearPrecisionDateIsNotRenderedAsADay() {
        let state = resolve(original: "1791", jdn: 2375000,
                            meta: ["status": "dated", "display": "1791", "precision": "year"])

        XCTAssertEqual(state.text, "1791")
        XCTAssertFalse(state.text.contains("January"), "a year must never render as a day")
        XCTAssertFalse(state.text.contains("1 "), "no day component may be invented")
    }

    /// Older rows written before `display` existed still have the verbatim
    /// manuscript text. Falling back to it is honest; formatting the JDN would
    /// not be.
    func testFallsBackToTheVerbatimOriginalWhenDisplayIsAbsent() {
        XCTAssertEqual(
            resolve(original: "3 Kal. Mar. 1483", jdn: 2260000, meta: ["status": "dated"]),
            .dated(text: "3 Kal. Mar. 1483")
        )
    }

    /// A contradiction — status says dated, nothing readable came with it.
    /// Rendering a date built from the JDN would assert a precision and a
    /// calendar the payload never claimed.
    func testDatedWithNothingReadableDoesNotInventADateFromTheJDN() {
        let state = resolve(original: nil, jdn: 2376054, meta: ["status": "dated"])

        XCTAssertEqual(state, .noDateFound)
        XCTAssertFalse(state.isKnown)
    }

    func testDatedWithAnEmptyDisplayIsNotADate() {
        XCTAssertEqual(
            resolve(original: "", jdn: 1, meta: ["status": "dated", "display": ""]),
            .noDateFound
        )
    }

    // MARK: - Forward compatibility

    /// A status this build does not know must not be shown raw — engine
    /// vocabulary in front of a user is worse than an honest "not examined".
    func testAnUnknownStatusDoesNotLeakEngineVocabulary() {
        let state = resolve(meta: ["status": "some_future_status"])

        XCTAssertEqual(state, .notExamined)
        XCTAssertFalse(state.text.contains("some_future_status"))
    }

    // MARK: - isKnown

    func testOnlyTheDatedCaseCountsAsKnown() {
        XCTAssertTrue(resolve(original: "1893", meta: ["status": "dated", "display": "1893"]).isKnown)
        XCTAssertFalse(resolve(meta: ["status": "undated_explicit"]).isKnown)
        XCTAssertFalse(resolve(meta: ["status": "none_found"]).isKnown)
        XCTAssertFalse(resolve(meta: nil).isKnown)
    }
}
