@testable import Fichero
import SwiftUI
import Testing

/// The drop grammar between projects (#2397, `transfer.app.drag-sidebar`, `transfer.alias.not-between-projects`):
/// the same modifier keys as within a project, read by the one grammar (`sidebarDropOperation`), but ⌘⌥ is refused
/// instead of making an alias. What breaks without it: an ⌥-drag that moves, a plain drag that copies, or an alias
/// made in another project that points at nothing there.
@MainActor
struct ProjectTransferDropGrammarTests {
    private func decision(option: Bool, command: Bool) -> ProjectTransferDropDecision {
        ProjectTransferDropDecision(modifiers: SidebarDropModifiers(option: option, command: command))
    }

    @Test("a drag moves, ⌥ copies, ⌘⌥ is refused as an alias, ⌘ alone still moves")
    func modifierKeys() {
        #expect(decision(option: false, command: false) == .move)
        #expect(decision(option: true, command: false) == .copy)
        #expect(decision(option: true, command: true) == .refuseAlias)
        #expect(decision(option: false, command: true) == .move)
    }

    @Test("every surface's resolved operation maps the same way (sidebar rows, headers, Items cells and pane)")
    func resolvedOperations() {
        #expect(ProjectTransferDropDecision(.move) == .move)
        #expect(ProjectTransferDropDecision(.copy) == .copy)
        #expect(ProjectTransferDropDecision(.alias) == .refuseAlias)
    }

    /// The cursor badge within a project is unchanged by the transfer: the delegate still proposes the grammar's
    /// operation for an in-app drag, so a move shows no `+`.
    @Test("the delegate's badge still follows the one grammar")
    func badge() {
        #expect(libraryItemDropProposedOperation(isInAppDrag: true, modifiers: .init(option: false, command: false)) == .move)
        #expect(libraryItemDropProposedOperation(isInAppDrag: true, modifiers: .init(option: true, command: false)) == .copy)
    }
}
