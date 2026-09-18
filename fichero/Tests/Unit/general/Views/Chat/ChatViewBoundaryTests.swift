@testable import Fichero
import SwiftUI
import XCTest

final class ChatViewBoundaryTests: XCTestCase {
    func testVisibleConversationsReturnsAllWhenFolderPathIsNil() {
        let conversations = [
            Conversation(id: "c1", folderPath: "/"),
            Conversation(id: "c2", folderPath: "/research/p1")
        ]

        XCTAssertEqual(
            ChatView.visibleConversations(conversations, folderPath: nil).map(\.id),
            ["c1", "c2"]
        )
    }

    func testVisibleConversationsFiltersToRequestedFolder() {
        let conversations = [
            Conversation(id: "root", folderPath: "/"),
            Conversation(id: "p1-a", folderPath: "/research/p1"),
            Conversation(id: "p1-b", folderPath: "/research/p1"),
            Conversation(id: "p2", folderPath: "/research/p2")
        ]

        XCTAssertEqual(
            ChatView.visibleConversations(conversations, folderPath: "/research/p1").map(\.id),
            ["p1-a", "p1-b"]
        )
    }

    func testChatViewNoLongerOwnsDuplicateConversationListState() throws {
        let source = try Self.appSource("Views/Chat/ChatView.swift")

        XCTAssertFalse(source.contains("@State var conversations"))
        // The old toolbar's `conversations:` argument is gone (2026-08-23) —
        // switching rides the crumb's jump-bar menu over the SAME
        // service-owned list, in the chrome split file.
        let chrome = try Self.appSource("Views/Chat/ChatView+PaneChrome.swift")
        XCTAssertTrue(chrome.contains("visibleConversations.map"))
    }

    func testResearchChatPaneScopesConversationsToProjectFolder() throws {
        let source = try Self.appSource("Views/Chat/Research/ResearchChatPane.swift")

        XCTAssertTrue(source.contains("conversationFolderPath: Self.conversationFolderPath(for: project)"))
        XCTAssertEqual(
            ResearchChatPane.conversationFolderPath(
                for: ResearchProject(
                    id: "proj-7",
                    name: "Research",
                    description: "",
                    status: .active,
                    createdAt: Date(timeIntervalSince1970: 0),
                    updatedAt: Date(timeIntervalSince1970: 0)
                )
            ),
            "/research/proj-7"
        )
    }

    // MARK: - #4817: the dock's stale-conversation bridge

    /// The dock mount (`PaneSpec.swift`'s `chatSurface`) re-renders `ChatView`
    /// on every sidebar selection with no `.id(…)` — `currentConversation`/
    /// `backendConversationId` are `@State`, seeded only at first mount, so
    /// without this bridge a sidebar-driven switch left the PREVIOUS
    /// conversation showing. Source-scan: a live `@State`-mutation test is
    /// awkward for SwiftUI view state without a hosting harness this suite
    /// does not have (the same limitation `ChatView`'s existing tests above
    /// already accept — they are source-scans too).
    func testChatViewObservesConversationChangesAndBridgesToSwitchConversation() throws {
        let source = try Self.appSource("Views/Chat/ChatView.swift")
        XCTAssertTrue(source.contains(".onChange(of: conversation?.id)"))
        // The pin guard — the SAME rule the title menu's own switch already
        // honors ("stay on THIS conversation" while pinned).
        XCTAssertTrue(source.contains("guard !isConversationPinned, let conversation else { return }"))
        XCTAssertTrue(source.contains("switchConversation(conversation)"))
    }

    /// `ResearchChatPane` always passes `conversation: nil`, so the bridge
    /// above never fires for it — its re-scoping signal is `researchProject`
    /// changing, which needs a PARALLEL observer, not the identical one.
    func testChatViewObservesResearchProjectChangesAndResetsToAFreshConversation() throws {
        let source = try Self.appSource("Views/Chat/ChatView.swift")
        XCTAssertTrue(source.contains(".onChange(of: researchProject?.id)"))
        XCTAssertTrue(source.contains("resetToFreshConversation()"))
    }

    /// `switchConversation` and `resetToFreshConversation` must reset the
    /// SAME composer state through one shared helper, or the two can drift
    /// on what "starting to look at something else" resets (#4817).
    func testSwitchConversationAndResetToFreshConversationShareOneResetHelper() throws {
        let source = try Self.appSource("Views/Chat/ChatView+Extensions.swift")
        XCTAssertEqual(
            source.components(separatedBy: "resetComposerState()").count - 1,
            3,  // 1 definition + 2 call sites
            "switchConversation and resetToFreshConversation must both call the shared helper"
        )
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent("\(relativePath)")
        return try String(contentsOf: url, encoding: .utf8)
    }
}
