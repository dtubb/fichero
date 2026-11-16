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

    @Test("the pair sits in the sidebar's own bar while the column is up (Mac and iPad, #6563)")
    func pairInSidebarWhileShown() {
        #expect(SidebarPairHome.home(columnShown: true, isCompact: false) == .sidebarColumn)
    }

    @Test("the pair moves to the content bar while the column is hidden, so it can bring it back (#6563)")
    func pairInContentBarWhileHidden() {
        #expect(SidebarPairHome.home(columnShown: false, isCompact: false) == .contentBar)
    }

    @Test("a compact iPhone has no pair; its split view is one stack (#6563)")
    func noPairWhenCompact() {
        #expect(SidebarPairHome.home(columnShown: true, isCompact: true) == nil)
        #expect(SidebarPairHome.home(columnShown: false, isCompact: true) == nil)
    }

    @Test("the Mac's sidebar bar declares the pair only while the column is its home (#6558)")
    func macDeclaresPairOnlyInItsHome() {
        #expect(SidebarPairHome.declaredInColumn(.sidebarColumn, onIOS: false))
        #expect(!SidebarPairHome.declaredInColumn(.contentBar, onIOS: false))
        #expect(!SidebarPairHome.declaredInColumn(nil, onIOS: false))
    }

    @Test("the iPad's sidebar bar keeps the pair after a hide, and a compact iPhone has none (#6563)")
    func iPadDeclaresPairWheneverThereIsOne() {
        #expect(SidebarPairHome.declaredInColumn(.sidebarColumn, onIOS: true))
        #expect(SidebarPairHome.declaredInColumn(.contentBar, onIOS: true))
        #expect(!SidebarPairHome.declaredInColumn(nil, onIOS: true))
    }

}
