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
        let source = try ([
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+Breadcrumb.swift"),
        ].joined(separator: "\n"))

        XCTAssertFalse(source.contains("withAnimation(.easeInOut(duration: 0.18)) { sidebarShowsChat = true }"))
    }

    /// Scoped chat is a command on a document node, not a pinned sidebar row.
    ///
    /// The pinned bottom rows were retired in #4102 — but the CAPABILITY must
    /// survive the row, and on every platform: Data ▸ New Chat opens an
    /// unscoped chat, so without a per-node command Mac loses document-scoped
    /// chat entirely. That is exactly the regression this pins.
    func testChatWithCurrentScopeIsANodeCommandOnEveryPlatform() throws {
        let pinned = try Self.appSource("Views/Sidebar/Sections/SidebarView+PinnedNavigationRows.swift")
        XCTAssertFalse(
            pinned.contains("chatWithDocsNavigationRow"),
            "the pinned Chat with Docs row is retired (#4102)"
        )

        let row = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        XCTAssertTrue(row.contains("private var chatWithScopeAction: some View"))
        XCTAssertTrue(row.contains("onOpenChatWithCurrentScope()"))
        XCTAssertTrue(
            row.contains("chatWithScopeAction"),
            "the command must be composed into rowContextMenu, not merely defined"
        )

        // The load-bearing half: the action must sit OUTSIDE the
        // compact-only branch, or Mac has no route to a scoped chat.
        guard let actionRange = row.range(of: "private var chatWithScopeAction: some View"),
              let compactRange = row.range(of: "private var compactTouchActions: some View") else {
            return XCTFail("expected both context-menu action builders")
        }
        let actionBody = row[actionRange.upperBound..<compactRange.lowerBound]
        XCTAssertFalse(
            actionBody.contains("horizontalSizeClass == .compact"),
            "scoped chat must not be size-class gated — Mac needs it too (#4102)"
        )
    }

    func testSidebarSelectionDoesNotHandleChatWithDocsAsStickyNavigation() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView.swift")

        XCTAssertFalse(source.contains("id == \"chat-with-docs-browser\""))
    }

    func testChatInspectorOffersTouchFriendlyAddToChatAffordance() throws {
        let source = try Self.appSource("Views/Chat/Inspector/ChatInspector+ScopedDocuments.swift")
        let headerSource = try Self.appSource("Views/Chat/Inspector/ChatInspector+Header.swift")
        let inspectorSource = try Self.appSource("Views/Chat/Inspector/ChatInspector.swift")

        XCTAssertTrue(source.contains("Add Current Selection to Chat"))
        XCTAssertTrue(source.contains("Search above or tap Add Current Selection to focus your chat."))
        XCTAssertTrue(source.contains(".buttonStyle(.borderedProminent)"))
        XCTAssertFalse(headerSource.contains("Label(\"Add to Chat\", systemImage: \"plus.circle\")"))
        XCTAssertTrue(inspectorSource.contains("var mergedSuggestedDocuments: Set<String>"))
    }

    func testCompactSidebarRowsExposeChatAndMoveToFolderActions() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        let helpers = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Helpers.swift")

        XCTAssertTrue(source.contains("Label(\"Add to Chat\", systemImage: \"plus.circle\")"))
        XCTAssertTrue(source.contains("Menu(\"Move to Folder\")"))
        XCTAssertTrue(helpers.contains("sidebarState.dropErrorMessage = error.localizedDescription"))
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
        XCTAssertTrue(source.contains("documentIds: groundingIds.isEmpty ? nil : Array(groundingIds)"))
    }
}
