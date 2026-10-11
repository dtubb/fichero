import SwiftUI

// Put Back and Empty Trash… (#2077, #5243, `safety.trash.put-back`, `safety.trash.empty-is-one-step`).
// Each verb is ONE component that the Edit menu and the Trash pane's context menu both render, so it
// has one label and one action wherever it appears (`menus.context-matches-bar`).

/// What the key window's Trash offers its verbs: that project's Trash and the items selected in it.
/// Published by `TrashPane` while it shows.
struct TrashActionsTarget: Equatable {
    let store: TrashStore
    let selection: Set<String>

    /// The selected items, in the order the Trash lists them.
    var selectedIds: [String] { store.entries.map(\.id).filter(selection.contains) }

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.store === rhs.store && lhs.selection == rhs.selection
    }
}

extension FocusedValues {
    @Entry var trashActions: TrashActionsTarget?
}

/// Put Back: the selected items go back to their folders (or Sources), and the engine's sentence
/// about where they went shows in the Trash pane.
struct PutBackButton: View {
    let target: TrashActionsTarget?

    static func isEnabled(_ target: TrashActionsTarget?) -> Bool {
        guard let target else { return false }
        return !target.selectedIds.isEmpty && !target.store.isWorking
    }

    var body: some View {
        Button("Put Back") {
            guard let target else { return }
            let ids = target.selectedIds
            Task { await target.store.putBack(ids) }
        }
        .disabled(!Self.isEnabled(target))
    }
}

/// Empty Trash…: asks first, with the engine's question and its moved-items sentences
/// (`TrashStore.askToEmpty`); the Trash pane presents the question.
struct EmptyTrashButton: View {
    let store: TrashStore?

    static func isEnabled(_ store: TrashStore?) -> Bool {
        guard let store else { return false }
        return !store.isEmpty && !store.isWorking
    }

    var body: some View {
        Button("Empty Trash…") {
            guard let store else { return }
            Task { await store.askToEmpty() }
        }
        .disabled(!Self.isEnabled(store))
    }
}

/// The Edit menu's Put Back, for the key window's Trash.
struct FocusedPutBackButton: View {
    @FocusedValue(\.trashActions) private var target

    var body: some View {
        PutBackButton(target: target)
    }
}

/// The Edit menu's Empty Trash…, for the key window's Trash.
struct FocusedEmptyTrashButton: View {
    @FocusedValue(\.trashActions) private var target

    var body: some View {
        EmptyTrashButton(store: target?.store)
    }
}
