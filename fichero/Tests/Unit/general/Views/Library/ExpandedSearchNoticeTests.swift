@testable import Fichero
import Foundation
import Testing

/// The library's "Expanded Search Results" notice (Daniel, 2026-08-31).
///
/// Two contracts, and the mounting half is not observable without a GUI, so
/// one half is a real behavioural check on the pure gate and the other is a
/// source guard:
///
///   - the SENTENCE is the product claim. It says the app can search by
///     meaning; if the wording drifts, the honesty of the claim drifts with
///     it, so it is pinned exactly;
///   - the GATE is what makes the claim true. The engine's `"fulltext"` mode
///     runs no embeddings leg, so the notice must not appear over its
///     results. `shouldPresent` is the whole decision and is testable
///     directly;
///   - the MOUNTING must additionally require a completed, non-empty search
///     and must read the persisted dismissal key. Both are asserted against
///     the source, since neither an `@AppStorage` read nor a `.safeAreaInset`
///     child can be reached from a unit test.
struct ExpandedSearchNoticeTests {

    private func source(_ path: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(path), encoding: .utf8)
    }

    // MARK: - The words

    @Test("Title and body are the approved wording, exactly")
    func noticeTextIsExact() {
        #expect(ExpandedSearchNotice.title == "Expanded Search Results")
        #expect(
            ExpandedSearchNotice.message
                == "Fichero can look for results based on what you mean, not just the words you type."
        )
    }

    // MARK: - The gate that makes the words true

    @Test("Only the engine modes that embed the query present the notice")
    func onlySemanticModesPresent() {
        #expect(ExpandedSearchNotice.shouldPresent(searchType: "semantic"))
        #expect(ExpandedSearchNotice.shouldPresent(searchType: "hybrid"))
        // Keyword-only search: the sentence would be a false claim.
        #expect(!ExpandedSearchNotice.shouldPresent(searchType: "fulltext"))
        // The engine's empty-query stat, and anything a future engine adds:
        // unrecognised means unproven, not assumed.
        #expect(!ExpandedSearchNotice.shouldPresent(searchType: "none"))
        #expect(!ExpandedSearchNotice.shouldPresent(searchType: ""))
    }

    // MARK: - The mounting

    @Test("Dismissal persists under the agreed key and gates the body")
    func dismissalIsPersistedAndGates() throws {
        let text = try source("Views/Library/Search/ExpandedSearchNotice.swift")
        #expect(text.contains("\"search.expandedResultsNoticeDismissed\""))
        #expect(text.contains("@AppStorage(ExpandedSearchNotice.dismissedKey)"))
        // Both halves of the view's own gate in one condition: dismissed AND mode.
        #expect(text.contains("if !dismissed, Self.shouldPresent(searchType: searchType)"))
        #expect(text.contains("accessibilityIdentifier(\"expandedSearchNotice\")"))
    }

    @Test("Mounted only over a completed, non-empty search in the results bar")
    func mountedOnlyOverLiveResults() throws {
        let text = try source("Views/Shell/ContentView/ContentView+SearchResultsBar.swift")
        // It is mounted at all…
        #expect(text.contains("expandedSearchNotice(store: store)"))
        #expect(text.contains("ExpandedSearchNotice(searchType: stats.searchType)"))
        // …and only inside the three-part guard. A search that failed, is
        // still running (no stats), or found nothing shows no banner.
        #expect(text.contains("if let stats = store.searchStats,"))
        #expect(text.contains("store.searchFailure == nil,"))
        #expect(text.contains("!searchResultDocuments.isEmpty"))
        // The REQUESTED type is not the gate — the engine's reported one is.
        #expect(!text.contains("ExpandedSearchNotice(searchType: transientSearchType)"))
    }
}
