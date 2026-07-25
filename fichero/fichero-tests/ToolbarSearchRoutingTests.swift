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
    private static let helpersSource = "Views/Library/Search/SearchView+Helpers.swift"
    private static let searchViewSource = "Views/Library/Search/SearchView.swift"

    // MARK: - Router behaviour

    func testToolbarSearchRoutesToATransientSearchWithNoSavedSearch() {
        let route = ToolbarSearchRouter.route(for: "marshall diaries")

        XCTAssertEqual(route?.sidebarMode, .search)
        // The nil payload is the whole point: no SavedSearch is created, so the
        // route has nothing to point at.
        XCTAssertEqual(route?.viewMode, .search(nil))
    }

    func testRepeatedSearchesAllRouteToTheSameTransientDestination() {
        // N searches must produce N identical transient routes — never N
        // distinct saved-search ids accumulating in the sidebar.
        let routes = ["one", "two", "three", "one"].compactMap {
            ToolbarSearchRouter.route(for: $0)
        }

        XCTAssertEqual(routes.count, 4)
        // AppViewMode is Equatable, not Hashable — compare pairwise.
        XCTAssertTrue(routes.allSatisfy { $0 == routes[0] })
        XCTAssertEqual(routes.first?.viewMode, .search(nil))
    }

    // MARK: - Edge cases

    func testBlankQueryProducesNoRoute() {
        XCTAssertNil(ToolbarSearchRouter.route(for: ""))
        XCTAssertNil(ToolbarSearchRouter.route(for: "   "))
        XCTAssertNil(ToolbarSearchRouter.route(for: "\n\t "))
    }

    func testWhitespacePaddedQueryStillRoutes() {
        XCTAssertEqual(ToolbarSearchRouter.route(for: "  cacao  ")?.viewMode, .search(nil))
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

        // createNewSearch() used to write a literal "New Search" row before the
        // user had typed anything.
        XCTAssertFalse(source.contains("query: \"New Search\""))
        XCTAssertFalse(source.contains("savedSearchService.saveSearch"))
        XCTAssertTrue(source.contains("viewMode = .search(nil)"))
    }

    func testExplicitSaveSearchPathIsPreserved() throws {
        let source = try Self.appSource(Self.helpersSource)

        // Removing the implicit save must not remove the explicit one.
        XCTAssertTrue(source.contains("func saveCurrentQuery() async"))
        XCTAssertTrue(source.contains("savedSearchService.saveSearch"))
    }

    func testSaveSearchButtonStillOffersToPersistATransientSearch() throws {
        let source = try Self.appSource(Self.searchViewSource)

        // The button is gated on savedSearch == nil, which is now the normal
        // state for every toolbar search rather than a rare one.
        XCTAssertTrue(source.contains("if savedSearch == nil"))
        XCTAssertTrue(source.contains("Label(\"Save Search\", systemImage: \"square.and.arrow.down\")"))
    }

    func testTransientSearchRunsItsQueryOnAppear() throws {
        let source = try Self.appSource(Self.searchViewSource)

        // With savedSearch == nil the query already sits in the shared toolbar
        // field, so `.onChange(of: queryText)` never fires and onAppear must
        // search on any non-empty queryText — not only when a saved search
        // supplied one. The marker comment pins the intent to the issue.
        XCTAssertTrue(source.contains("// Transient searches (#4086)"))
        XCTAssertTrue(source.contains("performSearch()"))
    }
}
