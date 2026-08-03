@testable import Fichero
import Foundation
import Testing

/// #4403 (P0): search found 3 results and the body said "Select a collection
/// to view documents".
///
/// The mechanism: the grid renders `searchResultDocuments`, which is built
/// from the DOCUMENT leg of the response only. A query matching six artifacts
/// and no documents leaves that array empty, so the grid falls to its empty
/// state — which branched on the local FILTER text, found it empty, and
/// printed the prompt for having chosen no collection. Two halves of one
/// screen deriving "is there anything here?" from different state, exactly as
/// the connection surfaces did in #4380.
struct LibraryEmptyReasonTests {

    private func resolve(
        isShowingEntities: Bool = false,
        filterText: String = "",
        activeSearchQuery: String? = nil,
        hitCounts: SearchHitCounts = SearchHitCounts()
    ) -> LibraryEmptyReason {
        LibraryEmptyReason.resolve(
            isShowingEntities: isShowingEntities,
            filterText: filterText,
            activeSearchQuery: activeSearchQuery,
            hitCounts: hitCounts
        )
    }

    // MARK: - Empty-area Import (#4449)

    /// The new-user case: an empty container, nothing filtered, nothing
    /// searched. This is the ONLY reason that may offer Import, and it must —
    /// it is the first thing someone sees on launch, and #4449 exists because
    /// every obvious way in looked dead.
    @Test("an empty container offers Import on right-click")
    func emptyContainerOffersImport() {
        #expect(resolve().offersImport)
        #expect(resolve() == .noCollectionSelected)
    }

    /// A filtered or searched-out body is HIDDEN, not empty. Importing there
    /// would drop files into a container the user cannot currently see —
    /// "a `+` on a folder that imports to the root is a different bug wearing
    /// the same shape", one level over. And an entity projection has no
    /// container to import into at all.
    @Test("hidden or non-container empty states offer no Import")
    func hiddenAndProjectionStatesOfferNoImport() {
        #expect(!resolve(filterText: "Image").offersImport)
        #expect(!resolve(activeSearchQuery: "Asprilla").offersImport)
        #expect(
            !resolve(
                activeSearchQuery: "Asprilla",
                hitCounts: SearchHitCounts(artifacts: 6)
            ).offersImport
        )
        #expect(!resolve(isShowingEntities: true).offersImport)
    }

    /// Exhaustive: across every resolvable combination, Import is offered by
    /// exactly the empty-container case and nothing else. A new reason added
    /// later defaults to NOT offering, which is the safe direction — a missing
    /// menu is visible, a menu that imports somewhere unexpected is not.
    @Test("Import is offered by exactly one reason, whatever the inputs")
    func importOfferedByExactlyOneReason() {
        for showingEntities in [true, false] {
            for filter in ["", "stuck"] {
                for query in [nil, "", "q"] as [String?] {
                    for artifacts in [0, 6] {
                        let reason = resolve(
                            isShowingEntities: showingEntities,
                            filterText: filter,
                            activeSearchQuery: query,
                            hitCounts: SearchHitCounts(artifacts: artifacts)
                        )
                        #expect(reason.offersImport == (reason == .noCollectionSelected))
                    }
                }
            }
        }
    }

    // MARK: - The invariant that generalises

    /// **The body must be non-empty and on-topic whenever the header count is
    /// non-zero.** Stated here as: with a search active, no combination of
    /// counts may produce the collection prompt.
    @Test("an active search never renders the collection prompt")
    func activeSearchNeverShowsTheCollectionPrompt() {
        for documents in [0, 1, 7] {
            for artifacts in [0, 6] {
                for entities in [0, 2] {
                    for claims in [0, 3] {
                        for showingEntities in [true, false] {
                            for filter in ["", "stuck"] {
                                let reason = resolve(
                                    isShowingEntities: showingEntities,
                                    filterText: filter,
                                    activeSearchQuery: "Asprilla",
                                    hitCounts: SearchHitCounts(
                                        documents: documents,
                                        artifacts: artifacts,
                                        entities: entities,
                                        claims: claims
                                    )
                                )
                                #expect(reason != .noCollectionSelected)
                                #expect(reason != .noEntitiesInCollection)
                                #expect(!reason.message.contains("Select a collection"))
                                #expect(reason.message.contains("Asprilla"))
                            }
                        }
                    }
                }
            }
        }
    }

    /// Daniel's exact screen: 3 results, an Artifacts (6) group, an empty grid.
    /// The body has to explain the header, not contradict it.
    @Test("the reported case explains the header instead of contradicting it")
    func theReportedCaseExplainsTheHeader() {
        let reason = resolve(
            activeSearchQuery: "Asprilla",
            hitCounts: SearchHitCounts(documents: 0, artifacts: 6, entities: 2)
        )
        #expect(reason == .searchMatchedOtherKinds(
            query: "Asprilla",
            counts: SearchHitCounts(documents: 0, artifacts: 6, entities: 2)
        ))
        #expect(reason.message.contains("Asprilla"))
        #expect(reason.message.contains("6 artifacts"))
        #expect(reason.message.contains("2 entities"))
        #expect(!reason.message.contains("Select a collection"))
        #expect(reason.title == "No Matching Documents")
    }

    /// Zero results names the query — a search empty state, not an unrelated
    /// prompt about collections.
    @Test("zero results quotes the query")
    func zeroResultsQuotesTheQuery() {
        let reason = resolve(activeSearchQuery: "Asprilla")
        #expect(reason == .searchFoundNothing(query: "Asprilla"))
        #expect(reason.message == "No results for \"Asprilla\"")
        #expect(!reason.offersClearFilter, "there is no local filter to clear")
    }

    // MARK: - The non-search cases still behave

    @Test("with no search and no filter, the collection prompt is correct")
    func collectionPromptSurvivesWhereItIsTrue() {
        #expect(resolve() == .noCollectionSelected)
        #expect(resolve().message == "Select a collection to view documents")
    }

    @Test("an entity collection says so")
    func entityCollectionSaysSo() {
        let reason = resolve(isShowingEntities: true)
        #expect(reason == .noEntitiesInCollection)
        #expect(reason.systemImage == "person.3.sequence")
    }

    /// The local filter keeps its escape hatch — the stuck-filter trap.
    @Test("a local filter offers Clear Filter and nothing else does")
    func onlyTheFilterOffersClear() {
        #expect(resolve(filterText: "Image").offersClearFilter)
        #expect(!resolve().offersClearFilter)
        #expect(!resolve(activeSearchQuery: "q").offersClearFilter)
        #expect(!resolve(isShowingEntities: true).offersClearFilter)
    }

    /// A search outranks a stuck local filter: while searching, the body talks
    /// about the search.
    @Test("an active search outranks the local filter")
    func searchOutranksTheFilter() {
        let reason = resolve(filterText: "Image", activeSearchQuery: "Asprilla")
        #expect(reason.message.contains("Asprilla"))
        #expect(!reason.message.contains("Image"))
    }

    /// An empty query string is not an active search — otherwise clearing the
    /// field would strand the body in search language.
    @Test("an empty query is not an active search")
    func emptyQueryIsNotASearch() {
        #expect(resolve(activeSearchQuery: "") == .noCollectionSelected)
    }

    // MARK: - Counts

    @Test("the hit summary names every kind that matched")
    func hitSummaryNamesEveryKind() {
        #expect(SearchHitCounts(artifacts: 1).nonDocumentSummary == "1 artifact")
        #expect(SearchHitCounts(entities: 1).nonDocumentSummary == "1 entity")
        #expect(SearchHitCounts(entities: 3).nonDocumentSummary == "3 entities")
        #expect(SearchHitCounts(claims: 2).nonDocumentSummary == "2 claims")
        #expect(SearchHitCounts(artifacts: 6, entities: 2).nonDocumentSummary == "6 artifacts and 2 entities")
        #expect(
            SearchHitCounts(artifacts: 1, entities: 1, claims: 1).nonDocumentSummary
                == "1 artifact, 1 entity, and 1 claim"
        )
    }

    @Test("total counts every kind, nonDocument counts what the grid cannot show")
    func totalsAreCorrect() {
        let counts = SearchHitCounts(documents: 3, artifacts: 6, entities: 2, claims: 1)
        #expect(counts.total == 12)
        #expect(counts.nonDocument == 9)
    }

    // MARK: - Structural

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The body must read the mapping rather than re-deriving "is there
    /// anything here?" from the filter text, which is what let it disagree
    /// with the header.
    @Test("the empty state reads the shared reason")
    func emptyStateReadsTheSharedReason() throws {
        let source = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")
        #expect(source.contains("LibraryEmptyReason.resolve("))
        #expect(source.contains("let reason = emptyReason"))
        // The old shape: a bare branch on the filter text choosing the
        // collection prompt.
        #expect(!source.contains("} else if isShowingEntitiesCollection {\n                Text(\"Select an entity"))
    }

    /// The grid has to be TOLD what the search found; it cannot see the store.
    @Test("the search context reaches the library grid")
    func searchContextReachesTheGrid() throws {
        let library = try Self.appSource("Views/Library/LibraryView.swift")
        #expect(library.contains("var activeSearchQuery: String?"))
        #expect(library.contains("var searchHitCounts: SearchHitCounts"))

        let navigation = try Self.appSource("Views/Shell/ContentView/ContentView+Navigation.swift")
        #expect(navigation.contains("activeSearchQuery: activeSearchQuery"))
        #expect(navigation.contains("searchHitCounts: transientSearchHitCounts"))

        let results = try Self.appSource("Views/Shell/ContentView/ContentView+SearchResults.swift")
        #expect(results.contains("var transientSearchHitCounts: SearchHitCounts"))
        // Entities and claims are counted, not silently dropped — they are
        // returned by the engine and were previously invisible everywhere.
        #expect(results.contains("entities: stats.entityHits.count"))
        #expect(results.contains("claims: stats.claimHits.count"))
    }
}
