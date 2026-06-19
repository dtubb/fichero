@testable import Fichero
import Foundation
import XCTest

final class ChatWithDocsRoutingTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testChatWithDocsRoutesToMainChatOnly() {
        let route = ChatWithDocsRouter.mainChatRoute(documentIds: ["doc-a", "doc-b", "doc-a"])

        XCTAssertEqual(route.selectedDocumentIds, ["doc-a", "doc-b"])
        XCTAssertEqual(route.sidebarMode, .chat)
        XCTAssertEqual(route.viewMode, .chat(nil))
        XCTAssertFalse(route.sidebarShowsChat)
    }

    func testChatWithDocsActionDoesNotOpenSidebarChatSwap() throws {
        let source = try Self.appSource("Views/ContentView+ViewBuilders.swift")

        XCTAssertFalse(source.contains("withAnimation(.easeInOut(duration: 0.18)) { sidebarShowsChat = true }"))
    }

    func testSidebarPinnedRowsExposeChatWithDocsAsCommand() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView+PinnedNavigationRows.swift")

        XCTAssertTrue(source.contains("private func chatWithDocsNavigationRow() -> some View"))
        XCTAssertTrue(source.contains("onOpenChatWithCurrentScope?()"))
        XCTAssertFalse(source.contains("tag: \"chat-with-docs-browser\""))
    }

    func testSidebarSelectionDoesNotHandleChatWithDocsAsStickyNavigation() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView.swift")

        XCTAssertFalse(source.contains("id == \"chat-with-docs-browser\""))
    }

    func testChatInspectorOffersTouchFriendlyAddToChatAffordance() throws {
        let source = try Self.appSource("Views/Chat/ChatInspector+ScopedDocuments.swift")
        let headerSource = try Self.appSource("Views/Chat/ChatInspector+Header.swift")
        let inspectorSource = try Self.appSource("Views/Chat/ChatInspector.swift")

        XCTAssertTrue(source.contains("Add Current Selection to Chat"))
        XCTAssertTrue(source.contains("Search above or tap Add Current Selection to focus your chat."))
        XCTAssertTrue(source.contains(".buttonStyle(.borderedProminent)"))
        XCTAssertFalse(headerSource.contains("Label(\"Add to Chat\", systemImage: \"plus.circle\")"))
        XCTAssertTrue(inspectorSource.contains("var mergedSuggestedDocuments: Set<String>"))
    }

    func testCompactSidebarRowsExposeChatAndMoveToFolderActions() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarItemRow+Presentation.swift")

        XCTAssertTrue(source.contains("Label(\"Add to Chat\", systemImage: \"plus.circle\")"))
        XCTAssertTrue(source.contains("Menu(\"Move to Folder\")"))
        XCTAssertTrue(source.contains("sidebarState.dropErrorMessage = error.localizedDescription"))
        XCTAssertTrue(source.contains("onOpenChatWithCurrentScope()"))
    }
}
