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

    private func entry(
        _ viewType: String,
        itemId: String? = nil,
        sidebarId: String? = nil,
        detailId: String? = nil
    ) -> AppNavigationHistory.Entry {
        AppNavigationHistory.Entry(
            viewType: viewType,
            viewItemId: itemId,
            selectedSidebarItemId: sidebarId,
            browserSelection: [],
            detailDocumentId: detailId
        )
    }
}
