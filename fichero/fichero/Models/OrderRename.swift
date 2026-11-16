import Foundation

/// Return renames in the Order list, Finder style (`source.editor.order-list-edits-like-finder`, Step 1.25):
/// one selected row edits in place -- a line its text, through the one correction path (`CorrectLine`).
/// A region's name waits for the engine's optional segment name, so a region does not begin an edit yet.
enum OrderRename {
    /// The words to start the edit with, or nil when Return does not begin one: several rows, none, or a
    /// segment that is not a line.
    static func begins(on selected: [Segment]) -> String? {
        guard selected.count == 1, let only = selected.first, CorrectLine.offers(only) else { return nil }
        return only.text ?? ""
    }

    /// What Return in the field sends: the words to record, or nil when nothing changed (cancel-like).
    static func commit(_ typed: String, on line: Segment) -> String? {
        CorrectLine.text(typed, replacing: line.text)
    }
}
