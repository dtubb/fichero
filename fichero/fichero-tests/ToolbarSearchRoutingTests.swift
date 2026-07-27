@testable import Fichero
import Foundation
import XCTest

/// #4086 — searching is navigation, not an artifact. A query typed into the
/// global toolbar search field must not persist anything: no SavedSearch row,
/// no sidebar item, no selection. Saving is the explicit "Save Search" action.
final class ToolbarSearchRoutingTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static let actionsSource = "Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift"
    private static let creationSource = "Views/Sidebar/Components/SidebarCreationHandlers.swift"
    private static let resultsSource = "Views/Shell/ContentView/ContentView+SearchResults.swift"

    func testResultsBarErasesInsetTypeAtContentRouterBoundary() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+Navigation.swift")

        XCTAssertTrue(source.contains("AnyView(transientSearchResultsBar)"))
    }

    // MARK: - Router behaviour

    func testToolbarSearchRoutesToATransientSearchWithNoSavedSearch() {
        let route = ToolbarSearchRouter.route(for: "marshall diaries")

        // #4106/S2: search stays IN the library — no mode switch, no persisted
        // object. The library column's contents swap to the transient result
        // set for the trimmed query.
        XCTAssertEqual(route?.sidebarMode, .library)
        XCTAssertEqual(route?.viewMode, .library(nil))
        XCTAssertEqual(route?.query, "marshall diaries")
    }

    func testRepeatedSearchesRouteIdenticallyPerQuery() {
        // N searches must produce N transient routes differing only by query —
        // never N distinct saved-search ids accumulating in the sidebar.
        let routes = ["one", "two", "three", "one"].compactMap {
            ToolbarSearchRouter.route(for: $0)
        }

        XCTAssertEqual(routes.count, 4)
        XCTAssertEqual(routes[0], routes[3])
        XCTAssertTrue(routes.allSatisfy {
            $0.sidebarMode == .library && $0.viewMode == .library(nil)
        })
    }

    // MARK: - Edge cases

    func testBlankQueryProducesNoRoute() {
        XCTAssertNil(ToolbarSearchRouter.route(for: ""))
        XCTAssertNil(ToolbarSearchRouter.route(for: "   "))
        XCTAssertNil(ToolbarSearchRouter.route(for: "\n\t "))
    }

    func testWhitespacePaddedQueryStillRoutesWithTrimmedQuery() {
        let route = ToolbarSearchRouter.route(for: "  cacao  ")
        XCTAssertEqual(route?.viewMode, .library(nil))
        XCTAssertEqual(route?.query, "cacao")
    }

    // MARK: - Regression: no implicit persistence

    func testToolbarSearchDoesNotSaveASearch() throws {
        let source = try Self.appSource(Self.actionsSource)

        // The pre-#4086 body called savedSearchService.saveSearch(...) on every
        // submit and selected the resulting row.
        XCTAssertFalse(source.contains("savedSearchService.saveSearch"))
        XCTAssertFalse(source.contains("selectedItemId = \"search:"))
        XCTAssertTrue(source.contains("ToolbarSearchRouter.route(for: rawQuery)"))
    }

    func testNewSearchPlaceholderIsNotPersisted() throws {
        let source = try Self.appSource(Self.creationSource)

        // createNewSearch() used to write a literal "New Search" row before
        // the user had typed anything; with the search mode retired (#4106/S2)
        // the whole creation affordance is gone.
        XCTAssertFalse(source.contains("query: \"New Search\""))
        XCTAssertFalse(source.contains("savedSearchService.saveSearch"))
        XCTAssertFalse(source.contains("createNewSearch"))
    }

    func testExplicitSaveSearchPathIsPreserved() throws {
        let source = try Self.appSource(Self.resultsSource)

        // Removing the implicit save must not remove the explicit one — it
        // now lives on the transient results bar (#4106/S2 slice B).
        XCTAssertTrue(source.contains("func saveTransientSearch() async"))
        XCTAssertTrue(source.contains("savedSearchService.saveSearch"))
        XCTAssertTrue(source.contains("Label(\"Save Search\", systemImage: \"square.and.arrow.down\")"))
    }

    func testSavedSearchesRunThroughTheTransientPath() throws {
        let sidebarSource = try Self.appSource("Views/Sidebar/Sections/SidebarView+SelectionHandling.swift")
        let resultsSource = try Self.appSource(Self.resultsSource)

        // Selecting a saved search must not resurrect a search mode — it
        // seeds the toolbar field and runs the same transient pipeline.
        XCTAssertTrue(sidebarSource.contains("onRunSavedSearch?(search)"))
        XCTAssertFalse(sidebarSource.contains("viewMode = .search"))
        XCTAssertTrue(resultsSource.contains("func runSavedSearch(_ search: SavedSearch)"))
    }

    func testFolderScopeRoutesThroughTheEngineFilter() throws {
        let resultsSource = try Self.appSource(Self.resultsSource)
        let storeSource = try Self.appSource("Models/SearchStore.swift")

        // #4107/S3: folder scope is the engine's folder_id filter (which
        // expands to the descendant set server-side), captured from the
        // browsed folder and toggleable in the results bar. No client-side
        // result filtering, and no "All libraries" until #4110.
        XCTAssertTrue(storeSource.contains("[\"folder_id\": $0]"))
        XCTAssertTrue(resultsSource.contains("transientSearchScopeIsFolder ? transientSearchContextFolder?.id : nil"))
        XCTAssertTrue(resultsSource.contains("Picker(\"Search scope\""))
        XCTAssertFalse(resultsSource.contains("All Libraries"))
    }

    func testDefaultScopeIsOneFinderStylePreference() throws {
        let actionsSource = try Self.appSource(Self.actionsSource)
        let settingsSource = try Self.appSource("Views/Settings/General/GeneralSettingsView.swift")

        // #4108/S4: ONE preference (Finder's "When performing a search"),
        // read at submit; folder default only applies when a folder exists.
        XCTAssertTrue(actionsSource.contains("Self.searchDefaultScopeIsFolderKey"))
        XCTAssertTrue(actionsSource.contains("transientSearchContextFolder != nil"))
        XCTAssertTrue(settingsSource.contains("Picker(\"When performing a search\""))
        XCTAssertTrue(settingsSource.contains("ContentView.searchDefaultScopeIsFolderKey"))
    }

    func testRealParametersReachTheEngine() throws {
        let storeSource = try Self.appSource("Models/SearchStore.swift")
        let resultsSource = try Self.appSource(Self.resultsSource)

        // #4112/S8: the 0.55 relevance floor is restored (minScore: 0.0
        // defeated the engine's noise threshold, #1054), and the type/sort
        // knobs flow from the results-bar menu into performSearch. Saved
        // searches apply AND store their parameters.
        XCTAssertTrue(storeSource.contains("static let defaultMinScore = 0.55"))
        XCTAssertTrue(storeSource.contains("minScore: Self.defaultMinScore"))
        XCTAssertFalse(storeSource.contains("minScore: 0.0"))
        XCTAssertTrue(resultsSource.contains("searchType: transientSearchType"))
        XCTAssertTrue(resultsSource.contains("transientSearchType = search.searchType"))
        XCTAssertTrue(resultsSource.contains("searchType: transientSearchType,"))
    }

    func testCompilationRunsOnExplicitSubmitOnlyAndIsAlwaysShown() throws {
        let actionsSource = try Self.appSource(Self.actionsSource)
        let resultsSource = try Self.appSource(Self.resultsSource)

        // #4116/#4117 UI halves: the explicit submit compiles in Ask mode
        // (the default) and searches raw text in Keyword mode; saved
        // searches always compile; re-run paths call runTransientSearch
        // without it. The compiled query AND any compilation failure render
        // in the results bar — AI = instrument, nothing hidden.
        XCTAssertTrue(actionsSource.contains("runTransientSearch(route.query, compile: searchFieldMode == .ask)"))
        XCTAssertTrue(resultsSource.contains("runTransientSearch(query, compile: true)"))
        XCTAssertTrue(resultsSource.contains("store.searchStats?.compiledQuery"))
        XCTAssertTrue(resultsSource.contains("store.searchStats?.compilationError"))
    }

    func testAIFirstFieldAndChatTheSearch() throws {
        let resultsSource = try Self.appSource(Self.resultsSource)
        let layoutSource = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")

        // #4117: the field's mode is a native search scope (Ask default /
        // Keyword), not extra chrome; Ask gets an inviting prompt.
        XCTAssertTrue(layoutSource.contains(".searchScopes($mode)"))
        XCTAssertTrue(layoutSource.contains("enum SearchFieldMode"))
        XCTAssertTrue(layoutSource.contains("case ask"))
        // Chat-the-search: the result set becomes the conversation's scope,
        // through the SAME router the sidebar chat entry uses.
        XCTAssertTrue(resultsSource.contains("func openChatWithSearchResults"))
        XCTAssertTrue(resultsSource.contains("ChatWithDocsRouter.mainChatRoute(documentIds: ids)"))
        XCTAssertTrue(resultsSource.contains("Label(\"Chat\""))
    }

    func testArtifactHitsPresentInTheResultsBar() throws {
        let resultsSource = try Self.appSource(Self.resultsSource)

        // #4118 UI half: the transient search requests all four legs and the
        // bar presents typed artifact hits (badge + snippet, click opens the
        // owning document).
        XCTAssertTrue(resultsSource.contains("include: [.content, .entities, .claims, .artifacts]"))
        XCTAssertTrue(resultsSource.contains("store.searchStats?.artifactHits"))
        XCTAssertTrue(resultsSource.contains("func openArtifactHit"))
        XCTAssertTrue(resultsSource.contains("navigateToDocument(doc)"))
    }

    func testTransientResultsRerunOnLibraryChanges() throws {
        let source = try Self.appSource(Self.resultsSource)

        // A document.* change bumps SearchStore.changeToken (#3249); the
        // results bar re-runs the active query so stale hits never linger.
        XCTAssertTrue(source.contains(".onChange(of: store.changeToken)"))
        XCTAssertTrue(source.contains("await runTransientSearch(query)"))
    }
}
