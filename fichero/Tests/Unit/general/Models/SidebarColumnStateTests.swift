@testable import Fichero
import Testing

@Suite("SidebarColumnState")
struct SidebarColumnStateTests {

    private static func state(shown: Bool, treeHidden: Bool = false, chat: Bool) -> SidebarColumnState {
        SidebarColumnState(columnShown: shown, treeHidden: treeHidden, chatOn: chat)
    }

    @Test("the tree button with only the tree up hides the whole column")
    func treeAloneHidesColumn() {
        let next = Self.state(shown: true, chat: false).togglingTree()
        #expect(!next.columnShown)
        #expect(!next.treeLit && !next.chatLit)
    }

    @Test("the tree button with chat up hides the tree and leaves the chat")
    func treeOffKeepsChat() {
        let next = Self.state(shown: true, chat: true).togglingTree()
        #expect(next.columnShown && next.treeHidden)
        #expect(!next.treeLit && next.chatLit)
    }

    @Test("the chat button with the tree up hides only the chat")
    func chatOffKeepsTree() {
        let next = Self.state(shown: true, chat: true).togglingChat()
        #expect(next.columnShown && !next.chatOn)
        #expect(next.treeLit && !next.chatLit)
    }

    @Test("the chat button with chat alone hides the whole column")
    func chatAloneHidesColumn() {
        let next = Self.state(shown: true, treeHidden: true, chat: true).togglingChat()
        #expect(!next.columnShown)
        #expect(!next.treeHidden)
    }

    @Test("the chat button on a closed column opens the chat alone")
    func chatOpensAlone() {
        let next = Self.state(shown: false, chat: false).togglingChat()
        #expect(next.columnShown && next.chatLit && !next.treeLit)
    }

    @Test("the tree button on a closed column opens the tree")
    func treeOpens() {
        let next = Self.state(shown: false, chat: false).togglingTree()
        #expect(next.treeLit && !next.chatLit)
    }

    @Test("with the chat alone, the tree button brings the tree back beside it")
    func treeBackBesideChat() {
        let next = Self.state(shown: true, treeHidden: true, chat: true).togglingTree()
        #expect(next.treeLit && next.chatLit)
    }

    @Test("closing both buttons in either order hides the column")
    func bothOffHides() {
        let both = Self.state(shown: true, chat: true)
        #expect(!both.togglingChat().togglingTree().columnShown)
        #expect(!both.togglingTree().togglingChat().columnShown)
    }
}
