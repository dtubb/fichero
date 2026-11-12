import Foundation

/// The left column's two parts and the two far-left toolbar buttons that drive them (Xcode-style).
/// The first button shows the folder tree, the second the chat conversations below it. Each lights
/// only while the column is up AND its part is on, and the column hides when neither is.
/// `treeHidden` is true while the chat stands alone in the column.
struct SidebarColumnState: Equatable {
    var columnShown: Bool
    var treeHidden: Bool
    var chatOn: Bool

    var treeLit: Bool { columnShown && !treeHidden }
    var chatLit: Bool { columnShown && chatOn }

    /// The tree button: hide the tree (the whole column when chat is not up), or bring the tree back.
    func togglingTree() -> SidebarColumnState {
        var next = self
        if treeLit {
            if chatLit {
                next.treeHidden = true
            } else {
                next.columnShown = false
                next.treeHidden = false
            }
        } else {
            next.columnShown = true
            next.treeHidden = false
        }
        return next
    }

    /// The chat button: hide the chat (the whole column when the tree is not up), or show it below
    /// the tree, or alone when the column was closed.
    func togglingChat() -> SidebarColumnState {
        var next = self
        if chatLit {
            next.chatOn = false
            if !treeLit {
                next.columnShown = false
                next.treeHidden = false
            }
        } else {
            if !columnShown { next.treeHidden = true }
            next.columnShown = true
            next.chatOn = true
        }
        return next
    }
}

/// Where the Sidebar/Chat pair is drawn (#6563). While the column is up it is an item of the sidebar column's own bar,
/// beside the window controls on the Mac and at the top of the iPad's sidebar; while the column is hidden it moves to
/// the content's bar, ahead of Back/Forward, so it can bring the column back. A compact iPhone, whose split view is a
/// single stack, has no pair: the column is the stack's root and Back returns to it.
enum SidebarPairHome: Equatable {
    case sidebarColumn
    case contentBar

    static func home(columnShown: Bool, isCompact: Bool) -> SidebarPairHome? {
        if isCompact { return nil }
        return columnShown ? .sidebarColumn : .contentBar
    }
}
