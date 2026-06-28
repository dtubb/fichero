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
        // (No `sidebarShowsChat`: chat-with-docs routes to the main chat and
        // never swaps the sidebar — the struct has no such field. The no-swap
        // behaviour is guarded by testChatWithDocsActionDoesNotOpenSidebarChatSwap.)
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

    // MARK: - #2451: chat-with-document conversationId fix

    func testChatViewTracksBackendConversationId() throws {
        let source = try Self.appSource("Views/Chat/ChatView.swift")
        // Confirms the nil-sentinel state variable exists so first POST has no
        // client-generated UUID (the backend would 404 on an unknown UUID).
        XCTAssertTrue(source.contains("backendConversationId: String?"))
    }

    func testSendMessageUsesBackendConversationIdNotLocalUUID() throws {
        let source = try Self.appSource("Views/Chat/ChatView+Extensions.swift")
        // First message passes nil so the backend auto-creates the conversation.
        XCTAssertTrue(source.contains("conversationId: backendConversationId"))
        // The old pattern (client UUID) must be gone.
        XCTAssertFalse(source.contains("conversationId: currentConversation.id"))
    }

    func testBackendConversationIdIsUpdatedAfterFirstResponse() throws {
        let source = try Self.appSource("Views/Chat/ChatView+Extensions.swift")
        XCTAssertTrue(source.contains("backendConversationId = response.conversationId"))
    }

    func testStartNewChatResetsBackendConversationId() throws {
        let source = try Self.appSource("Views/Chat/ChatView+Extensions.swift")
        XCTAssertTrue(source.contains("backendConversationId = nil"))
    }

    func testDocumentScopeIsPassedToRAGRequest() throws {
        let source = try Self.appSource("Views/Chat/ChatView+Extensions.swift")
        // documentIds is non-nil only when selectedDocuments is non-empty.
        XCTAssertTrue(source.contains("documentIds: selectedDocuments.isEmpty ? nil : Array(selectedDocuments)"))
    }
}
