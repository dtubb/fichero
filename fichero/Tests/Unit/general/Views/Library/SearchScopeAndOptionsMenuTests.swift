@testable import Fichero
import Foundation
import XCTest

/// Daniel, live testing 2026-09-02, two rulings about the strip of chrome
/// above the search results:
///
///   * scope should "reuse the breadcrumb concept — search the whole library
///     or the current breadcrumb context", dead simple, two choices; and
///   * the row itself (Ask/Keyword, the scope pills, the filter, Save Search)
///     should "fold into a submenu attached to the toolbar search field".
///
/// The behavioural half — how a folder becomes a named scope — is pure and
/// tested directly. The composition half is pinned by source scan, the way
/// this suite pins every other chrome invariant.
final class SearchScopeAndOptionsMenuTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static let menuSource = "Views/Library/Search/SearchFieldOptionsMenu.swift"
    private static let barSource = "Views/Shell/ContentView/ContentView+SearchResultsBar.swift"
    private static let actionsSource = "Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift"

    // MARK: - Scope IS the breadcrumb

    func testScopeCarriesTheWholeBreadcrumbTrailNotJustTheLeaf() {
        let collection = Document(id: "root", name: "Marshall Diaries")
        let box = Document(id: "box", parentId: "root", name: "1885")
        let lookup: BreadcrumbBuilder.DocumentLookup = { id in
            switch id {
            case "root": return collection
            case "box": return box
            default: return nil
            }
        }

        let scope = TransientSearchFolder.browsing(box, parentLookup: lookup)

        XCTAssertEqual(scope.id, "box")
        XCTAssertEqual(scope.path, ["Marshall Diaries", "1885"])
        // The trail is what disambiguates: a library with three folders called
        // "1885" makes the leaf label alone a coin flip.
        XCTAssertEqual(scope.trail, "Marshall Diaries ▸ 1885")
        // …and the compact label stays compact, for the inline count.
        XCTAssertEqual(scope.shortLabel, "1885")
    }

    /// "Library" is the OTHER choice, so it must never appear inside the
    /// context choice's trail — that would read as two library scopes.
    func testTheLibraryRootSegmentIsNotPartOfTheContextScope() {
        let folder = Document(id: "folder", name: "Inbox")

        let scope = TransientSearchFolder.browsing(folder, parentLookup: { _ in nil })

        XCTAssertEqual(scope.path, ["Inbox"])
        XCTAssertFalse(scope.trail.contains("Library"))
    }

    /// A folder whose ancestors are not loaded still names itself, rather
    /// than offering a blank second choice.
    func testAnUnresolvedAncestorChainStillNamesTheScope() {
        let orphan = Document(id: "child", parentId: "missing", name: "Loose Folder")

        let scope = TransientSearchFolder.browsing(orphan, parentLookup: { _ in nil })

        XCTAssertEqual(scope.name, "Loose Folder")
        XCTAssertEqual(scope.trail, "Loose Folder")
    }

    func testTheBrowsedFolderIsCapturedThroughTheBreadcrumbBuilder() throws {
        let source = try Self.appSource(Self.actionsSource)

        // Not `Document.name` — going through the builder is what stops the
        // scope disagreeing with the trail shown above it (#4416).
        XCTAssertTrue(source.contains("TransientSearchFolder.browsing("))
        XCTAssertFalse(source.contains("TransientSearchFolder(id: doc.id, name: doc.name)"))
    }

    // MARK: - Two choices, never more

    func testScopeOffersExactlyTwoChoices() throws {
        let source = try Self.appSource(Self.menuSource)

        let picker = try XCTUnwrap(
            source.components(separatedBy: "Picker(\"Look in\", selection: $scopeIsFolder)")
                .dropFirst().first
        )
        let body = String(picker.prefix(300))
        XCTAssertTrue(body.contains("Text(libraryName).tag(false)"))
        XCTAssertTrue(body.contains("Text(contextFolder.trail).tag(true)"))
        // No third scope until cross-library fan-out lands (#4110).
        XCTAssertFalse(source.contains("All Libraries"))
        XCTAssertFalse(source.contains("Everywhere"))
    }

    /// At the library root there is no second place to look, so the section
    /// is absent rather than showing one dead option.
    func testTheScopeSectionIsAbsentWithNoBrowsedContext() throws {
        let source = try Self.appSource(Self.menuSource)

        XCTAssertTrue(source.contains("if let contextFolder {"))
    }

    // MARK: - The row folded into the menu

    func testEveryFormerRowControlLivesInTheMenu() throws {
        let source = try Self.appSource(Self.menuSource)

        XCTAssertTrue(source.contains("Picker(\"Interpretation\", selection: $mode)"))
        XCTAssertTrue(source.contains("Text(\"Ask\").tag(SearchFieldMode.ask)"))
        XCTAssertTrue(source.contains("Text(\"Keyword\").tag(SearchFieldMode.keyword)"))
        XCTAssertTrue(source.contains("Picker(\"Search Type\", selection: $searchType)"))
        XCTAssertTrue(source.contains("Label(\"Save Search\", systemImage: \"square.and.arrow.down\")"))
    }

    func testTheResultsRowKeepsNoControlsOfItsOwn() throws {
        let source = try Self.appSource(Self.barSource)

        // The row says what the result set IS (count + pager). Everything
        // that CHANGES it is behind the one loupe.
        XCTAssertTrue(source.contains("searchFieldOptionsMenu(store: store)"))
        XCTAssertFalse(source.contains("pickerStyle(.segmented)"))
        XCTAssertFalse(source.contains("Picker(\"Search scope\""))
        XCTAssertFalse(source.contains("Picker(\"Search Type\""))
        XCTAssertFalse(source.contains("Label(\"Save Search\""))
        // The count and its pager stay — they are information, not controls.
        XCTAssertTrue(source.contains("Button(\"Load more\")"))
    }

    /// The menu body is separable from the button that hosts it, so the same
    /// rows can be mounted inside the toolbar search item without a second
    /// copy of the scope logic.
    func testTheMenuContentIsMountableIndependentlyOfItsButton() throws {
        let source = try Self.appSource(Self.menuSource)

        XCTAssertTrue(source.contains("struct SearchFieldOptionsMenu: View"))
        XCTAssertTrue(source.contains("struct SearchFieldOptionsMenuButton: View"))
        XCTAssertTrue(source.contains("SearchFieldOptionsMenu("))
    }

    /// A setting the menu shows must be the setting the next request uses —
    /// the menu binds the state `runTransientSearch` reads, not a copy.
    func testTheMenuBindsTheStateTheRequestIsBuiltFrom() throws {
        let bar = try Self.appSource(Self.barSource)
        let results = try Self.appSource("Views/Shell/ContentView/ContentView+SearchResults.swift")

        XCTAssertTrue(bar.contains("scopeIsFolder: $transientSearchScopeIsFolder"))
        XCTAssertTrue(bar.contains("searchType: $transientSearchType"))
        XCTAssertTrue(bar.contains("mode: searchFieldModeBinding"))
        XCTAssertTrue(
            results.contains("transientSearchScopeIsFolder ? transientSearchContextFolder?.id : nil")
        )
    }

    /// Changing WHERE a search looks is a new request, not a client-side
    /// filter — the handler moved with the control it used to hang off.
    func testChangingScopeStillReRunsTheQuery() throws {
        let source = try Self.appSource(Self.barSource)

        let handler = try XCTUnwrap(
            source.components(separatedBy: ".onChange(of: transientSearchScopeIsFolder)")
                .dropFirst().first
        )
        let body = String(handler.prefix(300))
        XCTAssertTrue(body.contains("transientSearchLimit = Self.transientSearchPageSize"))
        XCTAssertTrue(body.contains("runTransientSearch(query)"))
    }

    /// Save is offered for a result set worth saving, and never over a
    /// failure — the same condition the old button carried.
    func testSaveIsGatedOnAUsableResultSet() throws {
        let bar = try Self.appSource(Self.barSource)
        let menu = try Self.appSource(Self.menuSource)

        XCTAssertTrue(bar.contains("canSave: !store.results.isEmpty && store.searchFailure == nil"))
        XCTAssertTrue(menu.contains("if canSave {"))
    }
}
