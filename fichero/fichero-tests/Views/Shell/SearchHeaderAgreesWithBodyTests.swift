@testable import Fichero
import XCTest

/// The search header's number and the sections beneath it must be one count
/// (#4403).
///
/// The header read `searchStats.totalResults`, which is the DOCUMENT leg alone.
/// The body renders four legs — documents in the grid, plus artifact, entity
/// and claim sections. So a query matching six artifacts and no documents
/// produced "3 results for 'Asprilla'" sitting directly above a section headed
/// "Artifacts (6)". Two numbers describing one search, neither wrong on its own
/// terms, and #4421's second bar is "no number that is wrong".
///
/// The header now reads the SAME `SearchHitCounts` the body is built from, so
/// the two cannot diverge by construction rather than by agreement. These tests
/// pin that property, not today's arithmetic: a future leg added to the body
/// must appear in the header automatically, and the last test is the one that
/// fails if somebody wires the header to a separate source again.
final class SearchHeaderAgreesWithBodyTests: XCTestCase {

    // MARK: - The reported case

    /// Daniel's exact shape: artifacts matched, no documents. The header must
    /// not report the document leg.
    func testHitsWithNoDocumentsAreStillCounted() {
        let counts = SearchHitCounts(documents: 0, artifacts: 6, entities: 0, claims: 0)

        XCTAssertEqual(counts.total, 6, "the header must count what the body renders")
        XCTAssertEqual(counts.nonDocument, 6, "the grid structurally cannot show these")
    }

    /// The header is the sum of every leg, not of any subset — checked across a
    /// spread rather than one case, because the defect was a subset being
    /// mistaken for the whole.
    func testTheHeaderIsTheSumOfEveryLeg() {
        for documents in 0...2 {
            for artifacts in 0...2 {
                for entities in 0...2 {
                    for claims in 0...2 {
                        let counts = SearchHitCounts(
                            documents: documents,
                            artifacts: artifacts,
                            entities: entities,
                            claims: claims
                        )
                        XCTAssertEqual(
                            counts.total,
                            documents + artifacts + entities + claims,
                            "header total must equal the legs it sits above"
                        )
                    }
                }
            }
        }
    }

    /// A count of zero legs is zero — and, more usefully, the header cannot
    /// report a non-zero total for a search that rendered nothing, which was
    /// the mirror image of the reported bug.
    func testNothingRenderedIsNothingCounted() {
        XCTAssertEqual(SearchHitCounts().total, 0)
    }

    /// The document leg alone — the value the header USED to show — is not the
    /// total whenever another leg matched. Stated as its own assertion because
    /// it is precisely the substitution that shipped.
    func testTheDocumentLegAloneIsNotTheHeaderCount() {
        let counts = SearchHitCounts(documents: 3, artifacts: 6, entities: 0, claims: 0)

        XCTAssertNotEqual(
            counts.total,
            counts.documents,
            "3 over 'Artifacts (6)' is the #4403 screenshot"
        )
        XCTAssertEqual(counts.total, 9)
    }

    // MARK: - How a future divergence gets caught

    /// The structural half, and the one that matters. Header and body must read
    /// ONE value: `transientSearchHitCounts` is computed from
    /// `searchResultDocuments` and the three hit arrays — the same arrays the
    /// sections render — so wiring the header to anything else reintroduces two
    /// sources of truth for one number.
    ///
    /// This fails if someone points the header back at a server field, at
    /// `store.results.count`, or at any second computation, whatever its
    /// arithmetic happens to be that day.
    func testTheHeaderReadsTheSameCountsTheBodyRenders() throws {
        let source = Self.code(
            of: try AppSource.text("Views/Shell/ContentView/ContentView+SearchResults.swift")
        )

        XCTAssertTrue(
            source.contains("let total = transientSearchHitCounts.total"),
            "the header must read the counts the body is built from"
        )
        XCTAssertFalse(
            source.contains("store.searchStats?.totalResults ?? store.results.count"),
            "the document-leg-only count is back in the header (#4403)"
        )
    }

    /// And the body's own count comes from the rendered arrays, not from a
    /// parallel tally — the other half of "cannot diverge".
    func testTheBodyCountsTheArraysItRenders() throws {
        let source = Self.code(
            of: try AppSource.text("Views/Shell/ContentView/ContentView+SearchResults.swift")
        )

        for leg in ["searchResultDocuments.count", "stats.artifactHits.count",
                    "stats.entityHits.count", "stats.claimHits.count"] {
            XCTAssertTrue(
                source.contains(leg),
                "\(leg) must feed SearchHitCounts, or header and body describe different things"
            )
        }
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
