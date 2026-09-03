@testable import Fichero
import Foundation
import XCTest

/// Daniel, live testing 2026-09-02: "running a SECOND search does not refresh
/// the results — the list did not update until I clicked around."
///
/// The cause was a missing observer, not a bad equality check. `LibraryView`
/// keeps its visible rows in a `@State filteredDocuments` that only
/// `recomputeFiltered()` writes, and every caller of that function hangs off
/// an `.onChange` in `LibraryView+Body.swift` — for the document store's
/// revision, the entity array, the sort keys, the folder id, the ⌘F text.
/// There was no handler for `documents`, the ARRAY the shell hands in, which
/// is exactly what a transient search swaps to `searchResultDocuments`
/// (`ContentView+Navigation.swift`).
///
/// That made the FIRST search look fine by accident: `runToolbarSearch`
/// clears the sidebar selection, so `folderId` changed from a folder to nil
/// and the folder-id handler recomputed. On the second search `folderId` was
/// already nil, nothing this stack observes moved, and the grid kept the
/// previous query's rows until an unrelated click (a folder, a sort) tripped
/// one of the other handlers.
///
/// These pin the observer and the selection reset so the class cannot come
/// back the next time a handler is refactored.
final class SearchResubmissionRefreshTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static let bodySource = "Views/Library/LibraryView+Body.swift"
    private static let actionsSource = "Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift"
    private static let navigationSource = "Views/Shell/ContentView/ContentView+Navigation.swift"

    // MARK: - The missing observer

    func testLibraryRecomputesWhenTheDocumentArrayItselfChanges() throws {
        let source = try Self.appSource(Self.bodySource)

        XCTAssertTrue(
            source.contains(".onChange(of: documents) { _, _ in"),
            "LibraryView must observe its `documents` input — a re-submitted search "
                + "changes nothing else this view watches."
        )
    }

    func testTheDocumentsObserverActuallyRebuildsTheVisibleRows() throws {
        let source = try Self.appSource(Self.bodySource)

        let handler = try XCTUnwrap(
            source.components(separatedBy: ".onChange(of: documents) { _, _ in").dropFirst().first
        )
        // Only the handler body, not the rest of the file: the assertion is
        // that THIS observer recomputes, not that the file mentions the call.
        let body = String(handler.prefix(400))
        XCTAssertTrue(
            body.contains("recomputeFiltered()"),
            "Observing `documents` without recomputing would be a no-op observer."
        )
        // The projection refresh is OWNED by recomputeFiltered since
        // 2026-09-02 (the hand-paired call sites kept drifting), so the
        // handler follows the swap by calling the one owner.
        let filter = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")
        XCTAssertTrue(
            filter.contains("refreshLibraryProjection()"),
            "Canvas/space modes project from the same rows and must follow the swap too."
        )
    }

    /// The observer is only load-bearing because the shell really does swap
    /// this parameter to the search hits. If that swap ever moves, the test
    /// above would pin a handler guarding nothing.
    func testTheShellFeedsSearchHitsThroughThatSameDocumentsParameter() throws {
        let source = try Self.appSource(Self.navigationSource)

        XCTAssertTrue(
            source.contains("(activeSearchQuery == nil ? selectedDocuments : searchResultDocuments)")
        )
    }

    // MARK: - Stale selection

    func testResubmittingASearchClearsThePreviousResultSelection() throws {
        let source = try Self.appSource(Self.actionsSource)

        let run = try XCTUnwrap(
            source.components(separatedBy: "func runToolbarSearch(").dropFirst().first
        )
        let body = String(run.prefix(6000))
        XCTAssertTrue(
            body.contains("browserSelection = []"),
            "A new submission must not inherit the previous result set's selection."
        )
    }

    /// The reader re-points to the top hit ONLY when nothing is selected, so
    /// the selection reset above and this guard are one mechanism: together
    /// they are why a second search moves the reader as well as the grid.
    func testTheReaderRepointsOnlyWithNoSelection() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+SearchResults.swift")

        XCTAssertTrue(source.contains("if browserSelection.isEmpty, let first = resolved.first,"))
    }

    /// Already true before this fix, and the reason the grid is not merely
    /// stale but honest while the new query is in flight.
    func testASubmissionDropsThePreviousQueryRowsImmediately() throws {
        let source = try Self.appSource(Self.actionsSource)

        let run = try XCTUnwrap(
            source.components(separatedBy: "func runToolbarSearch(").dropFirst().first
        )
        let body = String(run.prefix(6000))
        XCTAssertTrue(body.contains("clearTransientSearchResults()"))
        XCTAssertTrue(body.contains("transientSearchLimit = Self.transientSearchPageSize"))
    }
}
