@testable import Fichero
import XCTest

/// The engine's claim versus what arrived (#4505).
///
/// `rendered_total` is the engine's count of every leg it returned. Nothing
/// compared it to what decoded, so a dropped leg, a decode failure or a
/// pagination edge would simply show fewer results and look correct doing it —
/// the silent-loss shape of a vision fanout returning empty text under a green
/// run, or MCP completing successfully having processed nothing.
final class SearchAgreementTests: XCTestCase {

    // MARK: - Absent is not zero

    /// The distinction the whole type exists for, and the one #4394 settled for
    /// the confidence badge. `rendered_total` is optional WITH A DEFAULT OF 0,
    /// so a zero is ambiguous in a way `nil` is not.

    func testAnAbsentFieldIsSilenceNotDisagreement() {
        XCTAssertEqual(SearchAgreement.resolve(claimed: nil, arrived: 7), .notStated)
        XCTAssertFalse(SearchAgreement.resolve(claimed: nil, arrived: 7).isMismatch)
    }

    /// The default firing, or an older engine sending a literal zero. Treating
    /// this as a mismatch would cry wolf on every request to an older server —
    /// an alarm that is always on is an alarm nobody reads.
    func testZeroOverANonEmptyBodyIsSilenceNotDisagreement() {
        let agreement = SearchAgreement.resolve(claimed: 0, arrived: 7)

        XCTAssertEqual(agreement, .notStated)
        XCTAssertNil(agreement.diagnosis, "silence must not be reported as loss")
    }

    /// But a zero over an EMPTY body is a real, correct agreement — an empty
    /// search genuinely returned nothing. The ambiguity is only ever about a
    /// zero standing next to arrivals.
    func testZeroOverAnEmptyBodyIsARealAgreement() {
        XCTAssertEqual(SearchAgreement.resolve(claimed: 0, arrived: 0), .agrees(count: 0))
    }

    // MARK: - What it catches

    /// The reason the field is worth reading at all: results lost between the
    /// engine and here.
    func testFewerArrivingThanClaimedIsADisagreement() {
        let agreement = SearchAgreement.resolve(claimed: 9, arrived: 6)

        XCTAssertEqual(agreement, .disagrees(claimed: 9, arrived: 6))
        XCTAssertTrue(agreement.isMismatch)
    }

    /// The other direction is equally a disagreement. It should be impossible,
    /// which is exactly why it must be reported rather than tolerated — a
    /// check that only looks one way misses the bug it did not predict.
    func testMoreArrivingThanClaimedIsAlsoADisagreement() {
        XCTAssertTrue(SearchAgreement.resolve(claimed: 3, arrived: 5).isMismatch)
    }

    func testMatchingCountsAgree() {
        XCTAssertEqual(SearchAgreement.resolve(claimed: 4, arrived: 4), .agrees(count: 4))
        XCTAssertFalse(SearchAgreement.resolve(claimed: 4, arrived: 4).isMismatch)
    }

    // MARK: - What it says

    /// A mismatch report that omits either number cannot be acted on: "results
    /// were lost" is not a bug report, "6 of 9" is.
    func testTheDiagnosisCarriesBothNumbers() throws {
        let diagnosis = try XCTUnwrap(
            SearchAgreement.resolve(claimed: 9, arrived: 6).diagnosis
        )

        XCTAssertTrue(diagnosis.contains("6"))
        XCTAssertTrue(diagnosis.contains("9"))
        XCTAssertTrue(diagnosis.contains("3"), "the size of the loss is the actionable part")
    }

    /// Only a disagreement produces a diagnosis. Agreement and silence are both
    /// quiet, so the log is signal rather than noise.
    func testOnlyADisagreementProducesADiagnosis() {
        XCTAssertNil(SearchAgreement.resolve(claimed: 4, arrived: 4).diagnosis)
        XCTAssertNil(SearchAgreement.resolve(claimed: nil, arrived: 4).diagnosis)
        XCTAssertNil(SearchAgreement.resolve(claimed: 0, arrived: 4).diagnosis)
    }

    // MARK: - It must never touch the header

    /// The separation is the point of #4505 existing separately from #4403. The
    /// header is derived from the arrays the body renders and must stay that
    /// way; this check observes and reports, and reconciling would both hide
    /// the loss and put the engine's tally back into the header by the back
    /// door.
    func testTheCheckOnlyLogsAndNeverReconciles() throws {
        let source = Self.code(of: try AppSource.text("Services/SearchService.swift"))

        XCTAssertTrue(source.contains(".reportingSearchAgreement()"))
        // No assignment back into the response, and no count adjustment.
        XCTAssertFalse(source.contains("renderedTotal ?? "))
        XCTAssertFalse(source.contains("totalResults = generated.renderedTotal"))
    }

    /// And the header still reads the rendered arrays, not this field — the
    /// #4403 property that #4505 must not undo.
    func testTheHeaderStillDoesNotReadRenderedTotal() throws {
        let source = Self.code(
            of: try AppSource.text("Views/Shell/ContentView/ContentView+SearchResults.swift")
        )

        XCTAssertFalse(
            source.contains("renderedTotal"),
            "the header must stay derived from the arrays the body renders (#4403)"
        )
        XCTAssertTrue(source.contains("let total = transientSearchHitCounts.total"))
    }

    // MARK: - Support

    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }
}
