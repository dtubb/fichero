import SwiftUI

/// What the menu bar's Segment menu acts on (#5229): the focused Preview's Edit Segments state, its
/// selection, and its OWN verbs -- the same audited calls its toolbar and context menu make, so the
/// menu is one more way in, never a second implementation.
struct SegmentMenuTarget {
    let isEditing: Bool
    let selectionCount: Int
    let toggleEditing: () -> Void
    let delete: () -> Void
    let join: () -> Void
    let apply: (SegmentEdit.Attribute) -> Void
}

extension FocusedValues {
    @Entry var segmentMenu: SegmentMenuTarget?
}

/// The Segment menu's items. Each disabled item's reason is shown under it, as the issue asks: a menu
/// that greys out with no word is how Delete went undiscovered.
struct SegmentMenuContent: View {
    @FocusedValue(\.segmentMenu) private var target

    var body: some View {
        let editing = target?.isEditing == true
        let count = target?.selectionCount ?? 0
        Button(editing ? "Stop Editing Segments" : "Edit Segments") { target?.toggleEditing() }
            .disabled(target == nil)
        if target == nil {
            Text("Show a page in the Preview to edit its segments")
        } else if !editing {
            Text("Turn on Edit Segments to change segments")
        } else if count == 0 {
            Text("Select segments on the page")
        }
        Divider()
        // No ⌫ here: a bare Delete key in the menu bar would take it from every text field. The page
        // keeps ⌫ while Edit Segments is on.
        Button(count > 1 ? "Delete \(count) Segments" : "Delete Segment", role: .destructive) { target?.delete() }
            .disabled(!editing || count == 0)
        Button("Join") { target?.join() }
            .keyboardShortcut("j", modifiers: .command)
            .disabled(!editing || count < 2)
        Divider()
        SegmentAttributeMenu.Items(apply: { target?.apply($0) })
            .disabled(!editing || count == 0)
    }
}
