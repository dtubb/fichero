@testable import Fichero
import XCTest

/// Spec: panes-magnifiers-workspaces `panes.chat.below-sidebar`. The assistant
/// chat moved out of the centre column into a region beneath the sidebar folder
/// tree; `ContentView.chatSurface` mounts ONE `ChatView` there. The only pure
/// decision in that relocation is WHICH conversation the surface shows — it
/// follows the view mode (a selected chat names its conversation; anything else
/// is a fresh one). This tests that decision without a running view.
final class ChatMountTests: XCTestCase {

    func testChatModeYieldsItsConversation() {
        let conversation = Conversation(id: "conv-1", title: "Hello")
        XCTAssertEqual(
            ChatMount.conversation(for: .chat(conversation))?.id,
            "conv-1",
            "A .chat(conversation) view mode names that conversation."
        )
    }

    func testChatModeWithNilYieldsFreshConversation() {
        XCTAssertNil(
            ChatMount.conversation(for: .chat(nil)),
            "A .chat(nil) view mode is a fresh conversation (nil)."
        )
    }

    func testNonChatModesYieldNoConversation() {
        XCTAssertNil(ChatMount.conversation(for: .library(nil)))
        XCTAssertNil(ChatMount.conversation(for: .automation))
        XCTAssertNil(
            ChatMount.conversation(for: .comparison(nil)),
            "A non-chat view mode never carries a chat conversation."
        )
    }
}
