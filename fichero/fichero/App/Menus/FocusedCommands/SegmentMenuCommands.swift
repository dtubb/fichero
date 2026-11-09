import SwiftUI

/// What the menu bar's Edit › Segments ▸ acts on (#5229; was the Segment menu, #5652): the focused Preview's Edit Segments state, its
/// selection, and its OWN verbs -- the same audited calls its toolbar and context menu make, so the
/// menu is one more way in, never a second implementation.
struct SegmentMenuTarget {
    let isEditing: Bool
    let selectionCount: Int
    let toggleEditing: () -> Void
    let canSelectAll: Bool
    let selectAll: () -> Void
    let delete: () -> Void
    let join: () -> Void
    let apply: (SegmentEdit.Attribute) -> Void
}

extension FocusedValues {
    @Entry var segmentMenu: SegmentMenuTarget?
}

/// Edit › Segments ▸' items (were Page › Segments, #6413). Each disabled item's reason is shown under it, as the issue asks: a menu
/// that greys out with no word is how Delete went undiscovered.
struct SegmentMenuContent: View {
    @FocusedValue(\.segmentMenu) private var target

    var body: some View {
        let editing = target?.isEditing == true
        let count = target?.selectionCount ?? 0
        Button(editing ? "Stop Editing Shape" : "Edit Shape") { target?.toggleEditing() }
            .disabled(target == nil)
        if let reason = Self.reason(hasPage: target != nil, selected: count) {
            Text(reason)
        }
        Divider()
        Button("Select All Segments") { target?.selectAll() }
            .disabled(target?.canSelectAll != true)
        // No chord of its own: Edit › Delete (⌘⌫) is the one keyed home and takes the segments when the Preview holds them
        // (`SegmentDeleteRoute`). A bare ⌫ here would take the key from every text field.
        Button(Self.deleteTitle(count), role: .destructive) { target?.delete() }
            .disabled(!Self.canDelete(selected: count))
        Button("Join") { target?.join() }
            .keyboardShortcut("j", modifiers: [.command, .option])
            .disabled(count < 2)
        Divider()
        SegmentAttributeMenu.Items(apply: { target?.apply($0) })
            .disabled(count == 0)
    }

    static func deleteTitle(_ count: Int) -> String { count > 1 ? "Delete \(count) Segments" : "Delete Segment" }

    /// Delete needs a selection and no mode (#6413: the gate is going).
    static func canDelete(selected: Int) -> Bool { selected > 0 }

    /// Why the segments' verbs cannot act, said once under Edit Segments; nil when they can.
    static func reason(hasPage: Bool, selected: Int) -> String? {
        if !hasPage { return "Show a page in \(SourcePane.name) to edit its segments" }
        return selected == 0 ? "Select segments on the page" : nil
    }
}

/// Whether Edit › Delete (⌘⌫) deletes segments instead of items: the Preview holds the focus and has segments selected.
enum SegmentDeleteRoute {
    static func takesDelete(focusedPane: PaneFocus?, selectedSegments: Int) -> Bool {
        focusedPane == .preview && selectedSegments > 0
    }
}

/// Edit › Segments ▸: the page's segments on the focused Preview's selection (#5229; was the Segment menu, then Page › Segments,
/// #6413), then a line's and a segment's verbs on the focused list's selection (#5652 slice 4, group 3).
struct SegmentsEditMenu: View {
    var body: some View {
        Menu("Segments") {
            SegmentMenuContent()
            Divider()
            FocusedLineVerbButtons()
        }
    }
}
