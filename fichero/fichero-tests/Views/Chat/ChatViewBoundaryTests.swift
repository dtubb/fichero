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
        XCTAssertTrue(source.contains("conversations: visibleConversations"))
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

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero/\(relativePath)")
        return try String(contentsOf: url, encoding: .utf8)
    }
}
