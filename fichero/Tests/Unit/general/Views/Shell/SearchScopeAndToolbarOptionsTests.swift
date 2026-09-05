@testable import Fichero
import Foundation
import Testing

/// The chrome must name the library it is actually showing, and the way a
/// search RUNS must be reachable before you have run one (Daniel, live
/// 2026-09-03).
///
///   * "The toolbar search shows scope 'Test' while Marshall Diaries is
///     selected, and Marshall Diaries should appear in the document island."
///     Both surfaces read one value, `searchChromeLibraryName`, so both were
///     wrong for one reason: `chromeUX.resultsLibraryName` is written at
///     request time and was cleared only by `clearTransientSearch()`, which
///     `handleLibraryChange()` calls only when a query is up. Search in one
///     library, dismiss the results, switch libraries — and the previous
///     library's name outlived the results it described.
///
///   * The search options lived only in the results bar, which exists only
///     after a search returns. Changing how a search runs required having
///     already run one the wrong way.
@MainActor
struct SearchScopeAndToolbarOptionsTests {

    private static func appSource(_ relativePath: String) throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    // MARK: - The chrome names the library it is showing

    /// The results-library name is per-RESULTS state: with no search on
    /// screen there is nothing for it to be the name OF, so the window's own
    /// library is the answer. Gating on `activeSearchQuery` makes the
    /// staleness structurally impossible rather than a clearing chore.
    @Test("the library name falls back to the window whenever no search is up")
    func libraryNameIgnoresResultsNameWithNoActiveSearch() throws {
        let source = try Self.appSource(
            "Views/Shell/ContentView/ContentView+SearchResults.swift"
        )
        let body = try #require(
            source.components(separatedBy: "var searchChromeLibraryName: String {")
                .dropFirst().first
        )
        let declaration = String(body.prefix(400))
        #expect(declaration.contains("guard activeSearchQuery != nil"))
        #expect(declaration.contains("windowState.library?.displayName"))
    }

    /// Belt and braces, and the honest state: this window now shows a
    /// different library, so a name describing the previous one's results is
    /// cleared whether or not a query happened to be up.
    @Test("switching library clears the results-library name unconditionally")
    func libraryChangeClearsTheResultsLibraryName() throws {
        let source = try Self.appSource(
            "Views/Shell/ContentView/ContentView+StateEvents.swift"
        )
        let handler = try #require(
            source.components(separatedBy: "func handleLibraryChange() {")
                .dropFirst().first
        )
        #expect(String(handler.prefix(1200)).contains("chromeUX.resultsLibraryName = nil"))
    }

    /// One value, so the scope chip and the document island cannot name
    /// different libraries — the property both already read.
    @Test("the island and the scope chip read the same library name")
    func islandAndScopeShareOneName() throws {
        let toolbar = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        let bar = try Self.appSource(
            "Views/Shell/ContentView/ContentView+SearchResultsBar.swift"
        )
        #expect(toolbar.contains("libraryName: searchChromeLibraryName"))
        #expect(bar.contains("return searchChromeLibraryName"))
    }

    // MARK: - Search options reach the main toolbar

    /// The options menu is mounted beside the system search item. SwiftUI
    /// gives no API for hanging a menu off `DefaultToolbarItem(kind: .search)`
    /// itself, so a neighbouring loupe is the closest placement the framework
    /// allows — and it must be its OWN toolbar identity, never sharing
    /// com.apple.SwiftUI.search (#3163's crash class).
    @Test("the main toolbar mounts the search options beside the search item")
    func toolbarMountsSearchOptionsBesideTheSearchField() throws {
        let container = try Self.appSource(
            "Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"
        )
        #expect(container.contains("DefaultToolbarItem(kind: .search, placement: .primaryAction)"))
        #expect(container.contains("ContentToolbarID.searchOptions"))
        #expect(container.contains("searchOptionsToolbarButton"))

        let ids = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(ids.contains("static let searchOptions = \"fichero.searchOptions\""))
    }

    /// Both mounts are two views of ONE state. The toolbar button binds the
    /// same values the request is built from, so the menu can never show a
    /// setting the next search will not honour.
    @Test("the toolbar options bind the same state the request is built from")
    func toolbarOptionsBindTheRequestState() throws {
        let source = try Self.appSource(
            "Views/Shell/ContentView/ContentView+ToolbarSearch.swift"
        )
        let button = try #require(
            source.components(separatedBy: "var searchOptionsToolbarButton: some View {")
                .dropFirst().first
        )
        let body = String(button.prefix(900))
        #expect(body.contains("mode: searchFieldModeBinding"))
        #expect(body.contains("scopeIsFolder: $transientSearchScopeIsFolder"))
        #expect(body.contains("searchType: $transientSearchType"))
        #expect(body.contains("libraryName: searchChromeLibraryName"))
    }

    /// Two controls sharing one accessibility identifier make "the options
    /// menu" ambiguous to a UI test, so each mount names itself.
    @Test("the two option-menu mounts have distinct accessibility identities")
    func optionMenuMountsAreDistinctlyIdentified() throws {
        let menu = try Self.appSource("Views/Library/Search/SearchFieldOptionsMenu.swift")
        #expect(menu.contains("var accessibilityId: String = \"library.search.optionsMenu\""))
        #expect(menu.contains(".accessibilityIdentifier(accessibilityId)"))

        let toolbar = try Self.appSource(
            "Views/Shell/ContentView/ContentView+ToolbarSearch.swift"
        )
        #expect(toolbar.contains("accessibilityId: \"toolbar.search.optionsMenu\""))
    }

    // MARK: - The reader's stream follows the visible list

    /// While a search is up the visible list is the results, so the reader
    /// pages through the results — not the browsed folder's children
    /// (Daniel: the reader's stream became the original folder location).
    @Test("the immersive reader pages through the visible list, not the folder")
    func immersiveReaderFollowsTheVisibleList() throws {
        let source = try Self.appSource(
            "Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"
        )
        #expect(source.contains("siblings: immersiveReadingSiblings"))
        let stream = try #require(
            source.components(separatedBy: "var immersiveReadingSiblings: [Document] {")
                .dropFirst().first
        )
        // `selectedDocuments` is already "results while searching, browsed
        // children otherwise" — reusing it is what keeps the reader and the
        // grid from disagreeing about which list the user is in.
        #expect(String(stream.prefix(300)).contains("selectedDocuments.filter"))
    }

    // MARK: - A saved search's tier dies with its results (Daniel, 2026-09-04)

    /// `runSavedSearch` applies the saved search's stored `searchType`, and it
    /// used to leave it there: run a saved FULLTEXT search once and every
    /// query typed afterwards was quietly keyword-only. That is exactly the
    /// "is it doing keyword by default, not semantic?" experience — a
    /// downgrade nobody chose, on a default the toolbar otherwise seeds to
    /// hybrid.
    @Test("a tier a saved search imposed returns to the default")
    func savedSearchTierReturnsToTheDefault() {
        #expect(
            ContentView.retrievalTierAfterSavedSearch(
                applied: "fulltext", current: "fulltext"
            ) == SearchRetrievalTier.defaultTier.requestValue
        )
    }

    /// The distinction the whole fix turns on. A tier the user picked in the
    /// options menu is a deliberate choice; resetting it on the next query
    /// would be a second bug wearing the first one's clothes.
    @Test("a tier the user chose is left alone")
    func userChosenTierSurvives() {
        #expect(
            ContentView.retrievalTierAfterSavedSearch(
                applied: nil, current: "hybrid_graph"
            ) == "hybrid_graph"
        )
    }

    /// The user re-chose after the saved search ran: theirs wins.
    @Test("a tier changed since the saved search applied it is the user's")
    func aChangedTierBelongsToTheUser() {
        #expect(
            ContentView.retrievalTierAfterSavedSearch(
                applied: "fulltext", current: "hybrid_graph"
            ) == "hybrid_graph"
        )
    }

    @Test("both moments that end a saved search's results restore the tier")
    func bothEndingsRestoreTheTier() throws {
        let results = try Self.appSource(
            "Views/Shell/ContentView/ContentView+SearchResults.swift"
        )
        let submit = try Self.appSource(
            "Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift"
        )
        #expect(results.contains("savedSearchAppliedTier = search.searchType"))
        #expect(
            results.contains("restoreDefaultRetrievalTier()"),
            "Dismissing the results ends the tier they were produced with."
        )
        #expect(
            submit.contains("restoreDefaultRetrievalTier()"),
            "So does submitting a new query — that is the moment Daniel hit."
        )
    }
}
