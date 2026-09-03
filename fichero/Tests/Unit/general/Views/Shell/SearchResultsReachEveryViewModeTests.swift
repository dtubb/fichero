@testable import Fichero
import Foundation
import XCTest

/// Daniel, live testing 2026-09-02: "while showing search results, alternate
/// view modes (e.g. timeline) must show ONLY the search results, not the
/// whole folder."
///
/// There are three ways a mode can get this wrong, and they are different
/// problems:
///
///   1. It renders `filteredDocuments`, which is derived from the `documents`
///      the shell hands in — correct by construction, ONCE that array is
///      actually observed (`SearchResubmissionRefreshTests`).
///   2. It re-queries the engine (the dataset renderers: grid, cards,
///      timeline, calendar, map). Those must pass the hit ids as a scope, and
///      an EMPTY hit list has to mean "nothing", never "everything".
///   3. Something upstream substitutes a different array entirely. That was
///      the live defect: a PINNED library pane holds a frozen snapshot that
///      wins over the result set in every mode at once.
final class SearchResultsReachEveryViewModeTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// A pin is a frozen snapshot of the rows that were showing when it was
    /// set. Left standing, it made a search look like it had run and returned
    /// the folder — in timeline, canvas and list alike, because the
    /// substitution happens above the mode switch.
    func testSubmittingASearchReleasesAPinnedLibraryScope() throws {
        let actions = try Self.appSource("Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift")
        let navigation = try Self.appSource("Views/Shell/ContentView/ContentView+Navigation.swift")

        // The substitution this guards against, still spelled the same way.
        XCTAssertTrue(navigation.contains("pinnedLibrary?.documents"))

        let run = try XCTUnwrap(
            actions.components(separatedBy: "func runToolbarSearch(").dropFirst().first
        )
        XCTAssertTrue(
            String(run.prefix(6000)).contains("pinnedLibrary = nil"),
            "A pin the results cannot be seen through is worse than no pin."
        )
    }

    /// The dataset renderers re-query rather than rendering the handed-in
    /// rows, so they carry the scope themselves.
    func testDatasetRenderersScopeTheirQueryToTheSearchHits() throws {
        let branches = try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")

        XCTAssertTrue(
            branches.contains("searchHitIds: activeSearchQuery != nil ? documents.map(\\.id) : nil")
        )
        // Timeline is one of them (Daniel named it); so are grid, cards,
        // calendar and map — they all route through `datasetModeView`.
        XCTAssertTrue(branches.contains("case .timeline:\n                datasetModeView(.timeline)"))
    }

    /// The distinction the whole scope depends on: `nil` is unscoped, `[]` is
    /// a real scope that matches nothing. If an empty hit list decayed into
    /// "no filter", a search that found nothing would render the entire
    /// library — the exact shape of the reported bug.
    func testAnEmptyHitScopeMatchesNothingRatherThanEverything() throws {
        // `AppSource.root()` is <repo>/fichero/fichero; the engine is two up.
        let repoRoot = try AppSource.root()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let query = try String(
            contentsOf: repoRoot
                .appendingPathComponent("fichero-server/src/fichero_server/db/dataset_query.py"),
            encoding: .utf8
        )

        XCTAssertTrue(query.contains("if query.ids is not None:"))
        XCTAssertTrue(query.contains("1 = 0"))
    }

    /// The client half of the same contract: `ids` is optional and passed
    /// through, so an empty array reaches the engine as an empty array.
    func testTheClientSendsTheHitScopeThrough() throws {
        let service = try Self.appSource("Services/DocumentService+Dataset.swift")

        XCTAssertTrue(service.contains("var ids: [String]?"))
        XCTAssertTrue(service.contains("ids: request.ids,"))
    }
}
