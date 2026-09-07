@testable import Fichero
import XCTest

final class AppNavigationHistoryTests: XCTestCase {
    func testPushAndBackAndForwardTrackHistory() {
        var history = AppNavigationHistory()
        let first = entry("library", itemId: "folder-a", sidebarId: "sidebar-a", detailId: "doc-a")
        let second = entry("search", itemId: "search-a", sidebarId: "sidebar-b", detailId: "doc-b")

        history.push(first)
        history.push(second)

        XCTAssertEqual(history.current, second)
        XCTAssertTrue(history.canGoBack)
        XCTAssertFalse(history.canGoForward)

        XCTAssertEqual(history.goBack(), first)
        XCTAssertFalse(history.canGoBack)
        XCTAssertTrue(history.canGoForward)

        XCTAssertEqual(history.goForward(), second)
        XCTAssertFalse(history.canGoForward)
    }

    func testPushDropsForwardBranchWhenNavigatingFromPastEntry() {
        var history = AppNavigationHistory()
        let first = entry("library", itemId: "folder-a")
        let second = entry("search", itemId: "search-a")
        let third = entry("chat", itemId: "chat-a")

        history.push(first)
        history.push(second)
        _ = history.goBack()

        history.push(third)

        XCTAssertEqual(history.current, third)
        XCTAssertFalse(history.canGoForward)
        XCTAssertEqual(history.stack, [first, third])
    }

    func testPushCapsHistoryDepth() {
        var history = AppNavigationHistory()

        for index in 0..<(AppNavigationHistory.maxDepth + 1) {
            history.push(entry("library", itemId: "item-\(index)"))
        }

        XCTAssertEqual(history.stack.count, AppNavigationHistory.maxDepth)
        XCTAssertEqual(history.stack.first?.viewItemId, "item-1")
        XCTAssertEqual(history.current?.viewItemId, "item-\(AppNavigationHistory.maxDepth)")
    }

    func testSearchQueryRoundTripsThroughBackAndForward() {
        var history = AppNavigationHistory()
        // Browsing a folder, then a search over it, then the hit's source
        // location — the exact double-click-to-reveal sequence (#4106).
        let browsing = entry("library", itemId: "folder-a")
        let searching = entry("library", itemId: "folder-a", detailId: "hit-1", searchQuery: "marshall")
        let revealed = entry("library", itemId: "folder-b", detailId: "hit-1")

        history.push(browsing)
        history.push(searching)
        history.push(revealed)

        // Back from the revealed source returns to the SEARCH (query intact),
        // not straight to bare folder browsing.
        XCTAssertEqual(history.goBack()?.searchQuery, "marshall")
        // Back again reaches plain browsing with no query.
        XCTAssertNil(history.goBack()?.searchQuery)
        // Forward re-enters the search.
        XCTAssertEqual(history.goForward()?.searchQuery, "marshall")
    }

    func testEntriesDifferingOnlyBySearchQueryAreNotDeduped() {
        var history = AppNavigationHistory()
        let browsing = entry("library", itemId: "folder-a")
        let searching = entry("library", itemId: "folder-a", searchQuery: "foo")

        history.push(browsing)
        history.push(searching)

        // Same folder, but the search overlay is a distinct navigable state —
        // push must not collapse it into the browsing entry.
        XCTAssertEqual(history.stack, [browsing, searching])
        XCTAssertTrue(history.canGoBack)
    }

    func testSearchQueryDefaultsToNilForPlainBrowsing() {
        XCTAssertNil(entry("library", itemId: "folder-a").searchQuery)
    }

    private func entry(
        _ viewType: String,
        itemId: String? = nil,
        sidebarId: String? = nil,
        detailId: String? = nil,
        searchQuery: String? = nil
    ) -> AppNavigationHistory.Entry {
        AppNavigationHistory.Entry(
            viewType: viewType,
            viewItemId: itemId,
            selectedSidebarItemId: sidebarId,
            browserSelection: [],
            detailDocumentId: detailId,
            searchQuery: searchQuery
        )
    }
}
