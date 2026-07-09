import XCTest

final class ChatViewBoundaryTests: XCTestCase {
    func testChatViewNoLongerOwnsDuplicateConversationListState() throws {
        let source = try Self.appSource("Views/Chat/ChatView.swift")

        XCTAssertFalse(source.contains("@State var conversations"))
        XCTAssertTrue(source.contains("conversations: conversationService.conversations"))
    }

    func testResearchChatPaneDocumentsLibraryWideScopeHonestly() throws {
        let source = try Self.appSource("Views/Research/ResearchChatPane.swift")

        XCTAssertTrue(source.contains("library-wide ChatView"))
        XCTAssertTrue(source.contains("does NOT yet scope conversations"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero/\(relativePath)")
        return try String(contentsOf: url, encoding: .utf8)
    }
}
