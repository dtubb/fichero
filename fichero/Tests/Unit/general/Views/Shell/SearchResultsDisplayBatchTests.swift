@testable import Fichero
import Foundation
import SwiftUI
import XCTest

/// Daniel's search-results batch, live 2026-09-04, on build 2.
///
///   * The Search Type submenu "shows NO current selection" — the rungs drew
///     their checkmark with a `systemImage`, and this menu drops item images.
///   * Results stop at 50 with no visible way to get the rest: the pager was
///     gated on the engine's `has_more`, which describes the DOCUMENT leg
///     alone, so an entity-answered query filled the page and reported no
///     more.
///   * Results "appear ordered by NAME not relevance": the ORDER was right,
///     the sort menu was the thing saying Name — it had no Relevance row at
///     all, so relevance was both unnamed and, once any sort was picked,
///     unreachable.
@MainActor
final class SearchResultsDisplayBatchTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    // MARK: - The tier menu says which rung is running

    func testTheTierBindingIsOnForTheActiveRungOnly() {
        var value = "hybrid"
        let binding = Binding(get: { value }, set: { value = $0 })
        XCTAssertTrue(SearchFieldOptionsMenu.tierBinding(.semantic, searchType: binding).wrappedValue)
        XCTAssertFalse(SearchFieldOptionsMenu.tierBinding(.fulltext, searchType: binding).wrappedValue)
    }

    func testTheLegacySemanticValueStillChecksTheSemanticRung() {
        var value = "semantic"
        let binding = Binding(get: { value }, set: { value = $0 })
        XCTAssertTrue(
            SearchFieldOptionsMenu.tierBinding(.semantic, searchType: binding).wrappedValue,
            "A saved search carrying the legacy pure-vector value must still show a checked row."
        )
    }

    func testSwitchingARungOnSelectsIt() {
        var value = "hybrid"
        let binding = Binding(get: { value }, set: { value = $0 })
        SearchFieldOptionsMenu.tierBinding(.fulltext, searchType: binding).wrappedValue = true
        XCTAssertEqual(value, "fulltext")
    }

    func testSwitchingARungOffIsANoOp() {
        var value = "fulltext"
        let binding = Binding(get: { value }, set: { value = $0 })
        SearchFieldOptionsMenu.tierBinding(.fulltext, searchType: binding).wrappedValue = false
        XCTAssertEqual(
            value, "fulltext",
            "This is a radio group — a retrieval tier is never 'none'."
        )
    }

    func testTheRungsDrawSelectionWithAToggleTheHostCannotDrop() throws {
        let menu = try Self.appSource("Views/Library/Search/SearchFieldOptionsMenu.swift")
        XCTAssertTrue(menu.contains("Toggle(isOn: Self.tierBinding("))
        XCTAssertFalse(
            menu.contains("Label(tier.title, systemImage: \"checkmark\")"),
            "Selection drawn as an image is selection the menu may not draw at all."
        )
    }

    // MARK: - The 50 is not a silent cap

    func testAFullPageOffersMoreEvenWhenTheEngineSaysThereIsNone() {
        XCTAssertTrue(
            SearchHonestySummary.showsPager(hasMore: false, rows: 50, limit: 50),
            """
            `has_more` describes the document leg alone; an entity-answered \
            query fills the page and reports none. A page that is exactly \
            full is never proof of the end.
            """
        )
    }

    func testAPartialPageOffersNothingMore() {
        XCTAssertFalse(SearchHonestySummary.showsPager(hasMore: false, rows: 12, limit: 50))
    }

    func testTheEngineSayingThereIsMoreIsAlwaysHonoured() {
        XCTAssertTrue(SearchHonestySummary.showsPager(hasMore: true, rows: 12, limit: 50))
    }

    func testNoRowsOffersNothing() {
        XCTAssertFalse(SearchHonestySummary.showsPager(hasMore: false, rows: 0, limit: 50))
        XCTAssertFalse(
            SearchHonestySummary.showsPager(hasMore: false, rows: 0, limit: 0),
            "A zero limit is not a full page."
        )
    }

    func testThePagerNamesTheSizeOfTheNextPage() {
        XCTAssertEqual(
            SearchHonestySummary.pagerLabel(pageSize: 50), "Load 50 more",
            "The cap the user just hit stops being invisible when the button names it."
        )
    }

    // MARK: - Relevance is a sort you can name and go back to

    func testRelevancePreservesTheRankingItArrivedIn() {
        let docs = [
            Document(id: "z", docType: .file, name: "Zebra"),
            Document(id: "a", docType: .file, name: "Apple")
        ]
        let ordered = LibrarySortField.orderedForDisplay(
            docs,
            field: .relevance,
            using: LibrarySortField.name.comparator(ascending: true)
        )
        XCTAssertEqual(
            ordered.map(\.id), ["z", "a"],
            "Re-sorting a fused ranking discards the fusion while still looking plausible."
        )
    }

    func testRelevanceIsOfferedOnlyWhileSearchResultsAreShowing() {
        XCTAssertTrue(LibrarySortField.fields(isSearching: true).contains(.relevance))
        XCTAssertFalse(
            LibrarySortField.fields(isSearching: false).contains(.relevance),
            "Outside a search there is no ranking for the word to mean."
        )
    }

    func testTheSortMenuNamesRelevanceWhileResultsAreUnsorted() {
        let state = LibraryToolbarState()
        state.searchIsActive = true
        state.userChoseSortDuringSearch = false
        XCTAssertEqual(
            state.effectiveSortField, .relevance,
            "The menu said Name over a list that was in relevance order — that WAS the report."
        )
    }

    func testAnExplicitSortDuringSearchIsWhatTheMenuThenNames() {
        let state = LibraryToolbarState()
        state.searchIsActive = true
        state.apply(LibrarySortMenuModel(selectedField: .name, ascending: true, isSearching: true))
        XCTAssertTrue(state.userChoseSortDuringSearch)
        XCTAssertEqual(state.effectiveSortField, .name)
    }

    func testChoosingRelevanceGoesBackToTheRankingRatherThanOverridingIt() {
        let state = LibraryToolbarState()
        state.searchIsActive = true
        state.apply(LibrarySortMenuModel(selectedField: .name, ascending: true, isSearching: true))
        state.apply(LibrarySortMenuModel(selectedField: .relevance, ascending: true, isSearching: true))
        XCTAssertFalse(
            state.userChoseSortDuringSearch,
            "Picking Relevance is a request to go BACK to the default, not away from it."
        )
        XCTAssertEqual(state.effectiveSortField, .relevance)
    }

    func testRelevanceIsNeverStoredAsAFolderSortPreference() {
        let state = LibraryToolbarState()
        state.sortFieldRaw = LibrarySortField.createdAt.rawValue
        state.searchIsActive = true
        state.apply(LibrarySortMenuModel(selectedField: .relevance, ascending: true, isSearching: true))
        XCTAssertEqual(
            state.sortFieldRaw, LibrarySortField.createdAt.rawValue,
            """
            Relevance means "the order the search produced", which the folder \
            you browse next has none of. Storing it would leave the per-folder \
            sort naming a ranking that no longer exists.
            """
        )
        state.searchIsActive = false
        XCTAssertEqual(state.effectiveSortField, .createdAt)
    }

    func testTheViewMenuIsHandedTheEffectiveFieldAndTheSearchContext() throws {
        let publish = try Self.appSource("Views/Library/LibraryView+KeyboardShortcuts.swift")
        let menu = try Self.appSource("App/Menus/ViewMenuLayoutSections.swift")
        XCTAssertTrue(publish.contains("value: libraryToolbar.effectiveSortField.rawValue"))
        XCTAssertTrue(publish.contains("isSearching: libraryToolbar.searchIsActive"))
        XCTAssertTrue(
            publish.contains("libraryToolbar.apply("),
            """
            The View menu's choice must route through `apply`, which decides \
            whether a mid-search pick overrides relevance. Writing the raw \
            field left the override unset, so picking Name checked Name and \
            changed nothing.
            """
        )
        XCTAssertTrue(
            menu.contains("LibrarySortField.fields(isSearching: sortField?.isSearching ?? false)"),
            "The menu offers Relevance exactly when the toolbar's sort menu does."
        )
    }

    func testTheFocusedSortValueChangesWhenTheSearchContextDoes() {
        let browsing = FocusedSortField(value: "Name", set: { _ in }, isSearching: false)
        let searching = FocusedSortField(value: "Name", set: { _ in }, isSearching: true)
        XCTAssertNotEqual(
            browsing, searching,
            """
            Equality gates the focus refresh: if the search context did not \
            count, the menu would keep the row list it was built with.
            """
        )
    }

    func testOutsideASearchTheStoredFieldStillDecides() {
        let state = LibraryToolbarState()
        state.searchIsActive = false
        state.sortFieldRaw = LibrarySortField.createdAt.rawValue
        XCTAssertEqual(state.effectiveSortField, .createdAt)
    }

    // MARK: - The preview lights the matched words

    /// The producer, the notification and the box-lighting all existed; the
    /// preview was the one surface that read the notification and not the
    /// LATCH. A search hit posts from the `detailDocument` change, before this
    /// preview's async `loadOCRGeometry()` has finished — so the handler's
    /// guard fired, cleared, and nothing re-applied once geometry landed.
    func testThePreviewReAppliesTheLatchedPassageWhenGeometryArrives() throws {
        let handlers = try Self.appSource(
            "Views/Preview/ImageViewer/ZoomableImagePreviewMac+EventHandlers.swift"
        )
        let preview = try Self.appSource("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        XCTAssertTrue(handlers.contains("func adoptLatchedPassageAnchor()"))
        XCTAssertTrue(handlers.contains("ReaderPassageFocus.latest"))
        XCTAssertTrue(
            preview.contains("adoptLatchedPassageAnchor()"),
            "The geometry load is what the latched passage was waiting for."
        )
        XCTAssertFalse(
            handlers.contains("ReaderPassageFocus.consume(documentId:"),
            """
            The preview must NOT consume the latch: the reader consumes it \
            when it lands, and both surfaces are meant to light the same \
            passage — consuming would make load order decide which one wins. \
            Matched on the CALL, not the bare symbol: the doc comment beside \
            `adoptLatchedPassageAnchor` names `ReaderPassageFocus.consume` to \
            explain why it is not called here, and a scan for the word alone \
            failed on its own explanation.
            """
        )
    }

    // MARK: - The why-match text reaches the rows

    func testListAndIconRowsCarryTheHitThatRankedThem() throws {
        let list = try Self.appSource("Views/Library/ViewModes/List/LibraryView+ListView.swift")
        let icon = try Self.appSource("Views/Library/ViewModes/Icon/LibraryView+IconMode.swift")
        let row = try Self.appSource("Views/Library/LibraryViewComponents.swift")
        XCTAssertTrue(list.contains("searchHit: searchRowHits[doc.id]"))
        XCTAssertTrue(icon.contains("searchHit: searchRowHits[doc.id]"))
        XCTAssertTrue(
            row.contains("Text(searchHit?.highlightedExcerpt ?? AttributedString(document.pageContent ?? \"\"))"),
            "A row that cannot say WHY it matched is a ranking the user has to take on faith."
        )
    }
}
